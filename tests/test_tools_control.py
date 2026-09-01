"""Testes da camada de controle (ToolsController) — 0.5.x.

Cobrem permissões, workspaces, execução com checkpoints reais (recusa
bloqueia de verdade), auditoria e as garantias de segurança exigidas
pela spec. Tudo offline, em diretórios temporários.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus
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


# ------------------------------------------------- 11F (auto-anexo run_pytest após WRITE)
def _make_controller(tmp_path: Path, tag: str = "") -> ToolsController:
    return ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / f"workspaces{tag}.json",
        audit_file=tmp_path / f"audit{tag}" / "audit.jsonl",
    )


def test_11f_appends_run_pytest_after_write_when_terminal_and_verification_enabled(
    controller, ws
):
    """Terminal + verificação 11E ON + plano com WRITE ⇒ 1 task run_pytest
    anexada no final, dependente das tasks anteriores."""
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")
    controller.enable_terminal()
    controller.enable_verification("pytest_result")
    report = controller.run_plan(ready(
        "trabalho",
        armed("T1", "create_file", {"path": "novo.txt", "content": "dados"}),
    ))
    # Execução começa com o plano ajustado (pausa no checkpoint do T1).
    assert report.status is PlanStatus.RUNNING
    assert controller.has_pending
    # Task anexada: última, id novo, depende da anterior.
    assert [t.id for t in controller._plan.tasks] == ["T1", "T2"]
    attached = controller._plan.tasks[-1]
    assert attached.tool == "run_pytest"
    assert attached.parameters == {"path": "tests"}
    assert attached.order == 2
    assert attached.dependencies == ("T1",)
    # O snapshot do relatório também contém a task anexada.
    assert len(report.tasks) == 2
    assert report.tasks[-1].id == "T2"
    assert report.tasks[-1].dependencies == ("T1",)


def test_11f_does_not_append_when_verification_disabled(controller, tmp_path, ws):
    """Não anexa quando a condição não se cumpre: verificação OFF (caso
    principal), terminal OFF, ou run_pytest já no plano (idempotência)."""
    # (1) Verificação desabilitada (terminal ON) ⇒ sem anexo.
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("WRITE")
    controller.enable_terminal()  # enable_verification NÃO é chamado
    controller.run_plan(ready("t", armed("T1", "create_file",
                                         {"path": "a.txt", "content": "x"})))
    assert [t.id for t in controller._plan.tasks] == ["T1"]
    assert all(t.tool != "run_pytest" for t in controller._plan.tasks)

    # (2) Terminal desabilitado (verificação ON) ⇒ sem anexo.
    c2 = _make_controller(tmp_path, "2")
    c2.add_workspace(str(ws), writable=True)
    c2.grant_permission("WRITE")
    c2.enable_verification("pytest_result")
    c2.run_plan(ready("t", armed("T1", "create_file",
                                 {"path": "b.txt", "content": "x"})))
    assert [t.id for t in c2._plan.tasks] == ["T1"]
    assert all(t.tool != "run_pytest" for t in c2._plan.tasks)

    # (3) run_pytest já no plano ⇒ sem duplicata.
    c3 = _make_controller(tmp_path, "3")
    c3.add_workspace(str(ws), writable=True)
    c3.grant_permission("WRITE")
    c3.enable_terminal()
    c3.enable_verification("pytest_result")
    c3.run_plan(ready(
        "t",
        armed("T1", "create_file", {"path": "c.txt", "content": "x"}),
        armed("T2", "run_pytest", {"path": "tests"}, order=2,
              dependencies=("T1",)),
    ))
    assert [t.id for t in c3._plan.tasks] == ["T1", "T2"]
    assert sum(1 for t in c3._plan.tasks if t.tool == "run_pytest") == 1


def test_11f_limit_12_tasks_fails_without_executing_any_tool(controller, ws):
    """Plano com 12/12 tasks + anexo necessário ⇒ falha **antes de
    executar**: FAILED, tudo SKIPPED, sem checkpoint e sem nenhuma
    execução bem-sucedida de tool na auditoria."""
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")
    controller.enable_terminal()
    controller.enable_verification("pytest_result")
    tasks = [
        armed(f"T{i}", "read_file", {"path": "leia.txt"}, order=i)
        for i in range(1, 12)
    ]
    tasks.append(armed("T12", "create_file", {"path": "z.txt", "content": "x"},
                       order=12))
    report = controller.run_plan(ready("t", *tasks))
    # Guardrail: falha antes de executar.
    assert report.status is PlanStatus.FAILED
    assert [t.status for t in report.tasks] == [PlannedTaskStatus.SKIPPED] * 12
    assert "run_pytest" in report.error and "12" in report.error
    # Sem checkpoint e nada pendente.
    assert not controller.has_pending
    assert report.pending_checkpoint is None
    assert report.checkpoints == ()
    # Auditoria: nenhuma execução de tool do plano (registros com
    # task_id/plan_id) — os admin (ex.: terminal_enable) são setup,
    # não execução.
    execs = [r for r in controller.audit_records() if r.get("task_id")]
    assert not execs  # nenhuma tool foi tentada, quanto menos executada
    assert not (ws / "z.txt").exists()  # nem a escrita rodou


# ------------------------------------------------------------- toggles (11H)
def _toggles_controller(tmp_path: Path, tag: str = "") -> ToolsController:
    """Controller com ``toggles_file`` compartilhado (workspaces/audit por
    instância, para isolar o que se está testando: o arquivo de toggles)."""
    return ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / f"workspaces{tag}.json",
        audit_file=tmp_path / f"audit{tag}" / "audit.jsonl",
        toggles_file=tmp_path / "agent_toggles.json",
    )


def test_toggles_persist_and_restore_corrections(tmp_path):
    """``set_corrections_enabled(True)`` persiste em agent_toggles.json e
    é restaurado em um novo ToolsController — SEM conceder permissão."""
    toggles_file = tmp_path / "agent_toggles.json"
    c1 = _toggles_controller(tmp_path, "1")
    assert c1.corrections_enabled is False  # default OFF
    c1.set_corrections_enabled(True)
    assert c1.corrections_enabled is True
    # Persistência: schema versionado, somente as flags bool.
    assert json.loads(toggles_file.read_text(encoding="utf-8")) == {
        "version": 1,
        "toggles": {"corrections_enabled": True, "verification_enabled": False},
    }
    # Restauração: novo controller (permissões/workspaces distintos) no
    # mesmo arquivo.
    c2 = _toggles_controller(tmp_path, "2")
    assert c2.corrections_enabled is True
    # Persistência NUNCA concede permissões: TERMINAL segue não-granted.
    assert c2.terminal_status()["permission_granted"] is False


def test_toggles_persist_and_restore_verification(tmp_path):
    """``set_verification_enabled(True)`` persiste e é restaurado (verifier
    ``pytest_result``) — SEM conceder permissão TERMINAL."""
    toggles_file = tmp_path / "agent_toggles.json"
    c1 = _toggles_controller(tmp_path, "1")
    assert c1.verification_enabled is False  # default OFF
    c1.set_verification_enabled(True)
    assert c1.verification_enabled is True
    payload = json.loads(toggles_file.read_text(encoding="utf-8"))
    assert payload["toggles"] == {
        "corrections_enabled": False, "verification_enabled": True,
    }
    c2 = _toggles_controller(tmp_path, "2")
    assert c2.verification_enabled is True
    # A verificação real é interpretador sem execução: nada de permissão.
    assert c2.terminal_status()["permission_granted"] is False
    # Toggle OFF também persiste (restaura estado desligado).
    c2.set_verification_enabled(False)
    c3 = _toggles_controller(tmp_path, "3")
    assert c3.verification_enabled is False


def test_toggles_fail_closed_on_corrupt_file(tmp_path):
    """Arquivo corrompido ⇒ tudo OFF, sem crash (fail-closed)."""
    (tmp_path / "agent_toggles.json").write_text(
        "isso não é JSON {{{", encoding="utf-8",
    )
    c = _toggles_controller(tmp_path, "1")  # não pode levantar
    assert c.corrections_enabled is False
    assert c.verification_enabled is False
    assert c.corrections_persisted is False
    assert c.verification_persisted is False
    # Fail-closed não impede uso: ligar depois reescreve o arquivo válido.
    c.set_corrections_enabled(True)
    c2 = _toggles_controller(tmp_path, "2")
    assert c2.corrections_enabled is True


# ------------------------------------------------------------- export (11I)
def _read_plan_controller(tmp_path: Path, export: bool) -> ToolsController:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("conteúdo", encoding="utf-8")
    permissions = PermissionManager()
    permissions.grant("READ")
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
        toggles_file=tmp_path / "agent_toggles.json",
        export_execution_reports=export,
        reports_dir=tmp_path / "reports",
    )
    controller.add_workspace(str(ws), writable=True)
    return controller


def test_11i_exports_report_when_enabled_and_sanitizes(tmp_path):
    """11I ON: run_plan terminal exporta JSON sanitizado em
    <reports_dir>/<safe_plan_id>.json — segredo NUNCA no arquivo."""
    controller = _read_plan_controller(tmp_path, export=True)
    plan = Plan(
        id="PLN:11I/TEST#1",  # ":" e "/" inválidos p/ nome de arquivo
        objective="ler a.txt (sk-TESTSECRET no objetivo)",
        status=PlanStatus.READY,
        tasks=[armed("T1", "file_exists", {"path": "a.txt"}, order=1)],
    )
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.COMPLETED
    # Nome sanitizado: ":" e "/" → "_"; "#" preservado.
    target = tmp_path / "reports" / "PLN_11I_TEST#1.json"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    payload = json.loads(content)
    assert set(payload) == {
        "version", "lumen_version", "exported_at", "plan",
        "execution_report", "correction_history", "audit",
    }
    assert payload["version"] == 1
    assert payload["plan"]["id"] == "PLN:11I/TEST#1"
    assert payload["execution_report"]["plan_id"] == "PLN:11I/TEST#1"
    assert payload["correction_history"] == []
    # Sanitização: o segredo não aparece EM NENHUMA parte do arquivo.
    assert "sk-TESTSECRET" not in content
    # Auditoria no payload: somente registros vinculados a ESTE plano.
    for record in payload["audit"]:
        assert record.get("plan_id") == report.plan_id


def test_11i_does_not_export_when_disabled(tmp_path):
    """11I OFF (default): run_plan termina normalmente e NENHUM arquivo
    de relatório nasce (bit-a-bit atual)."""
    controller = _read_plan_controller(tmp_path, export=False)
    plan = Plan(
        id="PLN-11I-OFF", objective="ler a.txt", status=PlanStatus.READY,
        tasks=[armed("T1", "file_exists", {"path": "a.txt"}, order=1)],
    )
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.COMPLETED
    reports_dir = tmp_path / "reports"
    assert not reports_dir.exists() or not any(reports_dir.iterdir())
