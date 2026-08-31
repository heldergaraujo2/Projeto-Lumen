"""GeminiProvider — integração com a API do Google Gemini (SDK oficial google-genai).

Características (Lumen 0.2 — complemento de providers):

- SDK oficial ``google-genai`` (recomendado pelo Google; o legado
  ``google-generativeai`` está deprecated) importado **lazy**: modo mock
  e testes funcionam sem o pacote instalado.
- ``client_factory`` injetável: testes injetam um client falso (interface
  ``models.generate_content(_stream)(model=…, contents=…, config=dict)``)
  e rodam 100% offline. A factory padrão envolve o SDK real em um
  adaptador que converte o ``config`` (dict) em ``GenerateContentConfig``
  e o timeout de segundos para milissegundos (unidade do SDK).
- Modelo **padrão GA** ``gemini-2.5-flash`` quando ``LUMEN_MODEL`` vazio
  (escolha documentada; ver docs/ARCHITECTURE.md §3.5).
- Timeout (``LUMEN_REQUEST_TIMEOUT``) e retry limitado
  (``LUMEN_MAX_RETRIES``) apenas para erros temporários — mesma política
  do OpenAIProvider; sem retry após deltas de streaming emitidos.
- Streaming via ``generate_content_stream``; system prompt via
  ``system_instruction``; histórico com roles mapeados para o formato
  nativo (``assistant`` → ``model``).
- Resposta normalizada em :class:`~app.ai.types.AIResponse` com
  ``usage_metadata`` preservado (input/output/total tokens).
- Erros convertidos para a taxonomia interna (``ClientError.code`` 400/
  401/403/404/429, ``ServerError`` 5xx, timeout, rede) com mensagens
  amigáveis e **sem segredos**.
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

logger = logging.getLogger("lumen.ai.gemini")

#: Modelo padrão (GA) usado quando LUMEN_MODEL estiver vazio.
#: Escolha baseada na documentação oficial atual (models page / dev guide):
#: "best price-performance model for low-latency, high-volume tasks that
#: require reasoning" — adequado para conversa e programação.
DEFAULT_MODEL = "gemini-2.5-flash"

ClientFactory = Callable[[str, float], Any]
"""Recebe (api_key, timeout_em_segundos) e devolve um client com ``models``."""

_ALLOWED_HISTORY_ROLES = ("user", "assistant")
_ROLE_MAP = {"user": "user", "assistant": "model"}


# ------------------------------------------------- adaptador do SDK oficial
class _SdkAdapterModels:
    """Converte a interface dict da Lumen para a do SDK google-genai."""

    def __init__(self, sdk_client: Any, types_module: Any) -> None:
        self._client = sdk_client
        self._types = types_module

    def _config(self, config: dict | None) -> Any:
        if not config:
            return None
        return self._types.GenerateContentConfig(**config)

    def generate_content(self, *, model: str, contents: list, config: dict | None):
        return self._client.models.generate_content(
            model=model, contents=contents, config=self._config(config)
        )

    def generate_content_stream(self, *, model: str, contents: list, config: dict | None):
        return self._client.models.generate_content_stream(
            model=model, contents=contents, config=self._config(config)
        )


class _SdkAdapter:
    """Client com a interface consumida pelo GeminiProvider."""

    def __init__(self, sdk_client: Any, types_module: Any) -> None:
        self._models = _SdkAdapterModels(sdk_client, types_module)

    @property
    def models(self) -> _SdkAdapterModels:
        return self._models


class GeminiProvider(AIProvider):
    """Provedor concreto para a API do Google Gemini (generate_content)."""

    name = "gemini"

    def __init__(
        self,
        settings: "Settings | None" = None,
        client_factory: ClientFactory | None = None,
        retry_backoff: float = 0.5,
    ) -> None:
        self._model = str(getattr(settings, "model", "") or "").strip() or DEFAULT_MODEL
        self._api_key = str(getattr(settings, "api_key", "") or "").strip()
        self._timeout = float(getattr(settings, "request_timeout", 60.0) or 60.0)
        self._max_retries = int(getattr(settings, "max_retries", 2) or 0)
        self._retry_backoff = float(retry_backoff)
        self._client_factory = client_factory or self._default_client_factory
        self._client: Any = None

        if not self._api_key:
            raise MissingApiKeyError(
                "LUMEN_API_KEY não configurada para o Gemini. Defina sua chave do "
                "Google AI Studio na tela ⚙ Configurações (ou no .env; veja "
                ".env.example) ou volte ao modo offline com LUMEN_PROVIDER=mock."
            )

    # ----------------------------------------------------------- configuração
    @staticmethod
    def _default_client_factory(api_key: str, timeout: float) -> Any:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ProviderDependencyError(
                "Dependência 'google-genai' não instalada. Execute: "
                "pip install -r requirements.txt"
            ) from exc
        # O SDK oficial espera o timeout em milissegundos.
        sdk_client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout * 1000)),
        )
        return _SdkAdapter(sdk_client, types)

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
        """Chama o Gemini com timeout, retry limitado e streaming opcional.

        ``max_tokens`` vira ``max_output_tokens`` quando fornecido.
        """
        if not self._api_key:
            raise MissingApiKeyError(
                "LUMEN_API_KEY não configurada para o Gemini (veja ⚙ Configurações)."
            )
        if self._client is None:
            self._client = self._client_factory(self._api_key, self._timeout)

        contents = self._build_contents(message, context)
        config: dict[str, Any] = {}
        if system_prompt:
            config["system_instruction"] = system_prompt
        if max_tokens is not None:
            config["max_output_tokens"] = max_tokens

        total_attempts = self._max_retries + 1
        for attempt in range(1, total_attempts + 1):
            emitted = {"delta": False}

            def _delta(chunk: str, _emitted: dict = emitted, _sink=on_delta) -> None:
                _emitted["delta"] = True
                _sink(chunk)

            try:
                if on_delta is None:
                    return self._request_plain(contents, config)
                return self._request_streaming(contents, config, _delta)
            except ProviderError as exc:
                retryable = isinstance(exc, RETRYABLE_ERRORS)
                last_attempt = attempt == total_attempts
                if last_attempt or not retryable or emitted["delta"]:
                    logger.error(
                        "Chamada Gemini falhou (tentativa %d/%d): %s",
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
    def _build_contents(
        message: str, context: Sequence[ContextMessage] | None
    ) -> list[dict]:
        """Histórico + mensagem atual no formato nativo (role ``model`` p/ assistant)."""
        contents: list[dict] = []
        for item in context or []:
            role = item.get("role", "")
            text = item.get("content", "")
            if role in _ALLOWED_HISTORY_ROLES and text:
                contents.append({
                    "role": _ROLE_MAP[role],
                    "parts": [{"text": text}],
                })
        contents.append({"role": "user", "parts": [{"text": message}]})
        return contents

    # ------------------------------------------------------------ requisições
    def _request_plain(self, contents: list, config: dict) -> AIResponse:
        try:
            response = self._client.models.generate_content(
                model=self._model, contents=contents, config=config or None
            )
        except Exception as exc:
            raise self._map_exception(exc) from exc
        return self._normalize(response)

    def _request_streaming(self, contents: list, config: dict, on_delta) -> AIResponse:
        try:
            stream = self._client.models.generate_content_stream(
                model=self._model, contents=contents, config=config or None
            )
            parts: list[str] = []
            finish_reason = ""
            model_name = ""
            usage: Usage | None = None
            for chunk in stream:
                model_name = getattr(chunk, "model_version", None) or model_name
                meta = getattr(chunk, "usage_metadata", None)
                if meta is not None:
                    usage = self._usage_from(meta)
                candidates = getattr(chunk, "candidates", None) or []
                if not candidates:
                    continue
                candidate = candidates[0]
                finish = getattr(candidate, "finish_reason", None)
                if finish is not None and str(finish):
                    finish_reason = self._finish_name(finish)
                text = self._candidate_text(candidate)
                if text:
                    parts.append(text)
                    on_delta(text)
        except Exception as exc:
            raise self._map_exception(exc) from exc

        return AIResponse(
            content="".join(parts),
            model=model_name or self._model,
            usage=usage,
            finish_reason=finish_reason,
            response_type=ResponseType.FINAL_RESPONSE,
        )

    # ---------------------------------------------------------- normalização
    @staticmethod
    def _candidate_text(candidate: Any) -> str:
        """Extrai o texto de um candidato de forma tolerante."""
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        texts = [getattr(part, "text", "") or "" for part in parts]
        return "".join(texts)

    @staticmethod
    def _finish_name(finish: Any) -> str:
        """Enum do SDK → nome legível (ex.: ``FinishReason.STOP`` → ``STOP``)."""
        return str(getattr(finish, "name", None) or finish)

    @staticmethod
    def _usage_from(meta: Any) -> Usage:
        return Usage(
            input_tokens=getattr(meta, "prompt_token_count", None),
            output_tokens=getattr(meta, "candidates_token_count", None),
            total_tokens=getattr(meta, "total_token_count", None),
        )

    def _normalize(self, response: Any) -> AIResponse:
        candidates = getattr(response, "candidates", None) or []
        content = self._candidate_text(candidates[0]) if candidates else ""
        finish_reason = ""
        if candidates:
            finish = getattr(candidates[0], "finish_reason", None)
            if finish is not None and str(finish):
                finish_reason = self._finish_name(finish)
        usage = None
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            usage = self._usage_from(meta)
        return AIResponse(
            content=content,
            model=getattr(response, "model_version", None) or self._model,
            usage=usage,
            finish_reason=finish_reason,
            response_type=ResponseType.FINAL_RESPONSE,
        )

    # ------------------------------------------------------------------ erros
    def _map_exception(self, exc: Exception) -> ProviderError:
        """Converte exceções do SDK na taxonomia interna (sem segredos)."""
        if isinstance(exc, ProviderError):
            return exc

        error_name = type(exc).__name__
        code = getattr(exc, "code", None)
        message = str(exc)

        if error_name == "MissingApiKeyError":
            return MissingApiKeyError(
                "Chave do Gemini ausente. Configure em ⚙ Configurações ou .env."
            )
        if error_name == "ClientError" or (isinstance(code, int) and 400 <= code < 500):
            if code in (401, 403):
                return ProviderAuthError(
                    "Chave de API inválida ou sem autorização. Verifique sua chave "
                    "do Google AI Studio."
                )
            if code == 429:
                return ProviderRateLimitError(
                    "Limite de uso do Gemini atingido (rate limit/quota). Aguarde um "
                    "momento e tente de novo."
                )
            if code == 404:
                return InvalidModelError(
                    f"Modelo '{self._model}' não está disponível para esta chave/API."
                )
            if code == 400:
                low = message.lower()
                if "api key" in low or "api_key" in low:
                    return ProviderAuthError(
                        "Chave de API inválida. Gere uma nova chave no Google AI Studio."
                    )
                if "model" in low:
                    return InvalidModelError(
                        f"Modelo '{self._model}' rejeitado pela API do Gemini."
                    )
                return ProviderError(f"Requisição inválida ao Gemini (400): {message[:160]}")
        if error_name == "ServerError" or (isinstance(code, int) and code >= 500):
            return ProviderServerError(
                "O servidor do Gemini respondeu com erro interno (5xx). Tente novamente."
            )
        if "timeout" in error_name.lower() or "deadline" in error_name.lower():
            return ProviderTimeoutError(
                f"A requisição excedeu o tempo limite de {self._timeout:g}s."
            )
        if "connect" in error_name.lower() or isinstance(exc, ConnectionError):
            return ProviderNetworkError(
                "Falha de rede ao contatar o Gemini. Verifique sua conexão com a internet."
            )
        return UnexpectedProviderError(
            f"Erro inesperado do provedor ({error_name}). Consulte data/logs/lumen.log."
        )
