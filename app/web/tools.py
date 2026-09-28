"""Ferramentas Web expostas à Lumen."""
from __future__ import annotations

from urllib.parse import urlsplit

from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult
from app.tools.filesystem import FilesystemAudit
from app.web.provider import (
    DuckDuckGoSearchProvider,
    StandardWebFetchProvider,
    WebProviderError,
    WebSearchRequest,
)
from app.web.security import WebSecurityPolicy


class WebSearchTool(StructuredTool):
    name = "web_search"
    description = "Pesquisa na Web e retorna fontes estruturadas."
    required_permission = PermissionLevel.WEB_ACCESS

    def __init__(self, policy=None, audit: FilesystemAudit | None = None, provider=None):
        self._policy = policy or WebSecurityPolicy()
        self._audit = audit
        self._provider = provider or DuckDuckGoSearchProvider(policy=self._policy)

    def run(self, query="", max_results=5):
        try:
            if not isinstance(query, str) or not query.strip():
                raise ValueError("query deve ser texto não vazio.")
            if not isinstance(max_results, int) or isinstance(max_results, bool):
                raise ValueError("max_results deve ser um inteiro.")
            if not 1 <= max_results <= 20:
                raise ValueError("max_results deve estar entre 1 e 20.")
            result = self._provider.search(
                WebSearchRequest(query=query, max_results=max_results)
            )
            data = {
                "query": result.query,
                "sources": [
                    {"title": s.title, "url": s.url, "snippet": s.snippet}
                    for s in result.sources
                ],
            }
            self._record(True, query, None)
            return ToolResult(True, data)
        except Exception as exc:
            self._record(False, query, str(exc))
            return ToolResult(False, error=str(exc))

    def _record(self, ok, query, error):
        if self._audit:
            query_length = len(query) if isinstance(query, str) else None
            self._audit.record(
                tool=self.name,
                operation="web_search",
                requested_path=None,
                success=ok,
                error=error,
                query_length=query_length,
            )


class WebResearchTool(StructuredTool):
    """Pesquisa e lê fontes públicas em uma única operação controlada.

    A composição fica dentro da camada Web para permitir que o Planner
    transforme uma pergunta de pesquisa em uma tarefa única, sem depender
    de indexação de listas no data-flow entre tools.
    """

    name = "web_research"
    description = (
        "Pesquisa na Web e lê as principais fontes públicas encontradas. "
        "Exige WEB_ACCESS."
    )
    required_permission = PermissionLevel.WEB_ACCESS

    def __init__(
        self,
        policy=None,
        audit: FilesystemAudit | None = None,
        search_provider=None,
        fetch_provider=None,
    ):
        self._policy = policy or WebSecurityPolicy()
        self._audit = audit
        self._search_provider = (
            search_provider
            or DuckDuckGoSearchProvider(policy=self._policy)
        )
        self._fetch_provider = (
            fetch_provider
            or StandardWebFetchProvider(policy=self._policy)
        )

    def run(self, query="", max_results=5, max_sources=3):
        try:
            if not isinstance(query, str) or not query.strip():
                raise ValueError("query deve ser texto não vazio.")
            if not isinstance(max_results, int) or isinstance(max_results, bool):
                raise ValueError("max_results deve ser um inteiro.")
            if not 1 <= max_results <= 20:
                raise ValueError("max_results deve estar entre 1 e 20.")
            if not isinstance(max_sources, int) or isinstance(max_sources, bool):
                raise ValueError("max_sources deve ser um inteiro.")
            if not 1 <= max_sources <= 5:
                raise ValueError("max_sources deve estar entre 1 e 5.")

            search = self._search_provider.search(
                WebSearchRequest(query=query, max_results=max_results)
            )
            sources = []
            for source in search.sources[:max_sources]:
                try:
                    self._policy.validate_url(source.url)
                    fetched = self._fetch_provider.fetch(source.url)
                    sources.append({
                        "title": source.title,
                        "url": source.url,
                        "snippet": source.snippet,
                        "final_url": fetched.final_url,
                        "content_type": fetched.content_type,
                        "text": fetched.text,
                        "truncated": fetched.truncated,
                    })
                except Exception as exc:
                    # Uma fonte indisponível não invalida as demais.
                    sources.append({
                        "title": source.title,
                        "url": source.url,
                        "snippet": source.snippet,
                        "fetch_error": str(exc),
                    })

            data = {
                "query": search.query,
                "sources": sources,
                "source_count": len(sources),
            }
            self._record(True, query, None, len(sources))
            return ToolResult(True, data)
        except Exception as exc:
            self._record(False, query, str(exc), 0)
            return ToolResult(False, error=str(exc))

    def _record(self, ok, query, error, source_count):
        if self._audit:
            self._audit.record(
                tool=self.name,
                operation="web_research",
                requested_path=None,
                success=ok,
                error=error,
                query_length=len(query) if isinstance(query, str) else None,
                source_count=source_count,
            )


class WebFetchTool(StructuredTool):
    name = "web_fetch"
    description = "Baixa uma página Web HTTP/HTTPS e extrai texto sem executar conteúdo."
    required_permission = PermissionLevel.WEB_ACCESS

    def __init__(self, policy=None, audit: FilesystemAudit | None = None, provider=None):
        self._policy = policy or WebSecurityPolicy()
        self._audit = audit
        self._provider = provider or StandardWebFetchProvider(policy=self._policy)

    def run(self, url=""):
        try:
            if not isinstance(url, str) or not url.strip():
                raise ValueError("url deve ser texto não vazio.")
            self._policy.validate_url(url)
            result = self._provider.fetch(url)
            data = {
                "url": result.url,
                "final_url": result.final_url,
                "title": result.title,
                "content_type": result.content_type,
                "text": result.text,
                "truncated": result.truncated,
            }
            self._record(True, url, None, result.final_url)
            return ToolResult(True, data)
        except Exception as exc:
            self._record(False, url, str(exc), None)
            return ToolResult(False, error=str(exc))

    def _record(self, ok, url, error, final_url):
        if self._audit:
            host = urlsplit(url).hostname if isinstance(url, str) else None
            final_host = (
                urlsplit(final_url).hostname
                if isinstance(final_url, str) and final_url
                else None
            )
            self._audit.record(
                tool=self.name,
                operation="web_fetch",
                requested_path=f"host:{host or '<invalid>'}",
                resolved_path=f"host:{final_host}" if final_host else None,
                success=ok,
                error=error,
            )
        return None
