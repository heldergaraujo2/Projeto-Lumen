"""Clientes HTTP de busca na web (Fase 1) — Tavily e Brave Search.

Implementados com ``urllib`` da stdlib (nenhuma dependência nova), no mesmo
padrão de injeção de transporte do :class:`~app.ai.ollama_provider.OllamaProvider`:
o parâmetro ``transport`` permite testar sem rede.

Referências de API (2026-10):
- Tavily:  ``POST https://api.tavily.com/search`` com
  ``Authorization: Bearer <key>``. A chave **não** vai no corpo — o campo
  ``api_key`` no body foi descontinuado pela Tavily.
  Tavily também aceita modo *keyless* (``X-Tavily-Access-Mode: keyless``),
  exposto aqui como opt-in explícito para o teste rápido do bootstrap.
- Brave:   ``GET https://api.search.brave.com/res/v1/web/search`` com
  ``X-Subscription-Token: <key>``.

Nenhuma chave é registrada em log ou incluída em mensagem de erro:
:func:`redact_secret` é aplicada a todo texto que sai deste módulo.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config.settings import ENV_FILE, _parse_env_file
from app.research.models import (
    MAX_RAW_CONTENT_CHARS,
    MAX_SNIPPET_CHARS,
    SearchResult,
    WebSearchResponse,
)

logger = logging.getLogger("lumen.research")

#: Transporte injetável: (method, url, body, headers, timeout) -> (status, body)
Transport = Callable[[str, str, bytes | None, Mapping[str, str], float], tuple[int, bytes]]

TAVILY_ENDPOINT = "https://api.tavily.com/search"
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

#: Nomes de variável de ambiente aceitos, em ordem de precedência.
TAVILY_KEY_ENV_VARS: tuple[str, ...] = ("TAVILY_API_KEY", "LUMEN_TAVILY_API_KEY")
BRAVE_KEY_ENV_VARS: tuple[str, ...] = ("BRAVE_API_KEY", "LUMEN_BRAVE_API_KEY")

DEFAULT_MAX_RESULTS = 5
MAX_RESULTS_CEILING = 10
DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 120.0
#: Teto de bytes aceitos do provedor (anti-DoS).
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

DEFAULT_TAVILY_DEPTH = "basic"
TAVILY_DEPTHS = frozenset({"basic", "advanced", "fast", "ultra-fast"})


class SearchProviderError(RuntimeError):
    """Falha ao consultar um provedor de busca."""


class SearchUnavailableError(SearchProviderError):
    """Provedor não configurado (sem chave de API, por exemplo)."""


class SearchResponseTooLargeError(SearchProviderError):
    """Resposta do provedor excedeu o teto de bytes."""


def redact_secret(text: str, secret: str | None) -> str:
    """Remove uma chave de API de um texto qualquer.

    Aplicada a toda mensagem que possa conter a chave (URLs de erro,
    corpos de resposta ecoados pelo provedor, tracebacks).
    """
    if not secret:
        return text
    return text.replace(secret, "***REDACTED***")


def _search_config(name: str, file_values: Mapping[str, str]) -> str:
    """Ambiente real vence .env; nunca registra o valor em logs."""
    return (os.environ[name] if name in os.environ else file_values.get(name, "")).strip()


def _resolve_key(env_vars: Sequence[str]) -> str:
    file_values = _parse_env_file(ENV_FILE)
    for name in env_vars:
        value = _search_config(name, file_values)
        if value:
            return value
    return ""


def _default_transport(
    method: str, url: str, body: bytes | None, headers: Mapping[str, str], timeout: float
) -> tuple[int, bytes]:
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 (host fixo por provedor)
            return int(getattr(response, "status", 200)), response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        # HTTPError é uma resposta: leia o corpo (curto) para a mensagem.
        return int(exc.code), exc.read(MAX_RESPONSE_BYTES + 1)[:2_000]
    except URLError as exc:
        raise SearchProviderError(f"falha de rede ao consultar o provedor: {exc.reason}") from exc


class SearchProvider(Protocol):
    """Contrato mínimo de um provedor de busca."""

    name: str

    def search(
        self,
        query: str,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> WebSearchResponse: ...


class _HttpSearchProvider:
    """Base comum: transporte, timeout, teto de bytes e parsing defensivo."""

    name = "http"

    def __init__(
        self,
        *,
        api_key: str = "",
        transport: Transport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if timeout <= 0 or timeout > MAX_TIMEOUT:
            raise ValueError(f"timeout deve estar em (0, {MAX_TIMEOUT}]; recebido {timeout}")
        self._api_key = api_key.strip()
        self._transport = transport or _default_transport
        self._timeout = float(timeout)

    # ------------------------------------------------------------- helpers
    @property
    def has_key(self) -> bool:
        return bool(self._api_key)

    def _clamp_results(self, max_results: int) -> int:
        if not isinstance(max_results, int) or isinstance(max_results, bool):
            raise ValueError("max_results deve ser inteiro")
        if max_results < 1:
            raise ValueError("max_results deve ser >= 1")
        return min(max_results, MAX_RESULTS_CEILING)

    def _read(
        self,
        method: str,
        url: str,
        body: bytes | None,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        try:
            status, payload = self._transport(method, url, body, headers, timeout)
        except SearchProviderError:
            raise
        except OSError as exc:  # pragma: no cover - defesa extra
            raise SearchProviderError(
                redact_secret(f"falha de rede: {exc}", self._api_key)
            ) from exc
        if len(payload) > MAX_RESPONSE_BYTES:
            raise SearchResponseTooLargeError(
                f"resposta do provedor excedeu {MAX_RESPONSE_BYTES} bytes"
            )
        return status, payload

    def _decode(self, status: int, payload: bytes) -> dict:
        if status >= 400:
            detail = redact_secret(
                payload.decode("utf-8", errors="replace")[:400], self._api_key
            )
            raise SearchProviderError(f"provedor respondeu HTTP {status}: {detail}")
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SearchProviderError(
                redact_secret(f"resposta do provedor não é JSON válido: {exc}", self._api_key)
            ) from exc
        if not isinstance(data, dict):
            raise SearchProviderError("resposta do provedor deve ser um objeto JSON")
        return data

    def _build_results(self, notes: list[str]) -> list[SearchResult]:  # pragma: no cover
        raise NotImplementedError

    @staticmethod
    def _clean(text: object, limit: int) -> str:
        if not isinstance(text, str):
            return ""
        return text.strip()[:limit]


class TavilySearchProvider(_HttpSearchProvider):
    """Provedor Tavily (``POST /search``, chave no header ``Authorization``)."""

    name = "tavily"

    #: Modo sem chave da Tavily — só usado quando ``allow_keyless=True``.
    #: Serve para o teste rápido do bootstrap, sem cadastro.
    ACCESS_MODE_HEADER = "X-Tavily-Access-Mode"

    def __init__(
        self,
        *,
        api_key: str = "",
        transport: Transport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        allow_keyless: bool = False,
        search_depth: str = DEFAULT_TAVILY_DEPTH,
        include_answer: bool = False,
    ) -> None:
        super().__init__(api_key=api_key, transport=transport, timeout=timeout)
        if search_depth not in TAVILY_DEPTHS:
            raise ValueError(
                f"search_depth inválido: {search_depth!r}; use um de {sorted(TAVILY_DEPTHS)}"
            )
        self._allow_keyless = bool(allow_keyless)
        self._search_depth = search_depth
        self._include_answer = bool(include_answer)

    @classmethod
    def from_env(
        cls, *, transport: Transport | None = None, allow_keyless: bool = False, **kwargs
    ) -> "TavilySearchProvider":
        return cls(
            api_key=_resolve_key(TAVILY_KEY_ENV_VARS),
            transport=transport,
            allow_keyless=allow_keyless,
            **kwargs,
        )

    def search(
        self,
        query: str,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float | None = None,
    ) -> WebSearchResponse:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query é obrigatória (texto não vazio)")
        if not self._api_key and not self._allow_keyless:
            raise SearchUnavailableError(
                "Tavily sem chave de API. Defina TAVILY_API_KEY "
                "(ou LUMEN_TAVILY_API_KEY) ou use allow_keyless=True para o modo sem chave."
            )
        limit = self._clamp_results(max_results)
        effective_timeout = self._timeout if timeout is None else float(timeout)

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        else:
            headers[self.ACCESS_MODE_HEADER] = "keyless"

        body = json.dumps(
            {
                "query": query.strip(),
                "search_depth": self._search_depth,
                "max_results": limit,
                "include_answer": self._include_answer,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        status, payload = self._read(
            "POST", TAVILY_ENDPOINT, body, headers, effective_timeout
        )
        data = self._decode(status, payload)

        notes: list[str] = []
        if not self._api_key:
            notes.append("modo keyless da Tavily (limites reduzidos)")

        raw_results = data.get("results")
        if raw_results is None:
            raw_results = []
        if not isinstance(raw_results, list):
            raise SearchProviderError("campo 'results' da Tavily deve ser uma lista")

        results: list[SearchResult] = []
        discarded = 0
        for item in raw_results:
            if not isinstance(item, dict):
                discarded += 1
                continue
            url = self._clean(item.get("url"), 2_000)
            if not url.startswith(("http://", "https://")):
                discarded += 1
                continue
            score = item.get("score", 0.0)
            try:
                score_value = float(score)
            except (TypeError, ValueError):
                score_value = 0.0
            score_value = min(max(score_value, 0.0), 1.0)
            try:
                result = SearchResult(
                    title=self._clean(item.get("title"), 500),
                    url=url,
                    content=self._clean(item.get("content"), MAX_SNIPPET_CHARS),
                    score=score_value,
                    raw_content=(
                        self._clean(item.get("raw_content"), MAX_RAW_CONTENT_CHARS) or None
                    ),
                )
                result.validate()
            except ValueError as exc:
                logger.debug("resultado descartado: %s", exc)
                discarded += 1
                continue
            results.append(result)

        if discarded:
            notes.append(f"{discarded} resultado(s) descartado(s) por formato inválido")

        answer = data.get("answer")
        response = WebSearchResponse(
            query=query.strip(),
            provider=self.name,
            results=tuple(results),
            answer=self._clean(answer, MAX_SNIPPET_CHARS) or None,
            truncated=len(results) >= limit,
            notes=tuple(notes),
        )
        response.validate()
        return response


class BraveSearchProvider(_HttpSearchProvider):
    """Provedor Brave Search (``GET /res/v1/web/search``)."""

    name = "brave"

    @classmethod
    def from_env(cls, *, transport: Transport | None = None, **kwargs) -> "BraveSearchProvider":
        return cls(api_key=_resolve_key(BRAVE_KEY_ENV_VARS), transport=transport, **kwargs)

    def search(
        self,
        query: str,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: float | None = None,
    ) -> WebSearchResponse:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query é obrigatória (texto não vazio)")
        if not self._api_key:
            raise SearchUnavailableError(
                "Brave Search sem chave de API. Defina BRAVE_API_KEY "
                "(ou LUMEN_BRAVE_API_KEY)."
            )
        limit = self._clamp_results(max_results)
        effective_timeout = self._timeout if timeout is None else float(timeout)

        url = f"{BRAVE_ENDPOINT}?{urlencode({'q': query.strip(), 'count': limit})}"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key,
        }
        status, payload = self._read("GET", url, None, headers, effective_timeout)
        data = self._decode(status, payload)

        container = data.get("web")
        items = container.get("results") if isinstance(container, dict) else None
        if items is None:
            items = []
        if not isinstance(items, list):
            raise SearchProviderError("campo 'web.results' do Brave deve ser uma lista")

        results: list[SearchResult] = []
        discarded = 0
        for item in items:
            if not isinstance(item, dict):
                discarded += 1
                continue
            url_value = self._clean(item.get("url"), 2_000)
            if not url_value.startswith(("http://", "https://")):
                discarded += 1
                continue
            # Brave não devolve 'score' — derivamos do rank (1.0 → 0.0).
            rank = len(results) + 1
            score = max(0.0, 1.0 - (rank - 1) * 0.1)
            description = self._clean(
                item.get("description") or item.get("snippet"), MAX_SNIPPET_CHARS
            )
            try:
                result = SearchResult(
                    title=self._clean(item.get("title"), 500),
                    url=url_value,
                    content=description,
                    score=score,
                )
                result.validate()
            except ValueError as exc:
                logger.debug("resultado descartado: %s", exc)
                discarded += 1
                continue
            results.append(result)

        notes = [f"{discarded} resultado(s) descartado(s) por formato inválido"] if discarded else []
        response = WebSearchResponse(
            query=query.strip(),
            provider=self.name,
            results=tuple(results),
            truncated=len(results) >= limit,
            notes=tuple(notes),
        )
        response.validate()
        return response


def create_search_provider(
    *, provider: str | None = None, transport: Transport | None = None, **kwargs
) -> SearchProvider:
    """Instancia o provedor de busca configurado.

    Ordem de precedência: parâmetro ``provider`` > env ``LUMEN_SEARCH_PROVIDER``
    > ``tavily`` se houver chave Tavily > ``brave`` se houver chave Brave >
    erro explícito.

    Nunca faz fallback silencioso para um provedor sem chave: falha alto e
    claro para o bootstrap poder explicar ao usuário o que configurar.
    """
    explicit = (provider or _search_config("LUMEN_SEARCH_PROVIDER", _parse_env_file(ENV_FILE))).strip().lower()
    if explicit:
        if explicit == "tavily":
            return TavilySearchProvider.from_env(transport=transport, **kwargs)
        if explicit == "brave":
            return BraveSearchProvider.from_env(transport=transport, **kwargs)
        raise SearchUnavailableError(
            f"provedor de busca desconhecido: {explicit!r} (use 'tavily' ou 'brave')"
        )

    if _resolve_key(TAVILY_KEY_ENV_VARS):
        return TavilySearchProvider.from_env(transport=transport, **kwargs)
    if _resolve_key(BRAVE_KEY_ENV_VARS):
        return BraveSearchProvider.from_env(transport=transport, **kwargs)

    raise SearchUnavailableError(
        "nenhum provedor de busca configurado. Defina TAVILY_API_KEY "
        "(recomendado) ou BRAVE_API_KEY no ambiente/'.env'."
    )


__all__ = [
    "BRAVE_ENDPOINT",
    "BRAVE_KEY_ENV_VARS",
    "BraveSearchProvider",
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_TIMEOUT",
    "DEFAULT_TAVILY_DEPTH",
    "MAX_RESPONSE_BYTES",
    "MAX_RESULTS_CEILING",
    "MAX_TIMEOUT",
    "SearchProvider",
    "SearchProviderError",
    "SearchResponseTooLargeError",
    "SearchUnavailableError",
    "TAVILY_DEPTHS",
    "TAVILY_ENDPOINT",
    "TAVILY_KEY_ENV_VARS",
    "TavilySearchProvider",
    "Transport",
    "create_search_provider",
    "redact_secret",
]
