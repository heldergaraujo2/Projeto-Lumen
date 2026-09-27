"""Provider local Ollama para a Lumen.

Integra a API HTTP local do Ollama sem adicionar um SDK obrigatório.
O Provider permanece desacoplado do Agent: conversa via o contrato AIProvider,
suporta histórico, system prompt, streaming NDJSON e health check.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.ai.provider import (
    AIProvider, ContextMessage, DeltaCallback, InvalidModelError,
    ModelNotConfiguredError, ProviderError, ProviderNetworkError,
    ProviderServerError, ProviderTimeoutError,
)
from app.ai.types import AIResponse, Usage

if TYPE_CHECKING:
    from app.config.settings import Settings

logger = logging.getLogger("lumen.ai.ollama")

DEFAULT_MODEL = "qwen2.5-coder:7b-instruct-q8_0"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_KEEP_ALIVE = "5m"

Transport = Callable[[str, str, bytes | None, float], Iterator[bytes]]


class OllamaProvider(AIProvider):
    """Provider local-first para Ollama /api/chat."""

    name = "ollama"

    def __init__(self, settings: "Settings | None" = None, *, transport: Transport | None = None) -> None:
        self._model = str(getattr(settings, "model", "") or "").strip() or DEFAULT_MODEL
        self._base_url = (str(getattr(settings, "ollama_base_url", "") or "").strip() or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = float(getattr(settings, "request_timeout", 60.0) or 60.0)
        self._keep_alive = str(getattr(settings, "ollama_keep_alive", "") or "").strip() or DEFAULT_KEEP_ALIVE
        self._transport = transport or self._default_transport
        if not self._model:
            raise ModelNotConfiguredError("LUMEN_MODEL não configurado para o Ollama.")

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def generate(self, message: str, context: Sequence[ContextMessage] | None = None) -> str:
        return self.chat(message, context).content

    def chat(
        self, message: str, context: Sequence[ContextMessage] | None = None,
        *, system_prompt: str | None = None, on_delta: DeltaCallback | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("A mensagem não pode ser vazia.")

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for item in context or ():
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", ""))
            if role in {"system", "user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message.strip()})

        options: dict[str, Any] = {}
        if max_tokens is not None:
            if not isinstance(max_tokens, int) or max_tokens < 1:
                raise ValueError("max_tokens deve ser um inteiro >= 1.")
            options["num_predict"] = max_tokens

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "keep_alive": self._keep_alive,
        }
        if options:
            payload["options"] = options

        text_parts: list[str] = []
        final_model = self._model
        finish_reason = "stop"
        usage = Usage()

        for raw in self._request("/api/chat", payload):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProviderError("O Ollama devolveu um evento de streaming inválido.") from exc
            if not isinstance(event, Mapping):
                raise ProviderError("O Ollama devolveu um evento inesperado.")
            if event.get("error"):
                raise self._map_api_error(str(event["error"]), 500)

            final_model = str(event.get("model") or final_model)
            msg = event.get("message")
            delta = msg.get("content", "") if isinstance(msg, Mapping) else ""
            if delta:
                text_parts.append(str(delta))
                if on_delta:
                    on_delta(str(delta))

            if event.get("done"):
                finish_reason = str(event.get("done_reason") or "stop")
                usage = Usage(
                    input_tokens=_int_or_none(event.get("prompt_eval_count")),
                    output_tokens=_int_or_none(event.get("eval_count")),
                    total_tokens=_sum_tokens(event.get("prompt_eval_count"), event.get("eval_count")),
                )

        content = "".join(text_parts)
        if not content.strip():
            raise ProviderError("O Ollama respondeu sem conteúdo.")

        return AIResponse(content=content, model=final_model, usage=usage, finish_reason=finish_reason)

    def health_check(self) -> bool:
        """Confirma que o daemon Ollama responde em /api/tags."""
        try:
            list(self._request("/api/tags", None))
            return True
        except ProviderError:
            return False

    def list_models(self) -> tuple[str, ...]:
        """Retorna modelos instalados sem fazer pull automático."""
        data = b"".join(self._request("/api/tags", None))
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("Resposta inválida ao listar modelos do Ollama.") from exc
        models = payload.get("models", []) if isinstance(payload, Mapping) else []
        return tuple(str(item["name"]) for item in models if isinstance(item, Mapping) and item.get("name"))

    def _request(self, path: str, payload: Mapping[str, Any] | None) -> Iterator[bytes]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        try:
            stream = self._transport(
                "POST" if payload is not None else "GET",
                f"{self._base_url}{path}",
                body,
                self._timeout,
            )
        except TimeoutError as exc:
            raise ProviderTimeoutError("O Ollama excedeu o tempo limite configurado.") from exc
        except HTTPError as exc:
            raise self._map_api_error(_read_http_error(exc), exc.code) from exc
        except (URLError, OSError) as exc:
            raise ProviderNetworkError(f"Não foi possível conectar ao Ollama em {self._base_url}.") from exc

        def guarded() -> Iterator[bytes]:
            try:
                yield from stream
            except TimeoutError as exc:
                raise ProviderTimeoutError("O Ollama excedeu o tempo limite configurado.") from exc
            except HTTPError as exc:
                raise self._map_api_error(_read_http_error(exc), exc.code) from exc
            except (URLError, OSError) as exc:
                raise ProviderNetworkError(
                    f"Não foi possível conectar ao Ollama em {self._base_url}."
                ) from exc

        return guarded()

    @staticmethod
    def _default_transport(method: str, url: str, body: bytes | None, timeout: float) -> Iterator[bytes]:
        request = Request(url, data=body, method=method, headers={
            "Content-Type": "application/json", "Accept": "application/x-ndjson",
        })
        response = urlopen(request, timeout=timeout)

        def iterator() -> Iterator[bytes]:
            with response:
                for line in response:
                    yield line

        return iterator()

    @staticmethod
    def _map_api_error(message: str, status: int) -> ProviderError:
        lowered = message.lower()
        if status == 404 and "model" in lowered:
            return InvalidModelError(f"Modelo Ollama não encontrado: {message}")
        if status >= 500:
            return ProviderServerError(f"O servidor Ollama retornou erro {status}: {message}")
        if status in {408, 504}:
            return ProviderTimeoutError("O Ollama excedeu o tempo limite.")
        if "not found" in lowered or ("model" in lowered and "pull" in lowered):
            return InvalidModelError(f"Modelo Ollama indisponível: {message}")
        return ProviderError(f"Ollama rejeitou a requisição ({status}): {message}")


def _read_http_error(exc: HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")[:1000]
    except OSError:
        return str(exc)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _sum_tokens(first: Any, second: Any) -> int | None:
    a, b = _int_or_none(first), _int_or_none(second)
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)
