"""Testes do Modo Autônomo da Lumen."""
from __future__ import annotations

from app.security.permissions import PermissionLevel, PermissionManager
from app.tools.control import ToolsController


def _controller(tmp_path):
    return ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
        toggles_file=tmp_path / "toggles.json",
    )


def test_autonomous_mode_grants_all_permissions_and_restores_previous_state(tmp_path):
    controller = _controller(tmp_path)
    before = controller._permissions.granted_levels()

    controller.enable_autonomous_mode()

    assert controller.autonomous_mode is True
    assert controller._permissions.granted_levels() == frozenset(PermissionLevel)

    controller.disable_autonomous_mode()

    assert controller.autonomous_mode is False
    assert controller._permissions.granted_levels() == before


def test_autonomous_mode_is_idempotent(tmp_path):
    controller = _controller(tmp_path)
    controller.enable_autonomous_mode()
    controller.enable_autonomous_mode()
    assert controller.autonomous_mode is True
    controller.disable_autonomous_mode()
    controller.disable_autonomous_mode()
    assert controller.autonomous_mode is False