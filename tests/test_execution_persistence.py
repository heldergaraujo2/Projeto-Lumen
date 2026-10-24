"""Suíte de testes obrigatórios da Fase I (Persistência, Contexto e Verificação)."""

import json
from pathlib import Path

import pytest

from app.core.bridge import ToolCallingBridge
from app.executor.executor import ExecutionReport, TaskRun
from app.memory.execution_store import (
    ExecutionBundleStore,
    ExecutionRecordEntry,
    ExecutionState,
)
from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus
from app.security.permissions import PermissionManager
from app.tools.control import ToolsControlError, ToolsController


def test_save_and_retrieve_completed_execution(tmp_path):
    store = ExecutionBundleStore(tmp_path)
    plan = Plan(
        id="PLN-001",
        objective="Test plan",
        status=PlanStatus.READY,
        tasks=(
            PlannedTask(
                id="T1",
                description="Test task",
                order=1,
                tool="read_file",
                parameters={"path": "README.md"},
            ),
        ),
    )
    report = ExecutionReport(
        plan_id="PLN-001",
        objective="Test plan",
        status=PlanStatus.COMPLETED,
        tasks=(
            TaskRun(
                id="T1",
                description="Test task",
                order=1,
                dependencies=(),
                status=PlannedTaskStatus.DONE,
                result=json.dumps({
                    "ok": True,
                    "data": {
                        "requested_path": "README.md",
                        "resolved_path": str(tmp_path / "README.md"),
                        "exists": True,
                    },
                }),
                verified=True,
            ),
        ),
        events=(),
        conversation_id="CONV-123",
    )

    store.save_bundle(
        plan=plan,
        report=report,
        conversation_id="CONV-123",
        workspace=str(tmp_path),
    )

    bundle = store.load_bundle("PLN-001")
    assert bundle is not None
    assert bundle["plan_id"] == "PLN-001"
    assert bundle["conversation_id"] == "CONV-123"

    exec_record = store.get_execution("EXEC-PLN-001-T1")
    assert exec_record is not None
    assert exec_record["status"] == ExecutionState.SUCCEEDED.value
    assert exec_record["task_id"] == "T1"


def test_save_and_retrieve_failed_execution(tmp_path):
    store = ExecutionBundleStore(tmp_path)
    plan = Plan(
        id="PLN-002",
        objective="Failed plan",
        status=PlanStatus.READY,
        tasks=(
            PlannedTask(
                id="T1",
                description="Failed task",
                order=1,
                tool="read_file",
                parameters={"path": "nonexistent.txt"},
            ),
        ),
    )
    report = ExecutionReport(
        plan_id="PLN-002",
        objective="Failed plan",
        status=PlanStatus.FAILED,
        tasks=(
            TaskRun(
                id="T1",
                description="Failed task",
                order=1,
                dependencies=(),
                status=PlannedTaskStatus.FAILED,
                error="Arquivo não encontrado",
            ),
        ),
        events=(),
        conversation_id="CONV-123",
    )

    store.save_bundle(plan=plan, report=report, conversation_id="CONV-123")

    exec_record = store.get_execution("EXEC-PLN-002-T1")
    assert exec_record is not None
    assert exec_record["status"] == ExecutionState.FAILED.value
    assert exec_record["error"] == "Arquivo não encontrado"


def test_recovery_after_reinstantiation(tmp_path):
    store1 = ExecutionBundleStore(tmp_path)
    plan = Plan(
        id="PLN-003",
        objective="Persist plan",
        status=PlanStatus.READY,
        tasks=(
            PlannedTask(id="T1", description="Task 1", order=1, tool="read_file"),
        ),
    )
    report = ExecutionReport(
        plan_id="PLN-003",
        objective="Persist plan",
        status=PlanStatus.COMPLETED,
        tasks=(
            TaskRun(
                id="T1",
                description="Task 1",
                order=1,
                dependencies=(),
                status=PlannedTaskStatus.DONE,
                result=json.dumps({"ok": True, "data": {"resolved_path": "/safe/path"}}),
            ),
        ),
        events=(),
        conversation_id="CONV-999",
    )
    store1.save_bundle(plan=plan, report=report, conversation_id="CONV-999")

    store2 = ExecutionBundleStore(tmp_path)
    results = store2.query_executions(conversation_id="CONV-999")
    assert len(results) == 1
    assert results[0]["execution_id"] == "EXEC-PLN-003-T1"


def test_readme_verification_scenario(tmp_path):
    """Cenário obrigatório do README.md com diretório e caminho resolvido controlado."""
    readme_file = tmp_path / "README.md"
    readme_file.write_text("# Test Project", encoding="utf-8")

    perms = PermissionManager()
    perms.grant("CHAT")
    perms.grant("READ")

    controller = ToolsController(
        perms,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit.jsonl",
        persist_execution_state=True,
        execution_state_dir=tmp_path / "executions",
    )
    controller.add_workspace(str(tmp_path), writable=False)

    plan = Plan(
        id="PLN-README",
        objective="Verificar se README.md existe",
        status=PlanStatus.READY,
        tasks=(
            PlannedTask(
                id="T1",
                description="Verificar existência de README.md",
                order=1,
                tool="read_file",
                parameters={"path": "README.md"},
            ),
        ),
        conversation_id="CONV-README",
    )

    report = controller.run_plan(plan)
    assert report.status is PlanStatus.COMPLETED

    task1 = report.task_run("T1")
    parsed = json.loads(task1.result)
    assert parsed["ok"] is True
    assert parsed["data"]["resolved_path"] == str(readme_file)

    store = controller.execution_store
    records = store.query_executions(conversation_id="CONV-README")
    assert len(records) == 1
    rec = records[0]
    assert rec["result"]["data"]["resolved_path"] == str(readme_file)
    assert rec["result"]["data"]["resolved_path"] != "/workspace/README.md"


def test_windows_readme_exact_path_preservation(tmp_path):
    """Regressão: D:\\Lumen Oficial\\README.md preservado exatamente sem invenção de caminhos fictícios."""
    win_path = r"D:\Lumen Oficial\README.md"
    perms = PermissionManager()
    controller = ToolsController(
        perms,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit.jsonl",
        persist_execution_state=True,
        execution_state_dir=tmp_path / "executions",
    )

    plan = Plan(
        id="PLN-WIN-README",
        objective="Verificar README no Windows",
        status=PlanStatus.READY,
        tasks=(
            PlannedTask(
                id="T1",
                description="Verificar README",
                order=1,
                tool="read_file",
                parameters={"path": "README.md"},
            ),
        ),
        conversation_id="CONV-WIN",
    )
    report = ExecutionReport(
        plan_id="PLN-WIN-README",
        objective="Verificar README no Windows",
        status=PlanStatus.COMPLETED,
        tasks=(
            TaskRun(
                id="T1",
                description="Verificar README",
                order=1,
                dependencies=(),
                status=PlannedTaskStatus.DONE,
                result=json.dumps({
                    "ok": True,
                    "data": {
                        "requested_path": "README.md",
                        "resolved_path": win_path,
                        "exists": True,
                    },
                }),
                verified=True,
            ),
        ),
        events=(),
        conversation_id="CONV-WIN",
    )

    controller.execution_store.save_bundle(
        plan=plan,
        report=report,
        conversation_id="CONV-WIN",
    )

    bridge = ToolCallingBridge(agent=None, controller=controller)
    ctx = bridge.get_execution_context("CONV-WIN")
    assert win_path in ctx
    assert "/workspace/README.md" not in ctx


def test_cross_conversation_context_isolation(tmp_path):
    """Garante isolamento total por conversation_id."""
    perms = PermissionManager()
    controller = ToolsController(
        perms,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit.jsonl",
        persist_execution_state=True,
        execution_state_dir=tmp_path / "executions",
    )

    plan_a = Plan(id="PLN-A", objective="Plano A", status=PlanStatus.READY)
    report_a = ExecutionReport(
        plan_id="PLN-A", objective="Plano A", status=PlanStatus.COMPLETED,
        tasks=(TaskRun(id="T1", description="Task A", order=1, dependencies=(), status=PlannedTaskStatus.DONE, result=json.dumps({"ok": True, "data": {"resolved_path": "/conv_a/file.txt"}})),),
        events=(), conversation_id="CONV-A",
    )
    controller.execution_store.save_bundle(plan=plan_a, report=report_a, conversation_id="CONV-A")

    bridge = ToolCallingBridge(agent=None, controller=controller)

    # Consulta CONV-B
    ctx_b = bridge.get_execution_context("CONV-B")
    assert ctx_b == ""

    # Consulta CONV-A
    ctx_a = bridge.get_execution_context("CONV-A")
    assert "/conv_a/file.txt" in ctx_a


def test_safe_task_resumption_preserves_completed_tasks(tmp_path, monkeypatch):
    """Garante que a retomada não reexecuta tarefas concluídas e processa tarefas pendentes."""
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    file1.write_text("Conteudo 1", encoding="utf-8")
    file2.write_text("Conteudo 2", encoding="utf-8")

    perms = PermissionManager()
    perms.grant("CHAT")
    perms.grant("READ")

    controller = ToolsController(
        perms,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit.jsonl",
        persist_execution_state=True,
        execution_state_dir=tmp_path / "executions",
    )
    controller.add_workspace(str(tmp_path), writable=False)

    plan = Plan(
        id="PLN-RESUME-1",
        objective="Plano com 2 etapas",
        status=PlanStatus.READY,
        tasks=(
            PlannedTask(
                id="T1",
                description="Ler file1",
                order=1,
                tool="read_file",
                parameters={"path": "file1.txt"},
            ),
            PlannedTask(
                id="T2",
                description="Ler file2",
                order=2,
                dependencies=("T1",),
                tool="read_file",
                parameters={"path": "file2.txt"},
            ),
        ),
        conversation_id="CONV-RESUME",
    )

    t1_result_saved = json.dumps({
        "ok": True,
        "data": {
            "requested_path": "file1.txt",
            "resolved_path": str(file1),
            "content": "Conteudo 1 Preservado",
        },
    })
    interrupted_report = ExecutionReport(
        plan_id="PLN-RESUME-1",
        objective="Plano com 2 etapas",
        status=PlanStatus.FAILED,
        tasks=(
            TaskRun(
                id="T1",
                description="Ler file1",
                order=1,
                dependencies=(),
                status=PlannedTaskStatus.DONE,
                result=t1_result_saved,
                verified=True,
            ),
            TaskRun(
                id="T2",
                description="Ler file2",
                order=2,
                dependencies=("T1",),
                status=PlannedTaskStatus.PENDING,
            ),
        ),
        events=(),
        conversation_id="CONV-RESUME",
    )

    controller.execution_store.save_bundle(
        plan=plan,
        report=interrupted_report,
        conversation_id="CONV-RESUME",
        workspace=str(tmp_path),
    )

    registry = controller.build_registry()
    executed_paths = []
    original_execute = registry.execute

    def counted_execute(name, **kwargs):
        if name == "read_file":
            executed_paths.append(kwargs.get("path"))
        return original_execute(name, **kwargs)

    registry.execute = counted_execute
    monkeypatch.setattr(controller, "build_registry", lambda: registry)

    resumed_report = controller.resume_execution(
        "PLN-RESUME-1", conversation_id="CONV-RESUME"
    )
    assert resumed_report.status is PlanStatus.COMPLETED

    res_t1 = resumed_report.task_run("T1")
    assert res_t1.status is PlannedTaskStatus.DONE
    parsed_t1 = json.loads(res_t1.result)
    assert parsed_t1["ok"] is True
    assert parsed_t1["data"]["resolved_path"] == str(file1)
    # O armazenamento remove conteúdo integral de arquivos por política
    # de sanitização; o resultado persistido continua íntegro para retomada.
    assert "content" not in parsed_t1["data"]

    res_t2 = resumed_report.task_run("T2")
    assert res_t2.status is PlannedTaskStatus.DONE
    parsed_t2 = json.loads(res_t2.result)
    assert parsed_t2["ok"] is True
    assert parsed_t2["data"]["resolved_path"] == str(file2)
    # Prova comportamental: T1 (concluída) não chama a ferramenta novamente;
    # somente a tarefa PENDING é executada durante a retomada.
    assert executed_paths == ["file2.txt"]


def test_resume_execution_blocks_on_unknown_task_status(tmp_path):
    """Retomada é interrompida por segurança quando uma tarefa tem estado UNKNOWN."""
    perms = PermissionManager()
    controller = ToolsController(
        perms,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit.jsonl",
        persist_execution_state=True,
        execution_state_dir=tmp_path / "executions",
    )

    plan = Plan(
        id="PLN-UNKNOWN",
        objective="Plano com tarefa desconhecida",
        status=PlanStatus.READY,
        tasks=(
            PlannedTask(id="T1", description="Task unknown", order=1, tool="read_file"),
        ),
        conversation_id="CONV-UNKNOWN",
    )
    report = ExecutionReport(
        plan_id="PLN-UNKNOWN",
        objective="Plano com tarefa desconhecida",
        status=PlanStatus.FAILED,
        tasks=(
            TaskRun(
                id="T1",
                description="Task unknown",
                order=1,
                dependencies=(),
                status=PlannedTaskStatus.PENDING,
            ),
        ),
        events=(), conversation_id="CONV-UNKNOWN",
    )
    controller.execution_store.save_bundle(
        plan=plan, report=report, conversation_id="CONV-UNKNOWN"
    )

    bundle = controller.execution_store.load_bundle("PLN-UNKNOWN")
    bundle["execution_report"]["tasks"][0]["status"] = "UNKNOWN"
    bundle_path = tmp_path / "executions" / "PLN-UNKNOWN.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(ToolsControlError) as exc_info:
        controller.resume_execution(
            "PLN-UNKNOWN", conversation_id="CONV-UNKNOWN"
        )
    assert "UNKNOWN" in str(exc_info.value)


@pytest.mark.parametrize("unsafe_status", [
    "RUNNING", "IN_PROGRESS", "FAILED", "UNKNOWN", "", "DONE_WITHOUT_RESULT",
])
def test_resume_execution_fails_closed_for_ambiguous_states(tmp_path, unsafe_status):
    perms = PermissionManager()
    controller = ToolsController(
        perms,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit.jsonl",
        execution_state_dir=tmp_path / "executions",
    )
    plan = Plan(
        id="PLN-UNSAFE",
        objective="Estado ambíguo",
        status=PlanStatus.READY,
        tasks=(PlannedTask(id="T1", description="Task", order=1, tool="read_file",
                           parameters={"path": "should-not-run.txt"}),),
        conversation_id="CONV-UNSAFE",
    )
    report = ExecutionReport(
        plan_id="PLN-UNSAFE", objective="Estado ambíguo", status=PlanStatus.FAILED,
        tasks=(TaskRun(id="T1", description="Task", order=1, dependencies=(),
                       status=PlannedTaskStatus.PENDING),),
        events=(), conversation_id="CONV-UNSAFE",
    )
    controller.execution_store.save_bundle(
        plan=plan, report=report, conversation_id="CONV-UNSAFE"
    )
    bundle = controller.execution_store.load_bundle("PLN-UNSAFE")
    task = bundle["execution_report"]["tasks"][0]
    task["status"] = unsafe_status
    if unsafe_status == "DONE_WITHOUT_RESULT":
        task["status"] = "DONE"
        task["result"] = None
    bundle_path = tmp_path / "executions" / "PLN-UNSAFE.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(ToolsControlError):
        controller.resume_execution("PLN-UNSAFE", conversation_id="CONV-UNSAFE")


def test_resume_execution_rejects_wrong_conversation(tmp_path):
    controller = ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit.jsonl",
        execution_state_dir=tmp_path / "executions",
    )
    plan = Plan(
        id="PLN-CONV", objective="Isolamento", status=PlanStatus.READY,
        tasks=(PlannedTask(id="T1", description="Task", order=1, tool="read_file"),),
        conversation_id="CONV-A",
    )
    report = ExecutionReport(
        plan_id="PLN-CONV", objective="Isolamento", status=PlanStatus.FAILED,
        tasks=(TaskRun(id="T1", description="Task", order=1, dependencies=(),
                       status=PlannedTaskStatus.PENDING),),
        events=(), conversation_id="CONV-A",
    )
    controller.execution_store.save_bundle(
        plan=plan, report=report, conversation_id="CONV-A"
    )
    with pytest.raises(ToolsControlError, match="não pertence à conversa"):
        controller.resume_execution("PLN-CONV", conversation_id="CONV-B")


def test_query_executions_does_not_inherit_missing_record_conversation_id(tmp_path):
    store = ExecutionBundleStore(tmp_path)
    plan = Plan(
        id="PLN-STRICT-CONV", objective="Consulta estrita", status=PlanStatus.READY,
        tasks=(PlannedTask(id="T1", description="Task", order=1, tool="read_file"),),
        conversation_id="CONV-BUNDLE",
    )
    report = ExecutionReport(
        plan_id="PLN-STRICT-CONV", objective="Consulta estrita",
        status=PlanStatus.COMPLETED,
        tasks=(TaskRun(id="T1", description="Task", order=1, dependencies=(),
                       status=PlannedTaskStatus.DONE,
                       result=json.dumps({"ok": True, "data": {}, "error": None}),),),
        events=(), conversation_id="CONV-BUNDLE",
    )
    store.save_bundle(plan=plan, report=report, conversation_id="CONV-BUNDLE")
    path = tmp_path / "PLN-STRICT-CONV.json"
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["execution_records"][0].pop("conversation_id", None)
    path.write_text(json.dumps(bundle), encoding="utf-8")

    assert store.query_executions(conversation_id="CONV-BUNDLE") == []
