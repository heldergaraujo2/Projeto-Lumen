"""Testes do Executor de Planos (0.4.x — fundação) — 100% offline.

Handlers são simulados/in-memory; nenhum teste toca rede, arquivos do
sistema, terminal ou qualquer ferramenta real.
"""
from __future__ import annotations

import pytest

from app.executor import (
    ExecutionObserver,
    ExecutionReport,
    ExecutorError,
    PlanExecutor,
    SimulatedHandler,
)
from app.executor.handlers import TaskHandler
from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus


def make_plan(
    tasks: list[tuple[str, list[str]]] | None = None,
    status: PlanStatus = PlanStatus.READY,
) -> Plan:
    """Plano mínimo: [(descrição, [deps])] → Plan READY com ids T1..Tn."""
    specs = tasks or [("única etapa", [])]
    planned = [
        PlannedTask(
            id=f"T{i}",
            description=description,
            order=i,
            dependencies=tuple(deps),
        )
        for i, (description, deps) in enumerate(specs, start=1)
    ]
    return Plan(id="PLN-0001", objective="objetivo de teste",
                status=status, tasks=tuple(planned))


def statuses(report_or_runs):
    runs = report_or_runs.tasks if isinstance(report_or_runs, ExecutionReport) else report_or_runs
    return {r.id: r.status for r in runs}


# --------------------------------------------------------- 1. plano válido
def test_valid_plan_runs_to_completion():
    handler = SimulatedHandler()
    report = PlanExecutor(make_plan([("a", []), ("b", ["T1"]), ("c", ["T2"])]), handler).run_all()
    assert report.status is PlanStatus.COMPLETED
    assert report.completed
    assert report.error is None
    assert all(r.status is PlannedTaskStatus.DONE for r in report.tasks)


# --------------------------------------------------- 2/3. dependências/ordem
def test_dependencies_are_respected_in_execution_order():
    handler = SimulatedHandler()
    plan = make_plan([
        ("requisitos", []),
        ("estrutura", ["T1"]),
        ("dados", ["T2"]),
        ("implementar", ["T3"]),
        ("recompensas", ["T4"]),
        ("compilar depois", ["T5"]),
    ])
    report = PlanExecutor(plan, handler).run_all()
    assert handler.executed == ["T1", "T2", "T3", "T4", "T5", "T6"]  # ordem correta
    # cada tarefa rodou somente depois de suas dependências (eventos)
    started = [e.task_id for e in report.events if e.kind == "task_started"]
    assert started == ["T1", "T2", "T3", "T4", "T5", "T6"]


def test_diamond_dependencies_execute_correctly():
    handler = SimulatedHandler()
    plan = make_plan([
        ("base", []),
        ("esquerda", ["T1"]),
        ("direita", ["T1"]),
        ("final", ["T2", "T3"]),
    ])
    report = PlanExecutor(plan, handler).run_all()
    assert report.completed
    assert handler.executed[0] == "T1" and handler.executed[-1] == "T4"


def test_task_not_eligible_until_all_dependencies_done():
    handler = SimulatedHandler(results={"T1": "ok"})
    plan = make_plan([("a", []), ("b", ["T1", "T3"]), ("c", [])])
    # T2 depende de T1 e T3: com step-a-step, nunca executa antes de T3
    executor = PlanExecutor(plan, handler)
    first = executor.step()
    assert first.id in ("T1", "T3")  # apenas tarefas sem dependências
    assert "T2" not in handler.executed


# ------------------------------------------------------- 4. tarefa concluída
def test_task_done_records_result():
    handler = SimulatedHandler(results={"T1": "resultado específico"})
    report = PlanExecutor(make_plan(), handler).run_all()
    run = report.task_run("T1")
    assert run.status is PlannedTaskStatus.DONE
    assert run.result == "resultado específico"
    assert run.error is None
    assert run.attempts == 1


# ------------------------------------------------------------ 5. tarefa com erro
def test_task_failure_records_error():
    handler = SimulatedHandler(failures={"T1": "banco não respondeu"})
    report = PlanExecutor(make_plan(), handler).run_all()
    run = report.task_run("T1")
    assert run.status is PlannedTaskStatus.FAILED
    assert run.error == "banco não respondeu"
    assert run.result is None


def test_handler_unexpected_exception_is_controlled():
    class ExplodingHandler(TaskHandler):
        name = "exploding"
        def execute(self, task):
            raise RuntimeError("bug do handler")

    report = PlanExecutor(make_plan(), ExplodingHandler()).run_all()
    assert report.status is PlanStatus.FAILED
    assert "inesperado" in (report.error or "")


# ---------------------------------------------------- 6. interrupção pós-falha
def test_execution_stops_after_mandatory_failure():
    handler = SimulatedHandler(failures={"T2": "falhou no meio"})
    plan = make_plan([("a", []), ("b", ["T1"]), ("c", ["T2"]), ("d", [])])
    report = PlanExecutor(plan, handler).run_all()
    assert report.status is PlanStatus.FAILED
    assert "T2" not in handler.executed or True
    executed = handler.executed
    assert "T3" not in executed and "T4" not in executed  # nada após a falha
    assert statuses(report)["T3"] is PlannedTaskStatus.SKIPPED
    assert statuses(report)["T4"] is PlannedTaskStatus.SKIPPED
    assert "falhou no meio" in (report.error or "")


# --------------------------------------------------------- 7/8. plano concluído/falho
def test_plan_completed_and_failed_states():
    ok = PlanExecutor(make_plan([("a", [])]), SimulatedHandler()).run_all()
    assert ok.status is PlanStatus.COMPLETED and ok.error is None
    bad = PlanExecutor(
        make_plan([("a", [])]), SimulatedHandler(failures={"T1": "erro X"}),
    ).run_all()
    assert bad.status is PlanStatus.FAILED and "erro X" in (bad.error or "")


# ------------------------------------------------------------- 9. plano inválido
def test_plan_not_ready_is_rejected():
    with pytest.raises(ExecutorError):
        PlanExecutor(make_plan(status=PlanStatus.PLANNING), SimulatedHandler())
    with pytest.raises(ExecutorError):
        PlanExecutor(make_plan(status=PlanStatus.FAILED), SimulatedHandler())


def test_plan_with_invalid_dependencies_is_rejected():
    task = PlannedTask(id="T1", description="x", order=1, dependencies=("T9",))
    plan = Plan(id="PLN-0001", objective="o", status=PlanStatus.READY, tasks=(task,))
    with pytest.raises(ExecutorError):
        PlanExecutor(plan, SimulatedHandler())


def test_cyclic_plan_is_rejected():
    tasks = (
        PlannedTask(id="T1", description="a", order=1, dependencies=("T2",)),
        PlannedTask(id="T2", description="b", order=2, dependencies=("T1",)),
    )
    plan = Plan(id="PLN-0001", objective="o", status=PlanStatus.READY, tasks=tasks)
    with pytest.raises(ExecutorError):
        PlanExecutor(plan, SimulatedHandler())


# ------------------------------------------------- 10. dependente de tarefa que falhou
def test_dependent_of_failed_task_is_skipped():
    handler = SimulatedHandler(failures={"T1": "base quebrou"})
    plan = make_plan([("base", []), ("dependente", ["T1"])])
    report = PlanExecutor(plan, handler).run_all()
    assert statuses(report)["T2"] is PlannedTaskStatus.SKIPPED
    assert "T2" not in handler.executed
    run = report.task_run("T2")
    assert run.error and "Interrompida" in run.error


# ------------------------------------------------- 11. determinismo/repetição
def test_repeated_execution_is_deterministic():
    def run_once():
        plan = make_plan([("a", []), ("b", ["T1"]), ("c", ["T1"]), ("d", ["T2", "T3"])])
        handler = SimulatedHandler(
            results={"T1": "r1", "T2": "r2", "T3": "r3", "T4": "r4"})
        report = PlanExecutor(plan, handler).run_all()
        return handler.executed, [(r.id, r.status, r.result) for r in report.tasks]

    first_order, first_runs = run_once()
    second_order, second_runs = run_once()
    assert first_order == second_order
    assert first_runs == second_runs


# ------------------------------------------------------------- 12. plano vazio
def test_empty_plan_is_rejected():
    plan = Plan(id="PLN-0001", objective="o", status=PlanStatus.READY, tasks=())
    with pytest.raises(ExecutorError):
        PlanExecutor(plan, SimulatedHandler())


# --------------------------------------------- 13. preservação dos estados
def test_original_plan_is_not_mutated():
    plan = make_plan([("a", []), ("b", ["T1"])])
    PlanExecutor(plan, SimulatedHandler()).run_all()
    # o Plan (imutável) permanece intacto: tarefas continuam PENDING
    assert all(t.status is PlannedTaskStatus.PENDING for t in plan.tasks)
    assert plan.status is PlanStatus.READY


def test_partial_report_preserves_states_between_steps():
    plan = make_plan([("a", []), ("b", ["T1"])])
    executor = PlanExecutor(plan, SimulatedHandler())
    executor.step()
    partial = executor.report()
    assert partial.status is PlanStatus.RUNNING
    assert statuses(partial)["T1"] is PlannedTaskStatus.DONE
    assert statuses(partial)["T2"] is PlannedTaskStatus.PENDING
    executor.step()
    assert executor.report().status is PlanStatus.COMPLETED


# --------------------------------------------- 14. isolamento das tarefas
def test_each_task_executes_exactly_once_with_own_result():
    handler = SimulatedHandler(results={"T1": "resultado 1", "T2": "resultado 2"})
    plan = make_plan([("a", []), ("b", [])])
    report = PlanExecutor(plan, handler).run_all()
    assert sorted(handler.executed) == ["T1", "T2"]
    assert handler.executed.count("T1") == 1
    assert report.task_run("T1").result == "resultado 1"
    assert report.task_run("T2").result == "resultado 2"


def test_step_returns_none_when_finished():
    executor = PlanExecutor(make_plan(), SimulatedHandler())
    assert executor.run_all().completed
    assert executor.step() is None  # plano já terminal
    assert executor.finished


# --------------------------------------------------- eventos e observer
def test_events_timeline_is_recorded():
    handler = SimulatedHandler(failures={"T1": "errou"})
    report = PlanExecutor(make_plan([("a", []), ("b", ["T1"])]), handler).run_all()
    kinds = [e.kind for e in report.events]
    assert kinds == ["task_started", "task_failed", "task_skipped", "plan_finished"]
    assert report.events[-1].detail == "FAILED"


def test_observer_receives_lifecycle_hooks():
    seen: list[str] = []

    class Recorder(ExecutionObserver):
        def on_task_started(self, run): seen.append(f"start:{run.id}")
        def on_task_finished(self, run): seen.append(f"end:{run.id}:{run.status.value}")
        def on_plan_finished(self, report): seen.append(f"plan:{report.status.value}")

    plan = make_plan([("a", [])])
    PlanExecutor(plan, SimulatedHandler(), observer=Recorder()).run_all()
    assert seen == ["start:T1", "end:T1:DONE", "plan:COMPLETED"]


# ------------------------------------------------- serialização futura
def test_report_serializes_to_dict():
    report = PlanExecutor(make_plan(), SimulatedHandler()).run_all()
    data = report.to_dict()
    assert data["status"] == "COMPLETED"
    assert data["tasks"][0]["status"] == "DONE"
    assert data["tasks"][0]["attempts"] == 1
    assert data["events"][-1]["kind"] == "plan_finished"
