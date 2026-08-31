"""Testes da tela 🛡 Ferramentas e Segurança (UI com toolkit falso).

A lógica vive no ToolsController (testado à parte); aqui se valida a
camada visual: renderização clara (o quê/onde/ferramenta/permissão/
aprovação), ações de workspace/permissão e o fluxo APROVAR/RECUSAR com
efeitos REAIS no filesystem temporário.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app.ui.main_window as main_window_module
import app.ui.tools_dialog as tools_dialog_module
from app.ai.mock import MockProvider
from app.core.agent import Agent
from app.memory.store import MemoryStore
from app.planner.models import Plan, PlanStatus, PlannedTask
from app.security.permissions import PermissionManager
from app.tools.control import ToolsController
from tests.fake_tk import FakeMessagebox, FakeRoot, FakeTkModule


@pytest.fixture(autouse=True)
def fake_tk(monkeypatch):
    fake = FakeTkModule()
    monkeypatch.setattr(main_window_module, "tk", fake)
    monkeypatch.setattr(tools_dialog_module, "tk", fake)
    monkeypatch.setattr(tools_dialog_module, "messagebox", FakeMessagebox(True))
    return fake


def make_controller(tmp_path: Path, permissions: PermissionManager | None = None):
    return ToolsController(
        permissions or PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
    )


def armed(task_id: str, tool: str, parameters: dict) -> PlannedTask:
    return PlannedTask(id=task_id, description=f"executar {tool}",
                       order=1, tool=tool, parameters=parameters)


def ready(*tasks: PlannedTask) -> Plan:
    return Plan(id="PLN-77", objective="objetivo", status=PlanStatus.READY,
                tasks=tasks)


# ------------------------------------------------------------------ básicos
def test_dialog_opens_with_empty_state(tmp_path):
    controller = make_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    assert "Nenhuma operação aguardando aprovação" in dialog.pending_label.cget("text")
    assert dialog.approve_button.cget("state") == "disabled"
    assert dialog.ws_rows == []
    assert dialog.audit_text.text.startswith("Nenhuma operação registrada")


def test_main_window_has_tools_button_and_opens_dialog(tmp_path):
    agent = Agent(MockProvider(), MemoryStore(tmp_path / "c.json"),
                  permissions=PermissionManager())
    controller = make_controller(tmp_path, agent.permissions)
    window = main_window_module.LumenWindow(FakeRoot(), agent,
                                            tools_controller=controller)
    assert "Ferramentas" in window.tools_button.cget("text")
    window._open_tools()  # não deve explodir; diálogo é construído real


def test_main_window_tools_button_disabled_without_controller(tmp_path):
    agent = Agent(MockProvider(), MemoryStore(tmp_path / "c.json"))
    window = main_window_module.LumenWindow(FakeRoot(), agent)
    assert window.tools_button.cget("state") == "disabled"


# --------------------------------------------------------------- workspaces
def test_dialog_adds_workspace_with_flags_and_persists(tmp_path):
    ws = tmp_path / "projeto"
    ws.mkdir()
    controller = make_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)

    dialog.path_entry.insert(0, str(ws))
    dialog._toggle_delete()  # exclusão implica escrita
    assert dialog.write_toggle.cget("text") == "Escrita: SIM"
    dialog._add_workspace()

    assert len(dialog.ws_rows) == 1
    assert dialog.ws_rows[0]["root"] == str(ws.resolve())
    assert dialog.ws_rows[0]["mode"] == "escrita + exclusão"
    assert controller.list_workspaces()[0]["allow_delete"] is True
    assert "🟢" in dialog.status_label.cget("text")
    assert dialog.path_entry.get() == ""  # campo limpo


def test_dialog_rejects_invalid_workspace_with_friendly_status(tmp_path):
    controller = make_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    dialog.path_entry.insert(0, "caminho/relativo")
    dialog._add_workspace()
    assert "🔴" in dialog.status_label.cget("text")
    assert "relativo" in dialog.status_label.cget("text")
    assert dialog.ws_rows == []


def test_dialog_removes_workspace_with_confirmation(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws))
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    assert len(dialog.ws_rows) == 1
    dialog.ws_rows[0]["remove_button"].invoke()
    assert dialog.ws_rows == []
    assert controller.list_workspaces() == []


# --------------------------------------------------------------- permissões
def test_dialog_permissions_render_and_toggle(tmp_path):
    controller = make_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    assert "● concedida" in dialog.perm_rows["CHAT"]["status"].cget("text")
    assert "○ não concedida" in dialog.perm_rows["WRITE"]["status"].cget("text")
    assert dialog.perm_rows["READ"]["action"].cget("text") == "Conceder"

    dialog._toggle_permission("READ")
    assert "● concedida" in dialog.perm_rows["READ"]["status"].cget("text")
    assert dialog.perm_rows["READ"]["action"].cget("text") == "Revogar"
    dialog._toggle_permission("READ")  # revoga de volta
    assert "○ não concedida" in dialog.perm_rows["READ"]["status"].cget("text")


def test_dialog_delete_row_reflects_workspace_opt_in(tmp_path):
    ws = tmp_path / "p"
    ws.mkdir()
    controller = make_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    assert "○ inativa" in dialog.delete_status.cget("text")
    controller.add_workspace(str(ws), writable=True, allow_delete=True)
    dialog.refresh()
    assert "● ativa" in dialog.delete_status.cget("text")


# ---------------------------------------------------------------- aprovação
def _paused_dialog(tmp_path, tool="create_file", parameters=None):
    ws = tmp_path / "docs"
    ws.mkdir()
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("WRITE")
    controller.grant_permission("READ")
    task = armed("T1", tool, parameters or {"path": "novo.txt", "content": "dados"})
    controller.run_plan(ready(task))
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    dialog.refresh()
    return dialog, controller, ws


def test_dialog_pending_shows_what_where_tool_operation_permission(tmp_path):
    dialog, _controller, ws = _paused_dialog(tmp_path)
    text = dialog.pending_label.cget("text")
    assert "AGUARDANDO APROVAÇÃO" in text
    assert "nada é executado antes da sua decisão" in text
    assert "O que: executar create_file" in text
    assert "Ferramenta: create_file" in text
    assert "Operação: escrita" in text
    assert "Permissão: WRITE" in text
    assert f"Onde: novo.txt → {ws.resolve() / 'novo.txt'}" in text
    assert f"workspace: {ws.resolve()}" in text
    assert dialog.approve_button.cget("state") == "normal"
    assert dialog.refuse_button.cget("state") == "normal"


def test_dialog_refusal_blocks_execution_for_real(tmp_path):
    dialog, _controller, ws = _paused_dialog(tmp_path)
    dialog._refuse()
    assert not (ws / "novo.txt").exists()  # NADA executado
    assert "NÃO foi executada" in dialog.status_label.cget("text")
    assert dialog.approve_button.cget("state") == "disabled"


def test_dialog_approval_executes_and_updates_audit(tmp_path):
    dialog, _controller, ws = _paused_dialog(tmp_path)
    dialog._approve()
    assert (ws / "novo.txt").read_text(encoding="utf-8") == "dados"
    assert "Aprovada e executada" in dialog.status_label.cget("text")
    assert "create_file" in dialog.audit_text.text
    assert "dados" not in dialog.audit_text.text  # sem conteúdo na auditoria


# ---------------------------------------------------------------- auditoria
def test_dialog_audit_lists_records_with_context(tmp_path):
    dialog, controller, ws = _paused_dialog(tmp_path)
    dialog._approve()
    dialog._refresh_audit()
    body = dialog.audit_text.text
    assert "create_file" in body and "write" in body
    assert f"{ws.resolve() / 'novo.txt'}" in body
    assert "T1/PLN-77" in body  # tarefa/plano relacionados
    assert "novo.txt" in body


def test_dialog_close(tmp_path):
    controller = make_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    dialog._close()
    assert dialog.top.destroyed


# --------------------------------------------- terminal (0.6.x) — seção nova
def make_terminal_controller(tmp_path: Path, permissions=None) -> ToolsController:
    return ToolsController(
        permissions or PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )


def test_dialog_terminal_section_empty_state(tmp_path):
    controller = make_terminal_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    assert "não concedida" in dialog.terminal_status_label.cget("text")
    assert dialog.terminal_toggle.cget("text") == "Conceder"
    assert "Terminal desabilitado" in dialog._empty_term_label.cget("text")
    assert dialog.term_rows == []


def test_dialog_toggle_terminal_grants_and_revokes(tmp_path):
    controller = make_terminal_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    dialog.terminal_toggle.invoke()
    assert controller.terminal_status()["permission_granted"] is True
    assert dialog.terminal_toggle.cget("text") == "Revogar"
    dialog.terminal_toggle.invoke()
    assert controller.terminal_status()["permission_granted"] is False
    operations = [r["operation"] for r in controller.audit_records()]
    assert "terminal_grant" in operations and "terminal_revoke" in operations


def test_dialog_adds_command_to_allowlist_and_persists(tmp_path):
    controller = make_terminal_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    dialog.cmd_entry.insert(0, "git")
    dialog.add_cmd_button.invoke()
    rows = controller.list_allowed_commands()
    assert [r["name"] for r in rows] == ["git"]
    assert rows[0]["requires_approval"] is True  # toggle default: SIM
    assert dialog.term_rows[0]["name"] == "git"
    assert dialog.cmd_entry.get() == ""  # limpo após adicionar
    data = json.loads((tmp_path / "terminal.json").read_text(encoding="utf-8"))
    assert [c["name"] for c in data["commands"]] == ["git"]


def test_dialog_adds_command_with_approval_toggle_off(tmp_path):
    controller = make_terminal_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    dialog.cmd_approval_toggle.invoke()  # Aprovação: NÃO
    dialog.cmd_entry.insert(0, "dir")
    dialog.add_cmd_button.invoke()
    rows = controller.list_allowed_commands()
    assert rows[0]["requires_approval"] is False


def test_dialog_rejects_denylisted_command_with_status(tmp_path):
    controller = make_terminal_controller(tmp_path)
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    dialog.cmd_entry.insert(0, "powershell")
    dialog.add_cmd_button.invoke()
    assert "🔴" in dialog.status_label.cget("text")
    assert controller.list_allowed_commands() == []
    assert dialog.term_rows == []


def test_dialog_removes_command_from_allowlist(tmp_path):
    controller = make_terminal_controller(tmp_path)
    controller.allow_command("git")
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    assert dialog.term_rows[0]["name"] == "git"
    dialog.term_rows[0]["remove_button"].invoke()  # FakeMessagebox(True)
    assert controller.list_allowed_commands() == []
    data = json.loads((tmp_path / "terminal.json").read_text(encoding="utf-8"))
    assert data["commands"] == []


def test_dialog_disable_terminal_empties_allowlist(tmp_path):
    controller = make_terminal_controller(tmp_path)
    controller.allow_command("git")
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    dialog.disable_terminal_button.invoke()  # confirmação SIM
    assert controller.terminal_status()["enabled"] is False
    assert dialog.term_rows == []


def test_dialog_pending_card_shows_command_args_dir_timeout(tmp_path):
    ws = tmp_path / "docs"
    ws.mkdir()
    controller = make_terminal_controller(tmp_path)
    controller.add_workspace(str(ws))
    controller.allow_command("mkdir")
    controller.grant_terminal()
    controller.run_plan(ready(armed("T1", "run_command",
                                    {"command": "mkdir", "args": ["dados"],
                                     "cwd": "."})))
    dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
    text = dialog.pending_label.cget("text")
    for fragment in ("Comando: mkdir", "Argumentos: dados",
                     "Diretório de trabalho:", "Timeout: 10s",
                     "Permissão: TERMINAL", "Ferramenta: run_command"):
        assert fragment in text, fragment


def test_dialog_uses_only_controller_facade():
    """A UI não importa filesystem/terminal — somente a fachada."""
    import inspect
    source = inspect.getsource(tools_dialog_module)
    for forbidden in ("app.tools.filesystem", "app.tools.terminal",
                      "subprocess", "TerminalPolicy", "RunCommandTool"):
        assert forbidden not in source, forbidden
    assert "app.tools.control" in source
