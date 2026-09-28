"""Testes offline das ferramentas e provedores Web."""
from __future__ import annotations

import json

import pytest

from app.security.permissions import PermissionDeniedError, PermissionLevel, PermissionManager
from app.tools.base import ToolRegistry
from app.web.provider import WebFetchResponse, WebSearchResponse, WebSource
from app.web.security import WebSecurityError, WebSecurityPolicy
from app.web.tools import WebFetchTool, WebSearchTool


class FakeSearch:
    def search(self, request):
        return WebSearchResponse(
            request.query,
            (WebSource("Fonte", "https://example.com", "trecho"),),
        )


class FakeFetch:
    def fetch(self, url):
        return WebFetchResponse(
            url, url, "Example", "text/html", "conteúdo público", False
        )


def test_web_tools_require_explicit_permission():
    permissions = PermissionManager()
    registry = ToolRegistry(permissions)
    registry.register(WebSearchTool(provider=FakeSearch()))
    with pytest.raises(PermissionDeniedError):
        registry.execute("web_search", query="teste")


def test_web_search_returns_structured_sources():
    permissions = PermissionManager([PermissionLevel.CHAT, PermissionLevel.WEB_ACCESS])
    registry = ToolRegistry(permissions)
    registry.register(WebSearchTool(provider=FakeSearch()))
    result = json.loads(registry.execute("web_search", query="teste", max_results=1))
    assert result["ok"] is True
    assert result["data"]["sources"][0]["url"] == "https://example.com"


def test_web_fetch_returns_text_without_execution():
    permissions = PermissionManager([PermissionLevel.CHAT, PermissionLevel.WEB_ACCESS])
    registry = ToolRegistry(permissions)
    registry.register(WebFetchTool(provider=FakeFetch()))
    result = json.loads(registry.execute("web_fetch", url="https://example.com"))
    assert result["ok"] is True
    assert result["data"]["text"] == "conteúdo público"


@pytest.mark.parametrize(
    ("query", "max_results"),
    ((123, 5), ("teste", True), ("teste", 0), ("teste", 21)),
)
def test_web_search_invalid_input_returns_controlled_error(query, max_results):
    tool = WebSearchTool(provider=FakeSearch())
    result = tool.run(query=query, max_results=max_results)
    assert not result.ok
    assert result.error


def test_web_search_invalid_input_does_not_leak_query_to_audit():
    class Audit:
        def __init__(self):
            self.events = []

        def record(self, **kwargs):
            self.events.append(kwargs)

    audit = Audit()
    tool = WebSearchTool(provider=FakeSearch(), audit=audit)
    result = tool.run(query=123, max_results=5)
    assert not result.ok
    assert audit.events[0]["query_length"] is None
    assert "123" not in str(audit.events[0])


@pytest.mark.parametrize("url", (123, None, ""))
def test_web_fetch_invalid_input_returns_controlled_error(url):
    tool = WebFetchTool(provider=FakeFetch())
    result = tool.run(url=url)
    assert not result.ok
    assert result.error


def test_web_fetch_invalid_input_does_not_leak_url_to_audit():
    class Audit:
        def __init__(self):
            self.events = []

        def record(self, **kwargs):
            self.events.append(kwargs)

    audit = Audit()
    tool = WebFetchTool(provider=FakeFetch(), audit=audit)
    result = tool.run(url=123)
    assert not result.ok
    assert audit.events[0]["requested_path"] == "host:<invalid>"
    assert "123" not in str(audit.events[0])


def test_planner_url_validation_blocks_private_destinations():
    from app.planner.catalog import build_catalog, validate_task_tool

    catalog = build_catalog(include_terminal=False)
    assert "web_search" in catalog and "web_fetch" in catalog
    assert validate_task_tool("web_fetch", {"url": "http://127.0.0.1/"}, catalog)
    assert validate_task_tool("web_fetch", {"url": "file:///secret"}, catalog)


def test_security_special_ranges_stay_blocked_when_private_networks_allowed():
    policy = WebSecurityPolicy(allow_private_networks=True)
    with pytest.raises(WebSecurityError):
        policy.validate_url("http://127.0.0.1/", resolve_dns=False)
    with pytest.raises(WebSecurityError):
        policy.validate_url("http://169.254.169.254/", resolve_dns=False)


def test_fetch_tool_rejects_unsafe_url_before_provider():
    class ExplodingProvider:
        def fetch(self, url):
            raise AssertionError("provider não deveria ser chamado")

    tool = WebFetchTool(provider=ExplodingProvider())
    result = tool.run("http://127.0.0.1/")
    assert not result.ok
    assert "não permitido" in (result.error or "") or "local" in (result.error or "")
