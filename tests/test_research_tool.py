"""Testes da ``WebSearchTool`` (Fase 1) — porteio de permissão e contrato.

Verifica que a tool respeita a coleira do LUMEN: sem permissão ``READ``
nada roda, o resultado é estruturado, e a chave de API nunca vaza.
"""
from __future__ import annotations

import json

import pytest

from app.research.client import SearchUnavailableError, TavilySearchProvider
from app.research.tool import (
    OPERATION_WEB_SEARCH,
    WEB_SEARCH_TOOL_NAME,
    WebSearchTool,
    build_research_registry,
)
from app.security.permissions import (
    PermissionDeniedError,
    PermissionLevel,
    PermissionManager,
)
from app.tools.base import ToolRegistry

SAMPLE = {
    "title": "Inventory System Tutorial",
    "url": "https://dev.epicgames.com/community/learning/inventory",
    "content": "Component-based inventory with UDataAsset.",
    "score": 0.91,
}


def make_provider(payload_results=(SAMPLE,), **kwargs):
    import json as _json

    body = _json.dumps({"results": list(payload_results)}).encode("utf-8")

    def transport(method, url, body_bytes, headers, timeout):
        return 200, body

    return TavilySearchProvider(api_key="tvly-SECRET", transport=transport, **kwargs)


# ----------------------------------------------------------------- metadata
def test_tool_declares_protocol_metadata():
    assert WebSearchTool.name == WEB_SEARCH_TOOL_NAME == "web_search"
    assert WebSearchTool.description.strip()
    assert WebSearchTool.required_permission is PermissionLevel.READ


def test_tool_name_matches_protocol_expectations():
    """O nome precisa ser snake_case estável — é o que o LLM emite."""
    assert WEB_SEARCH_TOOL_NAME.islower()
    assert " " not in WEB_SEARCH_TOOL_NAME


# ---------------------------------------------------------------- execution
def test_run_returns_structured_success():
    tool = WebSearchTool(make_provider())

    result = tool.run(query="unreal inventory system")

    assert result.ok is True
    assert result.error is None
    data = result.data
    assert data["operation"] == OPERATION_WEB_SEARCH
    assert data["provider"] == "tavily"
    assert data["query"] == "unreal inventory system"
    assert data["result_count"] == 1
    assert data["results"][0]["url"] == SAMPLE["url"]


def test_execute_serialises_to_json_for_registry():
    tool = WebSearchTool(make_provider())

    parsed = json.loads(tool.execute(query="q"))

    assert parsed["ok"] is True
    assert parsed["data"]["result_count"] == 1


def test_missing_query_is_a_structured_failure_not_an_exception():
    tool = WebSearchTool(make_provider())

    result = tool.run()

    assert result.ok is False
    assert "query" in (result.error or "")


def test_blank_query_is_rejected():
    tool = WebSearchTool(make_provider())
    assert tool.run(query="   ").ok is False


def test_provider_error_becomes_structured_failure():
    def broken(method, url, body, headers, timeout):
        return 500, b'{"detail":"boom tvly-SECRET"}'

    tool = WebSearchTool(TavilySearchProvider(api_key="tvly-SECRET", transport=broken))

    result = tool.run(query="q")

    assert result.ok is False
    assert "500" in (result.error or "")
    assert "tvly-SECRET" not in (result.error or ""), "a chave vazou na mensagem de erro"


def test_missing_api_key_is_reported_actionably():
    tool = WebSearchTool(provider_factory=lambda: (_ for _ in ()).throw(
        SearchUnavailableError("defina TAVILY_API_KEY")
    ))

    result = tool.run(query="q")

    assert result.ok is False
    assert "TAVILY_API_KEY" in (result.error or "")


def test_provider_is_resolved_lazily_so_registry_can_be_built_without_key():
    """Construir o registry não pode exigir chave de API."""
    calls = []

    def factory():
        calls.append(1)
        return make_provider()

    tool = WebSearchTool(provider_factory=factory)
    assert calls == [], "o provedor não deve ser resolvido na construção"

    tool.run(query="q")
    assert len(calls) == 1


def test_invalid_max_results_is_reported_as_failure():
    tool = WebSearchTool(make_provider())
    result = tool.run(query="q", max_results=0)
    assert result.ok is False
    assert "max_results" in (result.error or "")


# --------------------------------------------------------------- permission
def test_registry_blocks_execution_without_read_permission():
    permissions = PermissionManager()  # só CHAT por padrão
    registry = build_research_registry(permissions, provider=make_provider())

    with pytest.raises(PermissionDeniedError):
        registry.execute("web_search", query="q")


def test_registry_executes_after_read_is_granted():
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.READ)
    registry = build_research_registry(permissions, provider=make_provider())

    parsed = json.loads(registry.execute("web_search", query="inventory"))

    assert parsed["ok"] is True


def test_registry_lists_the_tool_with_read_permission():
    registry = build_research_registry(provider=make_provider())
    listed = registry.list_tools()

    assert len(listed) == 1
    assert listed[0]["name"] == "web_search"
    assert listed[0]["required_permission"] == "READ"


def test_build_registry_does_not_register_anything_else():
    registry = build_research_registry(provider=make_provider())
    assert [t["name"] for t in registry.list_tools()] == ["web_search"]


def test_registry_without_permissions_does_not_gate():
    """Sem PermissionManager o registry é inerte — comportamento herdado da 0.5."""
    registry = ToolRegistry(None)
    registry.register(WebSearchTool(make_provider()))
    assert json.loads(registry.execute("web_search", query="q"))["ok"] is True


# ------------------------------------------------------------------ secrets
def test_api_key_never_appears_in_tool_data():
    tool = WebSearchTool(make_provider())

    result = tool.run(query="q")
    serialised = json.dumps(result.data)

    assert "tvly-SECRET" not in serialised
