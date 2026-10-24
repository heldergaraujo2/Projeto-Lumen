"""Suíte de testes obrigatórios da Fase I (Persistência, Contexto e Verificação)."""

import json
from pathlib import Path

import pytest

from app.executor.executor import ExecutionReport, TaskRun
from app.memory.execution_store import (
    ExecutionBundleStore,
    ExecutionRecordEntry,
    ExecutionState,
)
from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus
from app.security.permissions import PermissionManager
from app.tools.control import ToolsController


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

    # Reinicializa o store para testar sobrevivência a reinício do processo
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

    # O resultado deve ter o caminho resolvido REAL do tmp_path
    task1 = report.task_run("T1")
    parsed = json.loads(task1.result)
    assert parsed["ok"] is True
    assert parsed["data"]["resolved_path"] == str(readme_file)

    # Recupera do ExecutionBundleStore
    store = controller.execution_store
    records = store.query_executions(conversation_id="CONV-README")
    assert len(records) == 1
    rec = records[0]
    assert rec["result"]["data"]["resolved_path"] == str(readme_file)
    assert rec["result"]["data"]["resolved_path"] != "/workspace/README.md"
