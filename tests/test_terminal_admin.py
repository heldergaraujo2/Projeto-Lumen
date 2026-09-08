"""Testes da camada de administração de terminal (0.6.x).

Concessão/revogação explícita de TERMINAL pela fachada
``ToolsController``, gerenciamento + persistência da allowlist
(``data/terminal.json``), auditoria das ações administrativas e as
garantias anti-concessão-silenciosa. Maioria cross-platform (nada
executa — checkpoints e gates acontecem ANTES da execução); os casos
que executam comandos de verdade pulam no Windows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.planner.models import Plan, PlanStatus, PlannedTask
from app.security.permissions import PermissionManager
from app.tools.control import ToolsControlError, ToolsController

pytestmark_execution = pytest.mark.skipif(
    sys.platform == "win32", reason="usa comandos POSIX do sandbox"
)


def make_controller(tmp_path: Path, permissions=None, *, persist=True):
    return ToolsController(
        permissions or PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json" if persist else None,
    )


def cmd_task(task_id: str, command: str, args: list | None = None,
             cwd: str = ".") -> PlannedTask:
    return PlannedTask(
        id=task_id, description=f"executar {command}", order=1,
        tool="run_command",
        parameters={"command": command, "args": args or [], "cwd": cwd},
    )


def plan_of(*tasks: PlannedTask) -> Plan:
    return Plan(id="PLN-61", objective="admin terminal",
                status=PlanStatus.READY, tasks=tasks)


# ----------------------------------------------------- concessão de TERMINAL
def test_permission_status_includes_terminal_row(tmp_path):
    controller = make_controller(tmp_path)
    rows = {row["level"]: row for row in controller.permission_status()}
    assert rows["TERMINAL"]["kind"] == "permission"
    assert rows["TERMINAL"]["granted"] is False  # nunca concedida por padrão
    assert "allowlist" in rows["TERMINAL"]["description"]


def test_generic_grant_permission_still_rejects_terminal(tmp_path):
    """O caminho genérico NÃO concede TERMINAL (sem concessão silenciosa)."""
    controller = make_controller(tmp_path)
    with pytest.raises(ToolsControlError):
        controller.grant_permission("TERMINAL")
    with pytest.raises(ToolsControlError):
        controller.revoke_permission("TERMINAL")
    assert not controller.terminal_status()["permission_granted"]


def test_grant_and_revoke_terminal_explicit(tmp_path):
    permissions = PermissionManager()
    controller = make_controller(tmp_path, permissions)
    controller.grant_terminal()
    assert permissions.is_granted("TERMINAL")
    assert controller.terminal_status()["permission_granted"]
    controller.revoke_terminal()
    assert not permissions.is_granted("TERMINAL")


def test_generic_grant_permission_still_rejects_computer_control(tmp_path):
    """O caminho genérico NÃO concede COMPUTER_CONTROL (sem concessão
    silenciosa) — mesmo com o caminho dedicado existindo."""
    permissions = PermissionManager()
    controller = make_controller(tmp_path, permissions)
    with pytest.raises(ToolsControlError):
        controller.grant_permission("COMPUTER_CONTROL")
    with pytest.raises(ToolsControlError):
        controller.revoke_permission("COMPUTER_CONTROL")
    assert not permissions.is_granted("COMPUTER_CONTROL")


def test_grant_and_revoke_computer_control_explicit(tmp_path):
    permissions = PermissionManager()
    controller = make_controller(tmp_path, permissions)
    controller.grant_computer_control()
    assert permissions.is_granted("COMPUTER_CONTROL")
    controller.revoke_computer_control()
    assert not permissions.is_granted("COMPUTER_CONTROL")


def test_computer_control_grant_toggles_planning_catalog(tmp_path, monkeypatch):
    """CC-3: o planner só vê ferramentas CC quando a permissão foi
    explicitamente concedida (paridade com include_terminal)."""
    captured = {}

    def fake_build_catalog(*, include_terminal, include_computer_control=False):
        captured["include_terminal"] = include_terminal
        captured["include_computer_control"] = include_computer_control
        return {"_witness": include_computer_control}

    monkeypatch.setattr(
        "app.planner.catalog.build_catalog", fake_build_catalog
    )

    controller = make_controller(tmp_path)
    catalog = controller.planning_catalog()
    assert captured["include_computer_control"] is False
    assert catalog == {"_witness": False}

    controller.grant_computer_control()
    catalog = controller.planning_catalog()
    assert captured["include_computer_control"] is True
    assert catalog == {"_witness": True}

    controller.revoke_computer_control()
    controller.planning_catalog()
    assert captured["include_computer_control"] is False


def test_computer_control_grant_and_revoke_are_audited(tmp_path):
    controller = make_controller(tmp_path)
    controller.grant_computer_control()
    controller.revoke_computer_control()
    records = controller.audit_records()
    operations = [r["operation"] for r in records]
    assert "cc_grant" in operations and "cc_revoke" in operations
    admin = [r for r in records if r["tool"] == "cc_admin"]
    assert {r["operation"] for r in admin} == {"cc_grant", "cc_revoke"}
    assert all(r["success"] for r in admin)
    # as ações de terminal continuam com tool próprio (sem vazamento)
    controller.grant_terminal()
    term = [r for r in controller.audit_records()
            if r["operation"] == "terminal_grant"]
    assert term and all(r["tool"] == "terminal_admin" for r in term)


def test_terminal_grant_and_revoke_are_audited(tmp_path):
    controller = make_controller(tmp_path)
    controller.grant_terminal()
    controller.revoke_terminal()
    records = controller.audit_records()
    operations = [r["operation"] for r in records]
    assert "terminal_grant" in operations and "terminal_revoke" in operations
    admin = [r for r in records if r["tool"] == "terminal_admin"]
    assert all(r["success"] for r in admin)


# ------------------------------------------------------------ allowlist UI
def test_allow_command_persists_and_lists(tmp_path):
    controller = make_controller(tmp_path)
    controller.enable_terminal([])
    controller.allow_command("git", requires_approval=False)
    controller.allow_command("dir")
    rows = controller.list_allowed_commands()
    assert [r["name"] for r in rows] == ["git", "dir"]
    assert rows[0]["requires_approval"] is False
    assert rows[1]["requires_approval"] is True  # default: aprovação obrigatória
    assert rows[0]["timeout_s"] == 10  # default resolvido
    data = json.loads((tmp_path / "terminal.json").read_text(encoding="utf-8"))
    assert [c["name"] for c in data["commands"]] == ["git", "dir"]
    assert data["defaults"]["default_timeout_s"] == 10


def test_remove_allowed_command_persists_and_errors(tmp_path):
    controller = make_controller(tmp_path)
    controller.enable_terminal(["git", "dir"])
    controller.remove_allowed_command("GIT")  # normalização na remoção
    assert controller.list_allowed_commands()[0]["name"] == "dir"
    data = json.loads((tmp_path / "terminal.json").read_text(encoding="utf-8"))
    assert [c["name"] for c in data["commands"]] == ["dir"]
    with pytest.raises(ToolsControlError):
        controller.remove_allowed_command("git")
    with pytest.raises(ToolsControlError):
        controller.remove_allowed_command("sh")  # denylist nem existe aqui


def test_denylisted_command_rejected_and_not_persisted(tmp_path):
    controller = make_controller(tmp_path)
    controller.enable_terminal([])
    with pytest.raises(ToolsControlError):
        controller.allow_command("powershell")
    with pytest.raises(ToolsControlError):
        controller.allow_command("python.exe")
    assert controller.list_allowed_commands() == []
    assert not (tmp_path / "terminal.json").exists() or json.loads(
        (tmp_path / "terminal.json").read_text(encoding="utf-8")
    )["commands"] == []


def test_first_allow_command_bootstraps_terminal(tmp_path):
    """Cadastrar o 1º comando habilita a allowlist (explícito; sem permissão)."""
    controller = make_controller(tmp_path)
    controller.allow_command("git")  # sem enable_terminal prévio
    status = controller.terminal_status()
    assert status["enabled"] is True and status["allowed_count"] == 1
    assert status["permission_granted"] is False  # habilitar ≠ conceder
    operations = [r["operation"] for r in controller.audit_records()]
    assert "terminal_enable" in operations and "allowlist_add" in operations


def test_remove_without_terminal_is_error(tmp_path):
    controller = make_controller(tmp_path)
    with pytest.raises(ToolsControlError):
        controller.remove_allowed_command("git")


def test_terminal_status_reflects_state(tmp_path):
    controller = make_controller(tmp_path)
    status = controller.terminal_status()
    assert status["enabled"] is False and status["allowed_count"] == 0
    controller.enable_terminal(["git"])
    status = controller.terminal_status()
    assert status["enabled"] is True and status["allowed_count"] == 1
    assert status["default_timeout_s"] == 10 and status["max_timeout_s"] == 60
    assert status["allow_operators"] is False


def test_disable_terminal_empties_persisted_allowlist(tmp_path):
    controller = make_controller(tmp_path)
    controller.enable_terminal(["git"])
    controller.disable_terminal()
    assert controller.terminal_status()["enabled"] is False
    data = json.loads((tmp_path / "terminal.json").read_text(encoding="utf-8"))
    assert data["commands"] == []
    operations = [r["operation"] for r in controller.audit_records()]
    assert "terminal_disable" in operations


def test_admin_actions_go_to_jsonl_file(tmp_path):
    audit_file = tmp_path / "audit" / "audit.jsonl"
    controller = make_controller(tmp_path)
    controller.enable_terminal(["git"])
    controller.grant_terminal()
    controller.remove_allowed_command("git")
    controller.revoke_terminal()
    text = audit_file.read_text(encoding="utf-8")
    for operation in ("terminal_enable", "terminal_grant",
                      "allowlist_remove", "terminal_revoke"):
        assert operation in text
    assert "terminal_admin" in text


# ------------------------------------------------------------- persistência
def test_allowlist_restored_on_new_controller_without_grant(tmp_path):
    """Allowlist persiste entre sessões; a PERMISSÃO TERMINAL não."""
    first = make_controller(tmp_path)
    first.enable_terminal(["git"])
    first.grant_terminal()
    assert (tmp_path / "terminal.json").exists()

    permissions = PermissionManager()  # nova sessão: só CHAT
    second = make_controller(tmp_path, permissions)
    status = second.terminal_status()
    assert status["enabled"] is True
    assert status["allowed_count"] == 1
    assert status["permission_granted"] is False  # sem concessão silenciosa
    assert [r["name"] for r in second.list_allowed_commands()] == ["git"]


def test_startup_does_not_create_terminal_file(tmp_path):
    make_controller(tmp_path)
    assert not (tmp_path / "terminal.json").exists()
    assert not (tmp_path / "workspaces.json").exists()


def test_corrupt_store_fails_closed(tmp_path):
    (tmp_path / "terminal.json").write_text("{corrompido", encoding="utf-8")
    controller = make_controller(tmp_path)
    assert controller.terminal_status()["enabled"] is False
    assert controller.list_allowed_commands() == []


def test_denylisted_entry_in_file_is_skipped_on_load(tmp_path):
    payload = {
        "commands": [
            {"name": "sh", "requires_approval": True},      # proibido
            {"name": 42},                                    # inválido
            {"name": "git", "requires_approval": False},     # válido
        ],
        "defaults": {"default_timeout_s": 5},
    }
    (tmp_path / "terminal.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    controller = make_controller(tmp_path)
    rows = controller.list_allowed_commands()
    assert [r["name"] for r in rows] == ["git"]  # fail closed por entrada
    assert rows[0]["timeout_s"] == 5  # defaults restaurados


# --------------------------------------------- gate + checkpoint (sem executar)
def test_run_without_terminal_permission_blocks_at_gate(tmp_path):
    ws = tmp_path / "docs"
    ws.mkdir()
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws))
    controller.enable_terminal(["mkdir"])
    report = controller.run_plan(plan_of(cmd_task("T1", "mkdir", ["negado"])))
    assert report.status is PlanStatus.FAILED
    assert not controller.has_pending  # sem aprovação decorativa
    assert "TERMINAL" in (report.task_run("T1").error or "")
    assert not (ws / "negado").exists()


def test_grant_terminal_unpauses_to_checkpoint_with_full_context(tmp_path):
    ws = tmp_path / "docs"
    ws.mkdir()
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws))
    controller.enable_terminal(["mkdir"])
    controller.grant_terminal()
    controller.run_plan(plan_of(cmd_task("T1", "mkdir", ["pasta"])))
    assert controller.has_pending
    pending = controller.pending_approval()
    assert pending["command"] == ["mkdir", "pasta"]
    assert pending["timeout_s"] == 10
    assert pending["resolved_path"] == str(ws.resolve())
    assert pending["permission"] == "TERMINAL"
    assert not (ws / "pasta").exists()  # nada antes da decisão


def test_revoke_while_pending_blocks_even_if_approved(tmp_path):
    """Revogar TERMINAL com checkpoint pendente: aprovar NÃO executa."""
    ws = tmp_path / "docs"
    ws.mkdir()
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws))
    controller.enable_terminal(["mkdir"])
    controller.grant_terminal()
    controller.run_plan(plan_of(cmd_task("T1", "mkdir", ["esperto"])))
    controller.revoke_terminal()  # usuário desiste enquanto pendente
    report = controller.approve("tento aprovar mesmo assim")
    assert report.status is PlanStatus.FAILED  # gate bloqueia de verdade
    assert not (ws / "esperto").exists()


# ------------------------------------------------- execução real (POSIX only)
@pytest.mark.skipif(sys.platform == "win32", reason="comando POSIX")
def test_full_admin_flow_executes_posix(tmp_path):
    ws = tmp_path / "docs"
    ws.mkdir()
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws))
    controller.enable_terminal(["printf"])
    controller.grant_terminal()
    controller.run_plan(plan_of(cmd_task("T1", "printf", ["ui-terminal"])))
    assert controller.has_pending
    report = controller.approve("ok")
    assert report.status is PlanStatus.COMPLETED
    assert "ui-terminal" in (report.task_run("T1").result or "")


@pytest.mark.skipif(sys.platform == "win32", reason="comando POSIX")
def test_removed_command_no_longer_runs(tmp_path):
    ws = tmp_path / "docs"
    ws.mkdir()
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws))
    controller.enable_terminal(["mkdir"])
    controller.grant_terminal()
    controller.remove_allowed_command("mkdir")
    report = controller.run_plan(plan_of(cmd_task("T1", "mkdir", ["jaera"])))
    assert report.status is PlanStatus.FAILED
    assert "allowlist" in (report.task_run("T1").error or "")
    assert not (ws / "jaera").exists()
