"""Camada de pesquisa web da Lumen (Fase 1).

Fornece uma tool de busca na web que o agente pode chamar para **pesquisar
como implementar** algo antes de planejar (objetivo 2 do projeto).

Provedores suportados (via ``urllib`` da stdlib — nenhuma dependência nova):

- **Tavily** (``TAVILY_API_KEY``) — recomendado; devolve trechos já extraídos;
- **Brave Search** (``BRAVE_API_KEY``) — alternativa.

Segurança (mesma coleira das demais tools):

- a busca exige a permissão ``READ`` — nunca roda sem concessão explícita;
- a chave de API **nunca** aparece em log, mensagem de erro ou no
  ``ToolResult`` (redação aplicada antes de qualquer retorno);
- corpo de resposta tem teto de bytes (anti-DoS);
- ``timeout`` é obrigatório e sempre finito;
- nada é escrito em disco; nenhum subprocesso é iniciado.
"""
from __future__ import annotations

from app.research.client import (
    DEFAULT_MAX_RESULTS,
    MAX_RESULTS_CEILING,
    BraveSearchProvider,
    SearchProvider,
    SearchProviderError,
    SearchResponseTooLargeError,
    SearchUnavailableError,
    TavilySearchProvider,
    create_search_provider,
    redact_secret,
)
from app.research.models import SearchResult, WebSearchResponse
from app.research.tool import WEB_SEARCH_TOOL_NAME, WebSearchTool, build_research_registry

__all__ = [
    "BraveSearchProvider",
    "DEFAULT_MAX_RESULTS",
    "MAX_RESULTS_CEILING",
    "SearchProvider",
    "SearchProviderError",
    "SearchResponseTooLargeError",
    "SearchResult",
    "SearchUnavailableError",
    "TavilySearchProvider",
    "WEB_SEARCH_TOOL_NAME",
    "WebSearchResponse",
    "WebSearchTool",
    "build_research_registry",
    "create_search_provider",
    "redact_secret",
]
