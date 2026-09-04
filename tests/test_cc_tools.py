"""CC-4: ferramenta ``cc_request_scope`` (solicitação de escopo/consentimento).

Cobre a tool em si (validação fail-closed, clamp de expiração, auditoria
metadata-only) e a integração: a tool só é registrada quando a permissão
COMPUTER_CONTROL foi explicitamente concedida (paridade com o gate
``include_computer_control`` do catálogo de planejamento).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.security.permissions import PermissionDeniedError, PermissionManager
from app.tools.base import ToolRegistry
from app.tools.computer_control import CcRequestScopeTool
from app.tools.control import ToolsController


def _tool(scopes: dict | None = None, audit: list | None = None) -> CcRequestScopeTool:
    class _Audit:
        def __init__(self) -> None:
            self.records: list[dict] = []

        def record(self, **kw) -> None:
            self.records.append(kw)

    audit_sink = _Audit()
    return CcRequestScopeTool(
        scopes=scopes if scopes is not None else {}, audit=audit_sink
    ), audit_sink


VALID = dict(
    app_name="Bloco",
    allowed_actions=["screenshot"],
    expires_in_s=60,
    max_actions_total=1,
    max_actions_per_minute=1,
)


# ------------------------------------------------------------------ tool
def test_request_scope_rejects_invalid_inputs():
    tool, _ = _tool()
    # sem target
    r = tool.run(**{k: v for k, v in VALID.items() if k != "app_name"})
    assert r.ok is False and r.error == "invalid_input"
    # ação fora do MVP (mouse_click) é rejeitada
    r = tool.run(**{**VALID, "allowed_actions": ["key_type"]})
    assert r.ok is False
    # expiração não-positiva
    r = tool.run(**{**VALID, "expires_in_s": 0})
    assert r.ok is False
    # limite não-positivo
    r = tool.run(**{**VALID, "max_actions_total": 0})
    assert r.ok is False


def test_request_scope_creates_valid_scope_with_clamp():
    scopes: dict = {}
    tool, audit = _tool(scopes)
    result = tool.run(**{**VALID, "expires_in_s": 99999, "max_actions_total": 10})
    assert result.ok is True
    data = result.data
    # clamp conservador de 3600s
    from datetime import datetime

    created = datetime.fromisoformat(data["created_at"])
    expires = datetime.fromisoformat(data["expires_at"])
    assert int((expires - created).total_seconds()) == 3600
    # scope registrado no dict injetado e consistente com os dados
    scope = scopes[data["scope_id"]]
    assert scope.allowed_actions and data["allowed_actions"] == ["screenshot"]
    # auditoria metadata-only: sucesso com scope_id, sem paths/conteúdo
    ok_records = [r for r in audit.records if r["success"]]
    assert ok_records and ok_records[0]["scope_id"] == data["scope_id"]
    assert all(r.get("requested_path") is None for r in audit.records)


# ------------------------------------------------------------- registry
def _controller(tmp_path: Path, granted: bool) -> ToolsController:
    permissions = PermissionManager()
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )
    if granted:
        controller.grant_computer_control()
    return controller


def test_cc_tool_not_registered_without_grant(tmp_path):
    controller = _controller(tmp_path, granted=False)
    registry = controller.build_registry()
    with pytest.raises(Exception):
        registry.get("cc_request_scope")


def test_cc_tool_registered_with_grant_and_gated_by_permission(tmp_path):
    # Sem grant: não registrada.
    controller = _controller(tmp_path, granted=False)
    catalog_no_grant = controller.planning_catalog()
    assert "cc_request_scope" not in catalog_no_grant

    # Com grant: registrada E visível no catálogo (paridade).
    controller.grant_computer_control()
    catalog = controller.planning_catalog()
    assert "cc_request_scope" in catalog

    registry = controller.build_registry()
    tool = registry.get("cc_request_scope")
    assert tool.name == "cc_request_scope"

    # Registry isolado sem permissão deve bloquear (gate do ToolRegistry).
    fresh_perms = PermissionManager()  # sem grant
    blocked = ToolRegistry(fresh_perms)
    blocked.register(CcRequestScopeTool(scopes={}, audit=None))
    with pytest.raises(PermissionDeniedError):
        blocked.execute("cc_request_scope", **VALID)


def test_cc_scope_created_via_registry_persists_in_controller_session(tmp_path):
    controller = _controller(tmp_path, granted=True)
    registry = controller.build_registry()
    out = json.loads(registry.execute("cc_request_scope", **VALID))
    assert out["ok"] is True
    scope_id = out["data"]["scope_id"]
    # o scope vive no dict de sessão do controller (compartilhado)
    assert scope_id in controller._cc_scopes
