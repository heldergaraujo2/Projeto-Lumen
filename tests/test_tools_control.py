"""Testes da camada de controle (ToolsController) — 0.5.x.

Cobrem permissões, workspaces, execução com checkpoints reais (recusa
bloqueia de verdade), auditoria e as garantias de segurança exigidas
pela spec. Tudo offline, em diretórios temporários.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.planner.models import Plan, PlanStatus, PlannedTask
from app.security.permissions import PermissionManager
from app.tools.control import ToolsControlError, ToolsController


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "leia.txt").write_text("conteúdo", encoding="utf-8")
    return root


@pytest.fixture()
def controller(tmp_path: Path) -> ToolsController:
    return ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
    )


def armed(task_id: str, tool: str, parameters: dict, order: int = 1,
          dependencies: tuple[str, ...] = ()) -> PlannedTask:
    return PlannedTask(id=task_id, description=f"{tool} {parameters.get('path', '')}",
                       order=order, dependencies=dependencies,
                       tool=tool, parameters=parameters)


def ready(objective: str, *tasks: PlannedTask) -> Plan:
    return Plan(id="PLN-4242", objective=objective, status=PlanStatus.READY,
                tasks=tasks)


# ------------------------------------------------------------- permissões
def test_default_permissions_and_no_silent_grants(controller):
    rows = {row["level"]: row for row in controller.permission_status()}
    assert rows["CHAT"]["granted"] is True
    assert rows["READ"]["granted"] is False
    assert rows["WRITE"]["granted"] is False
    assert rows["DELETE"]["kind"] == "workspace_opt_in"
    assert rows["DELETE"]["granted"] is False


def test_grant_and_revoke_read_write(controller):
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")
    rows = {row["level"]: row for row in controller.permission_status()}
    assert rows["READ"]["granted"] and rows["WRITE"]["granted"]
    controller.revoke_permission("WRITE")
    rows = {row["level"]: row for row in controller.permission_status()}
    assert rows["WRITE"]["granted"] is False and rows["READ"]["granted"] is True


def test_terminal_computer_control_and_delete_are_rejected(controller):
    for level in ("TERMINAL", "COMPUTER_CONTROL", "DELETE", "inexistente"):
        with pytest.raises(ToolsControlError):
            controller.grant_permission(level)
        with pytest.raises(ToolsControlError):
            controller.revoke_permission(level)


def test_controller_requires_permission_manager(tmp_path):
    with pytest.raises(ToolsControlError):
        ToolsController(None, workspaces_file=tmp_path / "ws.json",
                        audit_file=tmp_path / "audit.jsonl")


# ------------------------------------------------------------- workspaces
def test_workspace_lifecycle_via_controller(controller, ws, tmp_path):
    assert controller.list_workspaces() == []
    info = controller.add_workspace(str(ws))
    assert info["mode"] == "somente leitura"
    assert controller.list_workspaces() == [
        {"root": str(ws.resolve()), "writable": False, "allow_delete": False,
         "mode": "somente leitura"},
    ]
    updated = controller.set_workspace_flags(str(ws), writable=True,
                                             allow_delete=True)
    assert updated["mode"] == "escrita + exclusão"
    controller.remove_workspace(str(ws))
    assert controller.list_workspaces() == []


def test_workspace_validation_errors_surface(controller, ws, tmp_path):
    with pytest.raises(ValueError):
        controller.add_workspace("caminho/relativo")
    with pytest.raises(ValueError):
        controller.add_workspace(str(tmp_path / "sumiu"))
    with pytest.raises(ValueError):
        controller.add_workspace(str(Path(ws.resolve().anchor)))  # disco todo
    with pytest.raises(ValueError):
        controller.add_workspace(str(ws), allow_delete=True)  # delete sem write
    assert controller.list_workspaces() == []  # nada persistiu


def test_delete_reflects_workspace_opt_in(controller, ws):
    rows = {row["level"]: row for row in controller.permission_status()}
    assert rows["DELETE"]["granted"] is False
    controller.add_workspace(str(ws), writable=True, allow_delete=True)
    rows = {row["level"]: row for row in controller.permission_status()}
    assert rows["DELETE"]["granted"] is True


# ------------------------------------------------- execução + checkpoints
def test_run_plan_executes_and_pauses_at_destructive_operation(controller, ws):
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")
    (ws / "base.txt").write_text("ok", encoding="utf-8")
    report = controller.run_plan(ready(
        "trabalho",
        armed("T1", "read_file", {"path": "base.txt"}),
        armed("T2", "create_file", {"path": "novo.txt", "content": "dados"},
              order=2, dependencies=("T1",)),
    ))
    assert report.status is PlanStatus.RUNNING  # pausado antes de T2
    assert controller.has_pending
    assert not (ws / "novo.txt").exists()  # BLOQUEADO até aprovação
    pending = controller.pending_approval()
    assert pending["task_id"] == "T2"
    assert pending["tool"] == "create_file"
    assert pending["operation"] == "write"
    assert pending["operation_label"] == "escrita"
    assert pending["permission"] == "WRITE"
    assert pending["requested_path"] == "novo.txt"
    assert pending["resolved_path"] == str((ws / "novo.txt").resolve())
    assert pending["workspace"] == str(ws.resolve())
    assert pending["status"] == "PENDING_APPROVAL"
    assert pending["plan_id"] == "PLN-4242"


def test_approval_really_executes_the_operation(controller, ws):
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("WRITE")
    controller.run_plan(ready("t", armed("T1", "create_file",
                                         {"path": "x.txt", "content": "v"})))
    report = controller.approve("pode")
    assert report.status is PlanStatus.COMPLETED
    assert (ws / "x.txt").read_text(encoding="utf-8") == "v"
    assert not controller.has_pending
    assert controller.pending_approval() is None


def test_refusal_never_executes_the_tool(controller, ws):
    """Checkpoint não é decorativo: recusar ⇒ nada roda."""
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("WRITE")
    controller.run_plan(ready("t", armed("T1", "create_file",
                                         {"path": "perigo.txt", "content": "x"})))
    report = controller.refuse("não autorizo")
    assert report.status is PlanStatus.FAILED
    assert report.task_run("T1").status.value == "SKIPPED"
    assert not (ws / "perigo.txt").exists()
    assert not controller.has_pending


def test_approve_refuse_without_pending_is_error(controller):
    with pytest.raises(ToolsControlError):
        controller.approve()
    with pytest.raises(ToolsControlError):
        controller.refuse()


def test_unfeasible_operation_fails_directly_without_checkpoint(controller, ws):
    """Operação inviável (fora do workspace) NÃO gera checkpoint decorativo:
    falha controlada direto, sem interrogar o usuário."""
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("WRITE")
    report = controller.run_plan(ready("t", armed("T1", "write_file",
                                                  {"path": "../../fora.txt",
                                                   "content": "x"})))
    assert report.status is PlanStatus.FAILED
    assert not controller.has_pending
    assert "traversal" in report.task_run("T1").error


# --------------------------------------------------------- segurança (spec)
def test_escape_traversal_symlink_blocked_via_controller(controller, ws, tmp_path):
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")
    for bad in ("../fora.txt", str(tmp_path / "absoluto.txt")):
        report = controller.run_plan(ready("t", armed("T1", "write_file",
                                                      {"path": bad, "content": "x"})))
        assert report.status is PlanStatus.FAILED, bad
    assert not (tmp_path / "fora.txt").exists()
    assert not (tmp_path / "absoluto.txt").exists()


def test_operations_still_require_permissions(controller, ws):
    controller.add_workspace(str(ws), writable=True)  # sem grants
    report = controller.run_plan(ready("t", armed("T1", "read_file",
                                                  {"path": "leia.txt"})))
    assert report.status is PlanStatus.FAILED
    assert "READ" in report.task_run("T1").error
    controller.grant_permission("READ")
    report = controller.run_plan(ready("t", armed("T1", "write_file",
                                                  {"path": "w.txt", "content": "1"})))
    assert report.status is PlanStatus.FAILED
    assert "WRITE" in report.task_run("T1").error
    assert not (ws / "w.txt").exists()


def test_delete_still_requires_double_opt_in(controller, ws):
    controller.grant_permission("WRITE")
    controller.add_workspace(str(ws), writable=True)  # sem allow_delete
    (ws / "velho.txt").write_text("lixo", encoding="utf-8")
    report = controller.run_plan(ready("t", armed("T1", "delete_file",
                                                  {"path": "velho.txt"})))
    assert report.status is PlanStatus.FAILED
    assert "allow_delete" in report.task_run("T1").error
    assert (ws / "velho.txt").exists()
    controller.set_workspace_flags(str(ws), writable=True, allow_delete=True)
    report = controller.run_plan(ready("t2", armed("T1", "delete_file",
                                                   {"path": "velho.txt"})))
    # destrutiva ⇒ checkpoint antes de executar
    assert controller.has_pending and (ws / "velho.txt").exists()
    controller.approve()
    assert not (ws / "velho.txt").exists()


def test_read_only_workspace_blocks_write_via_controller(controller, ws):
    controller.add_workspace(str(ws))  # somente leitura
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")
    report = controller.run_plan(ready("t", armed("T1", "write_file",
                                                  {"path": "n.txt", "content": "x"})))
    assert report.status is PlanStatus.FAILED
    assert "somente leitura" in report.task_run("T1").error
    assert not (ws / "n.txt").exists()


def test_no_workspaces_blocks_everything(controller):
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")
    report = controller.run_plan(ready("t", armed("T1", "read_file",
                                                  {"path": "a.txt"})))
    assert report.status is PlanStatus.FAILED
    assert "Nenhum workspace autorizado" in report.task_run("T1").error


def test_startup_has_no_side_effects(tmp_path, monkeypatch):
    """build_app + controller: nenhum arquivo de workspace/auditoria nasce,
    nenhuma permissão concedida, nenhum efeito fora de data/."""
    import main as lumen_main
    from app.config.settings import Settings

    data_dir = tmp_path / "data"
    settings = Settings(provider="mock", data_dir=data_dir)
    agent, _service = lumen_main.build_app(settings)
    from app.tools.control import ToolsController as TC

    controller = TC(agent.permissions,
                    workspaces_file=data_dir / "workspaces.json",
                    audit_file=data_dir / "audit" / "audit.jsonl")
    assert controller.list_workspaces() == []
    assert not (data_dir / "workspaces.json").exists()
    assert not (data_dir / "audit").exists()
    rows = {row["level"]: row for row in controller.permission_status()}
    assert rows["CHAT"]["granted"] and not rows["READ"]["granted"]
    assert controller.audit_records() == []  # nada executado no startup


# ------------------------------------------------------------- auditoria
def test_audit_records_with_context_and_no_content(controller, ws):
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")
    controller.run_plan(ready("t", armed("T1", "create_file",
                                         {"path": "a.txt", "content": "SEGREDO-987"})))
    controller.approve()
    records = controller.audit_records()
    assert records
    for record in records:
        assert record["task_id"] == "T1" and record["plan_id"] == "PLN-4242"
        assert record["timestamp"] and record["tool"] and record["operation"]
    assert "SEGREDO-987" not in json.dumps(records, ensure_ascii=False)
    # persistido em JSONL (separado do conteúdo dos arquivos)
    audit_file = controller._audit_file
    assert audit_file.exists()
    assert "SEGREDO-987" not in audit_file.read_text(encoding="utf-8")


def test_audit_records_fall_back_to_memory_before_file(controller):
    assert controller.audit_records() == []
    controller.audit.record(tool="read_file", operation="read",
                            requested_path="x", success=False, error="sem permissão")
    records = controller.audit_records()
    assert len(records) == 1 and records[0]["error"] == "sem permissão"


def test_permission_block_is_audited(controller, ws):
    controller.add_workspace(str(ws), writable=True)  # sem WRITE
    controller.run_plan(ready("t", armed("T1", "create_file",
                                         {"path": "a.txt", "content": "x"})))
    records = [r for r in controller.audit_records()
               if r["operation"] == "permission_gate"]
    assert records and records[0]["success"] is False
    assert records[0]["tool"] == "create_file"
