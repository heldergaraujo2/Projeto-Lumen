"""OpenAIProvider — integração com a API da OpenAI (SDK oficial).

Características (Lumen 0.2):

- SDK importado **lazy**: o modo ``mock`` funciona mesmo sem o pacote
  ``openai`` instalado; testes injetam um client falso via
  ``client_factory`` e rodam 100% offline.
- Configuração validada na construção (API key e modelo) com mensagens
  claras explicando como configurar o ``.env``.
- Timeout por requisição (``LUMEN_REQUEST_TIMEOUT``) e retry limitado
  (``LUMEN_MAX_RETRIES``) **somente** para erros temporários (rate
  limit, timeout, rede, 5xx). Erros de autenticação/configuração nunca
  são repetidos.
- Streaming limpo: quando o chamador fornece ``on_delta``, a resposta é
  transmitida em pedaços; se uma tentativa falhar **após** emitir
  deltas, não repetimos (evita texto duplicado na UI).
- Resposta normalizada em :class:`~app.ai.types.AIResponse` (content,
  model, usage, finish_reason).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from app.ai.provider import (
    AIProvider,
    ContextMessage,
    DeltaCallback,
    InvalidModelError,
    MissingApiKeyError,
    ModelNotConfiguredError,
    ProviderAuthError,
    ProviderDependencyError,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    RETRYABLE_ERRORS,
    UnexpectedProviderError,
)
from app.ai.types import AIResponse, ResponseType, Usage

if TYPE_CHECKING:
    from app.config.settings import Settings

logger = logging.getLogger("lumen.ai.openai")

ClientFactory = Callable[[str, float], Any]
"""Receba (api_key, timeout) e devolve um client com ``chat.completions``."""

_ALLOWED_HISTORY_ROLES = ("user", "assistant")


class OpenAIProvider(AIProvider):
    """Provedor concreto para a API da OpenAI (chat/completions)."""

    name = "openai"

    def __init__(
        self,
        settings: "Settings | None" = None,
        client_factory: ClientFactory | None = None,
        retry_backoff: float = 0.5,
    ) -> None:
        self._model = str(getattr(settings, "model", "") or "").strip()
        self._api_key = str(getattr(settings, "api_key", "") or "").strip()
        self._timeout = float(getattr(settings, "request_timeout", 60.0) or 60.0)
        self._max_retries = int(getattr(settings, "max_retries", 2) or 0)
        self._retry_backoff = float(retry_backoff)
        self._client_factory = client_factory or self._default_client_factory
        self._client: Any = None

        self._validate_config()

    # ----------------------------------------------------------- configuração
    def _validate_config(self) -> None:
        """Falha rápido, com instrução clara de como configurar."""
        if not self._api_key:
            raise MissingApiKeyError(
                "LUMEN_API_KEY não configurada. Defina sua chave no arquivo .env "
                "(veja .env.example) ou volte ao modo offline com LUMEN_PROVIDER=mock."
            )
        if not self._model:
            raise ModelNotConfiguredError(
                "LUMEN_MODEL não configurado. Exemplo: LUMEN_MODEL=gpt-4o-mini no arquivo "
                ".env (veja .env.example), depois reinicie a Lumen."
            )

    @staticmethod
    def _default_client_factory(api_key: str, timeout: float) -> Any:
        try:
            import openai  # import lazy: só quando o provedor é realmente usado
        except ImportError as exc:
            raise ProviderDependencyError(
                "Dependência 'openai' não instalada. Execute: pip install -r requirements.txt"
            ) from exc
        # max_retries=0: retry é controlado por nós (política visível e testável).
        return openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=0)

    @property
    def model_name(self) -> str:
        return self._model

    # ------------------------------------------------------------------- API
    def generate(self, message: str, context: Sequence[ContextMessage] | None = None) -> str:
        """Compatibilidade 0.1: devolve apenas o texto da resposta."""
        return self.chat(message, context).content

    def chat(
        self,
        message: str,
        context: Sequence[ContextMessage] | None = None,
        *,
        system_prompt: str | None = None,
        on_delta: DeltaCallback | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Chama a API com timeout, retry limitado e streaming opcional.

        ``max_tokens`` limita o tamanho da resposta (usado pelo teste de
        conexão para manter a requisição barata; ``None`` = padrão da API).
        """
        self._validate_config()
        if self._client is None:
            self._client = self._client_factory(self._api_key, self._timeout)

        messages = self._build_messages(message, context, system_prompt)
        extra = {"max_tokens": max_tokens} if max_tokens is not None else {}
        total_attempts = self._max_retries + 1

        for attempt in range(1, total_attempts + 1):
            emitted = {"delta": False}

            def _delta(chunk: str, _emitted: dict = emitted, _sink: DeltaCallback = on_delta) -> None:  # noqa: B008
                _emitted["delta"] = True
                _sink(chunk)

            try:
                if on_delta is None:
                    return self._request_plain_compat(messages, extra)
                return self._request_streaming(messages, _delta)
            except ProviderError as exc:
                retryable = isinstance(exc, RETRYABLE_ERRORS)
                last_attempt = attempt == total_attempts
                if last_attempt or not retryable or emitted["delta"]:
                    logger.error(
                        "Chamada OpenAI falhou (tentativa %d/%d): %s",
                        attempt, total_attempts, exc,
                    )
                    raise
                delay = self._retry_backoff * attempt
                logger.warning(
                    "Tentativa %d/%d falhou (%s). Nova tentativa em %.1fs…",
                    attempt, total_attempts, type(exc).__name__, delay,
                )
                time.sleep(delay)

        raise UnexpectedProviderError("Loop de retry encerrado sem resultado.")  # pragma: no cover

    # ------------------------------------------------------------ mensagens
    @staticmethod
    def _build_messages(
        message: str,
        context: Sequence[ContextMessage] | None,
        system_prompt: str | None,
    ) -> list[dict[str, str]]:
        """Monta o payload: system prompt → histórico (sem timestamps) → mensagem."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for item in context or []:
            role = item.get("role", "")
            content = item.get("content", "")
            if role in _ALLOWED_HISTORY_ROLES and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
        return messages

    # ------------------------------------------------------------ requisições
    def _request_plain_compat(self, messages: list[dict[str, str]], extra: dict | None) -> AIResponse:
        """Requisição não-streaming com compatibilidade de parâmetros.

        Alguns modelos (ex.: série ``o``) não aceitam ``max_tokens``.
        Nesse caso específico — erro BadRequest citando ``max_tokens`` —
        a chamada é repetida **uma única vez** sem o parâmetro, mantendo
        o teste de conexão funcional com qualquer modelo.
        """
        try:
            return self._request_plain(messages, extra)
        except InvalidModelError as exc:
            cause = getattr(exc, "__cause__", None)
            if extra and cause is not None and "max_tokens" in str(cause).lower():
                logger.info("Modelo não aceita 'max_tokens'; repetindo sem o parâmetro.")
                return self._request_plain(messages, None)
            raise

    def _request_plain(self, messages: list[dict[str, str]], extra: dict | None = None) -> AIResponse:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                timeout=self._timeout,
                **(extra or {}),
            )
        except Exception as exc:
            raise self._map_exception(exc) from exc
        return self._normalize_plain(response)

    def _request_streaming(
        self, messages: list[dict[str, str]], on_delta: DeltaCallback
    ) -> AIResponse:
        try:
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
                timeout=self._timeout,
            )
            content_parts: list[str] = []
            finish_reason = ""
            model_name = ""
            for chunk in stream:
                model_name = getattr(chunk, "model", None) or model_name
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                choice = choices[0]
                finish_reason = getattr(choice, "finish_reason", None) or finish_reason
                delta = getattr(getattr(choice, "delta", None), "content", None)
                if delta:
                    content_parts.append(delta)
                    on_delta(delta)
        except Exception as exc:
            raise self._map_exception(exc) from exc

        return AIResponse(
            content="".join(content_parts),
            model=model_name or self._model,
            usage=None,  # SDK não envia usage no stream padrão; preservado no modo plain
            finish_reason=finish_reason,
            response_type=ResponseType.FINAL_RESPONSE,
        )

    @staticmethod
    def _normalize_plain(response: Any) -> AIResponse:
        choices = getattr(response, "choices", None) or []
        choice = choices[0] if choices else None
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) or ""
        usage_raw = getattr(response, "usage", None)
        usage = None
        if usage_raw is not None:
            usage = Usage(
                input_tokens=getattr(usage_raw, "prompt_tokens", None),
                output_tokens=getattr(usage_raw, "completion_tokens", None),
                total_tokens=getattr(usage_raw, "total_tokens", None),
            )
        return AIResponse(
            content=content,
            model=getattr(response, "model", None) or "",
            usage=usage,
            finish_reason=getattr(choice, "finish_reason", None) or "",
            response_type=ResponseType.FINAL_RESPONSE,
        )

    # ------------------------------------------------------------------ erros
    def _map_exception(self, exc: Exception) -> ProviderError:
        """Converte exceções do SDK na taxonomia interna (sem segredos)."""
        if isinstance(exc, ProviderError):
            return exc

        error_name = type(exc).__name__
        status = getattr(exc, "status_code", None)

        if error_name == "AuthenticationError" or status in (401, 403):
            return ProviderAuthError(
                "Chave de API inválida ou sem autorização. Verifique LUMEN_API_KEY no .env."
            )
        if error_name == "RateLimitError" or status == 429:
            return ProviderRateLimitError(
                "Limite de uso da API atingido (rate limit). Aguarde um momento e tente de novo."
            )
        if error_name == "NotFoundError" or status == 404:
            return InvalidModelError(
                f"Modelo '{self._model}' não está disponível para esta conta/chave API."
            )
        if "Timeout" in error_name:
            return ProviderTimeoutError(
                f"A requisição excedeu o tempo limite de {self._timeout:g}s."
            )
        if error_name in ("APIConnectionError", "ConnectionError") or isinstance(exc, ConnectionError):
            return ProviderNetworkError(
                "Falha de rede ao contatar o provedor. Verifique sua conexão com a internet."
            )
        if error_name == "InternalServerError" or (isinstance(status, int) and status >= 500):
            return ProviderServerError(
                "O servidor do provedor respondeu com erro interno (5xx). Tente novamente."
            )
        if error_name == "BadRequestError" and "model" in str(exc).lower():
            return InvalidModelError(
                f"Modelo '{self._model}' rejeitado pela API (BadRequest)."
            )
        return UnexpectedProviderError(
            f"Erro inesperado do provedor ({error_name}). Consulte data/logs/lumen.log."
        )
