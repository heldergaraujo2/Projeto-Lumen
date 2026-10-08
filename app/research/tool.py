"""``WebSearchTool`` — a tool de pesquisa web exposta ao agente (Fase 1).

Segue o padrão de :mod:`app.tools.protocol` e :class:`app.tools.base.StructuredTool`:
declara ``name``, ``description`` e ``required_permission``, e devolve
``ToolResult`` estruturado.

**Permissão ``READ``.** Pesquisar na web é leitura de fonte pública — o
mesmo nível de confiança que ler um arquivo. Não exige ``TERMINAL`` nem
``COMPUTER_CONTROL``.

``ToolResult.data`` (schema estável)::

    operation, provider, query, result_count, truncated, answer,
    results[{title, url, content, score}], notes[]

A chave de API nunca entra em ``data`` nem em ``error``.
"""
from __future__ import annotations

import logging
from typing import Any

from app.research.client import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_TIMEOUT,
    SearchProvider,
    SearchProviderError,
    create_search_provider,
    redact_secret,
)
from app.security.permissions import PermissionLevel, PermissionManager
from app.tools.base import StructuredTool, ToolRegistry, ToolResult

logger = logging.getLogger("lumen.research.tool")

WEB_SEARCH_TOOL_NAME = "web_search"
OPERATION_WEB_SEARCH = "web_search"


class WebSearchTool(StructuredTool):
    """Pesquisa na web e devolve resultados estruturados com fontes citáveis."""

    name = WEB_SEARCH_TOOL_NAME
    description = (
        "Pesquisa na web e devolve resultados com título, URL e trecho. "
        "Use antes de planejar uma implementação para descobrir como fazer."
    )
    required_permission = PermissionLevel.READ

    def __init__(
        self,
        provider: SearchProvider | None = None,
        *,
        default_max_results: int = DEFAULT_MAX_RESULTS,
        default_timeout: float = DEFAULT_TIMEOUT,
        provider_factory=create_search_provider,
    ) -> None:
        self._provider = provider
        self._provider_factory = provider_factory
        self._default_max_results = default_max_results
        self._default_timeout = default_timeout

    # ---------------------------------------------------------------- API
    def _get_provider(self) -> SearchProvider:
        """Resolve o provedor tardiamente — só quando a tool é executada.

        Assim, a construção do registry não exige chave de API e o erro
        aparece no momento do uso, com mensagem acionável.
        """
        if self._provider is None:
            self._provider = self._provider_factory()
        return self._provider

    def run(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query")
        if not isinstance(query, str) or not query.strip():
            return ToolResult(
                ok=False,
                data={"operation": OPERATION_WEB_SEARCH},
                error="Parâmetro 'query' é obrigatório (texto não vazio).",
            )

        max_results = kwargs.get("max_results", self._default_max_results)
        timeout = kwargs.get("timeout", self._default_timeout)

        try:
            provider = self._get_provider()
        except SearchProviderError as exc:
            return ToolResult(
                ok=False,
                data={"operation": OPERATION_WEB_SEARCH, "query": query.strip()},
                error=redact_secret(str(exc), None),
            )

        try:
            response = provider.search(
                query.strip(), max_results=max_results, timeout=timeout
            )
        except SearchProviderError as exc:
            # `exc` já passou por redação na origem; reforçamos aqui.
            return ToolResult(
                ok=False,
                data={"operation": OPERATION_WEB_SEARCH, "query": query.strip()},
                error=redact_secret(str(exc), None),
            )
        except (ValueError, TypeError) as exc:
            return ToolResult(
                ok=False,
                data={"operation": OPERATION_WEB_SEARCH, "query": query.strip()},
                error=f"parâmetros inválidos: {exc}",
            )

        data = response.to_dict()
        data["operation"] = OPERATION_WEB_SEARCH
        logger.info(
            "web_search: provider=%s resultados=%d",
            response.provider,
            len(response.results),
        )
        return ToolResult(ok=True, data=data)


def build_research_registry(
    permissions: PermissionManager | None = None,
    *,
    provider: SearchProvider | None = None,
) -> ToolRegistry:
    """Registry com a tool de pesquisa registrada (explícito, sem efeito no startup)."""
    registry = ToolRegistry(permissions)
    registry.register(WebSearchTool(provider))
    return registry


__all__ = [
    "OPERATION_WEB_SEARCH",
    "WEB_SEARCH_TOOL_NAME",
    "WebSearchTool",
    "build_research_registry",
]
