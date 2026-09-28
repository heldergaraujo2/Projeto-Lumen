"""Ferramentas Web expostas à Lumen."""
from __future__ import annotations
from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult
from app.tools.filesystem import FilesystemAudit
from app.web.provider import DuckDuckGoSearchProvider, StandardWebFetchProvider, WebProviderError, WebSearchRequest
from app.web.security import WebSecurityPolicy

class WebSearchTool(StructuredTool):
    name="web_search"; description="Pesquisa na Web e retorna fontes estruturadas."; required_permission=PermissionLevel.WEB_ACCESS
    def __init__(self, policy=None, audit:FilesystemAudit|None=None, provider=None):
        self._policy=policy or WebSecurityPolicy(); self._audit=audit
        self._provider=provider or DuckDuckGoSearchProvider(policy=self._policy)
    def run(self, query="", max_results=5):
        try:
            result=self._provider.search(WebSearchRequest(query=query,max_results=max_results))
            data={"query":result.query,"sources":[{"title":s.title,"url":s.url,"snippet":s.snippet} for s in result.sources]}
            self._record(True,query, None)
            return ToolResult(True,data)
        except Exception as exc:
            self._record(False,query, str(exc))
            return ToolResult(False,error=str(exc))
    def _record(self,ok,query,error):
        if self._audit: self._audit.record(tool=self.name,operation="web_search",requested_path=query[:500],success=ok,error=error)

class WebFetchTool(StructuredTool):
    name="web_fetch"; description="Baixa uma página Web HTTP/HTTPS e extrai texto sem executar conteúdo."; required_permission=PermissionLevel.WEB_ACCESS
    def __init__(self, policy=None, audit:FilesystemAudit|None=None, provider=None):
        self._policy=policy or WebSecurityPolicy(); self._audit=audit
        self._provider=provider or StandardWebFetchProvider(policy=self._policy)
    def run(self, url=""):
        try:
            self._policy.validate_url(url)
            result=self._provider.fetch(url)
            data={"url":result.url,"final_url":result.final_url,"title":result.title,"content_type":result.content_type,"text":result.text,"truncated":result.truncated}
            self._record(True,url,None,result.final_url)
            return ToolResult(True,data)
        except Exception as exc:
            self._record(False,url,str(exc),None)
            return ToolResult(False,error=str(exc))
    def _record(self,ok,url,error,final_url):
        if self._audit: self._audit.record(tool=self.name,operation="web_fetch",requested_path=url[:1000],resolved_path=final_url,success=ok,error=error)
