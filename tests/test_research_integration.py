"""Integração da pesquisa web com o ToolsController (Fase 1).

Verifica o contrato fail-closed: por padrão a tool NÃO existe (nem no
registry, nem no catálogo do Planner); só aparece após ``enable_web_search``.
Habilitar não concede permissão — o gate ``READ`` continua valendo.
"""
from __future__ import annotations

import pytest

from app.research.client import SearchUnavailableError, TavilySearchProvider
from app.security.permissions import PermissionLevel, PermissionManager
from app.tools.control import ToolsController


def make_provider():
    import json

    body = json.dumps(
        {
            "results": [
                {
                    "title": "BP Inventory",
                    "url": "https://example.com/inventory",
                    "content": "Use UDataAsset.",
                    "score": 0.9,
                }
            ]
        }
    ).encode()

    def transport(method, url, payload, headers, timeout):
        return 200, body

    return TavilySearchProvider(api_key="tvly-x", transport=transport)


@pytest.fixture
def controller(tmp_path):
    return ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
    )


def test_web_search_is_absent_by_default_in_registry(controller):
    names = [t["name"] for t in controller.build_registry().list_tools()]
    assert "web_search" not in names


def test_web_search_is_absent_by_default_in_catalog(controller):
    assert "web_search" not in controller.planning_catalog()


def test_enable_web_search_registers_tool(controller):
    outcome = controller.enable_web_search(make_provider())

    assert outcome["enabled"] is True
    assert outcome["provider"] == "tavily"
    assert "web_search" in [t["name"] for t in controller.build_registry().list_tools()]


def test_enable_web_search_adds_to_planner_catalog(controller):
    controller.enable_web_search(make_provider())

    catalog = controller.planning_catalog()

    assert "web_search" in catalog
    param_names = [p["name"] for p in catalog["web_search"]["parameters"]]
    assert param_names == ["query", "max_results"]


def test_enabling_does_not_grant_read_permission(controller):
    """Habilitar a tool não pode ampliar a autoridade do usuário."""
    controller.enable_web_search(make_provider())

    registry = controller.build_registry()

    from app.security.permissions import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        registry.execute("web_search", query="q")


def test_web_search_executes_through_registry_after_read_granted(tmp_path):
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.READ)
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "w.json",
        audit_file=tmp_path / "a.jsonl",
    )
    controller.enable_web_search(make_provider())

    import json

    parsed = json.loads(
        controller.build_registry().execute("web_search", query="unreal inventory")
    )

    assert parsed["ok"] is True
    assert parsed["data"]["provider"] == "tavily"


def test_disable_web_search_restores_fail_closed(controller):
    controller.enable_web_search(make_provider())
    assert controller.web_search_enabled is True

    controller.disable_web_search()

    assert controller.web_search_enabled is False
    assert "web_search" not in controller.planning_catalog()
    assert "web_search" not in [t["name"] for t in controller.build_registry().list_tools()]


def test_enable_reports_missing_configuration_without_raising(controller, monkeypatch):
    for name in ("TAVILY_API_KEY", "LUMEN_TAVILY_API_KEY", "BRAVE_API_KEY",
                 "LUMEN_BRAVE_API_KEY", "LUMEN_SEARCH_PROVIDER"):
        monkeypatch.delenv(name, raising=False)

    outcome = controller.enable_web_search()

    assert outcome["enabled"] is False
    assert "TAVILY_API_KEY" in outcome["reason"]
    assert controller.web_search_enabled is False


def test_enable_returns_provider_name(controller):
    outcome = controller.enable_web_search(make_provider())
    assert outcome == {"enabled": True, "provider": "tavily", "reason": None}


def test_terminal_and_web_search_are_independent(tmp_path):
    """Habilitar pesquisa não habilita terminal — e vice-versa."""
    permissions = PermissionManager()
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "w.json",
        audit_file=tmp_path / "a.jsonl",
    )

    controller.enable_web_search(make_provider())
    catalog = controller.planning_catalog()

    assert "web_search" in catalog
    assert "run_command" not in catalog, "pesquisa web não pode habilitar o terminal"
