"""Testes de checkpoints do Executor (0.4.x) — 100% offline.

Garantem que checkpoints podem realmente pausar/retomar/interromper a
execução — sem nenhuma UI (abstração interna) e sem execução real.
"""
from __future__ import annotations

import pytest

from app.executor import (
    CheckpointStatus,
    EveryTaskCheckpoints,
    ExecutorError,
    NeverCheckpoints,
    PlanExecutor,
    SimulatedHandler,
)
from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus


def make_plan(tasks=None):
    specs = tasks or [("a", []), ("b", ["T1"]), ("c", ["T2"])]
    planned = [
        PlannedTask(id=f"T{i}", description=d, order=i, dependencies=tuple(deps))
        for i, (d, deps) in enumerate(specs, start=1)
    ]
    return Plan(id="PLN-0001", objective="o", status=PlanStatus.READY,
                tasks=tuple(planned))


# ------------------------------------------------- checkpoint obrigatório
def test_checkpoint_required_pauses_execution():
    handler = SimulatedHandler()
    executor = PlanExecutor(make_plan(), handler, checkpoints=EveryTaskCheckpoints())
    executor.step()  # tenta começar T1 → pausa por checkpoint

    assert executor.paused
    assert handler.executed == []                       # NADA executou
    pending = executor.pending_checkpoint
    assert pending is not None
    assert pending.status is CheckpointStatus.PENDING_APPROVAL  # necessário
    assert pending.task_id == "T1"
    assert executor.report().status is PlanStatus.RUNNING       # pausado, não falho
    assert executor.report().pending_checkpoint is pending


def test_run_all_stops_when_paused_by_checkpoint():
    handler = SimulatedHandler()
    executor = PlanExecutor(make_plan(), handler, checkpoints=EveryTaskCheckpoints())
    report = executor.run_all()
    assert executor.paused                        # parou aguardando confirmação
    assert not executor.finished
    assert report.status is PlanStatus.RUNNING
    assert handler.executed == []


# ------------------------------------------------------ checkpoint aprovado
def test_checkpoint_approved_resumes_execution():
    handler = SimulatedHandler()
    executor = PlanExecutor(make_plan([("a", [])]), handler,
                            checkpoints=EveryTaskCheckpoints())
    executor.run_all()                       # pausa antes de T1
    approved = executor.approve_checkpoint("pode seguir")

    assert approved.status is CheckpointStatus.APPROVED
    assert not executor.paused
    report = executor.run_all()               # retomada após aprovação
    assert report.completed
    assert handler.executed == ["T1"]


def test_resume_after_approval_completes_remaining_plan():
    handler = SimulatedHandler()
    executor = PlanExecutor(make_plan(), handler, checkpoints=EveryTaskCheckpoints())

    # T1: pausa → aprova → executa
    executor.run_all()
    executor.approve_checkpoint()
    executor.run_all()
    assert handler.executed == ["T1"]

    # T2: novo checkpoint (uma aprovação por tarefa)
    assert executor.pending_checkpoint.task_id == "T2"
    executor.approve_checkpoint()
    executor.run_all()
    assert handler.executed == ["T1", "T2"]

    executor.approve_checkpoint()             # T3
    report = executor.run_all()
    assert report.completed
    assert handler.executed == ["T1", "T2", "T3"]
    # histórico completo de checkpoints no relatório
    assert [c.status for c in report.checkpoints] == [CheckpointStatus.APPROVED] * 3


# ------------------------------------------------------ checkpoint recusado
def test_checkpoint_refused_fails_plan_without_executing():
    handler = SimulatedHandler()
    executor = PlanExecutor(make_plan(), handler, checkpoints=EveryTaskCheckpoints())
    executor.run_all()                          # pausa antes de T1
    refused = executor.refuse_checkpoint("ação não autorizada")

    assert refused.status is CheckpointStatus.REFUSED
    report = executor.report()
    assert report.status is PlanStatus.FAILED
    assert "recusado" in (report.error or "").lower()
    assert handler.executed == []               # nada rodou
    statuses = {r.id: r.status for r in report.tasks}
    assert statuses["T1"] is PlannedTaskStatus.SKIPPED
    assert statuses["T2"] is PlannedTaskStatus.SKIPPED
    kinds = [e.kind for e in report.events]
    assert "checkpoint_refused" in kinds and "plan_finished" in kinds


def test_approved_task_is_not_repaused():
    handler = SimulatedHandler()
    executor = PlanExecutor(make_plan([("a", [])]), handler,
                            checkpoints=EveryTaskCheckpoints())
    executor.run_all()
    executor.approve_checkpoint()
    assert executor.step().id == "T1"            # aprovada: executa direto
    assert executor.pending_checkpoint is None


# ------------------------------------------------------------- API guards
def test_approve_without_pending_checkpoint_raises():
    executor = PlanExecutor(make_plan(), SimulatedHandler())
    with pytest.raises(ExecutorError):
        executor.approve_checkpoint()


def test_refuse_without_pending_checkpoint_raises():
    executor = PlanExecutor(make_plan(), SimulatedHandler())
    with pytest.raises(ExecutorError):
        executor.refuse_checkpoint()


# ---------------------------------------------------- política padrão (0.4.1)
def test_default_policy_never_pauses():
    report = PlanExecutor(make_plan(), SimulatedHandler()).run_all()
    assert report.completed
    assert report.checkpoints == ()
    assert report.pending_checkpoint is None
    assert NeverCheckpoints().requires_checkpoint(
        make_plan([("x", [])]).tasks[0]) is False


# --------------------------------------------------- checkpoint seletivo
def test_selective_policy_only_pauses_chosen_tasks():
    class OnlySecond(EveryTaskCheckpoints):
        def requires_checkpoint(self, task) -> bool:
            return task.id == "T2"

    handler = SimulatedHandler()
    executor = PlanExecutor(make_plan([("a", []), ("b", ["T1"])]), handler,
                            checkpoints=OnlySecond())
    executor.run_all()
    assert handler.executed == ["T1"]            # T1 rodou sem checkpoint
    assert executor.pending_checkpoint.task_id == "T2"


# ---------------------------------------------------------- determinismo
def test_checkpoint_flow_is_deterministic():
    def run_flow():
        handler = SimulatedHandler()
        executor = PlanExecutor(make_plan([("a", []), ("b", ["T1"])]), handler,
                                checkpoints=EveryTaskCheckpoints())
        executor.run_all()
        executor.approve_checkpoint()
        executor.run_all()
        executor.refuse_checkpoint("não")
        return handler.executed, executor.report().to_dict()

    def strip_timestamps(report: dict) -> dict:
        # timestamps de parede não fazem parte do determinismo mecânico
        report = dict(report)
        report["checkpoints"] = [
            {k: v for k, v in c.items() if k not in ("created_at", "decided_at")}
            for c in report["checkpoints"]
        ]
        return report

    executed1, report1 = run_flow()
    executed2, report2 = run_flow()
    assert executed1 == executed2 == ["T1"]
    for key in ("status", "tasks", "events", "checkpoints"):
        assert strip_timestamps(report1)[key] == strip_timestamps(report2)[key]
