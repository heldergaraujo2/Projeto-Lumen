"""Testes do motor de correção controlada (0.6.2) — genérico, in-memory.

Cobrem o ciclo EXECUTAR→VERIFICAR→(ANALISAR→PROPOR→VALIDAR→APROVAR→
APLICAR→RETRY→VERIFICAR) com handlers/verificadores simulados: sucessos,
falhas de execução/verificação, propostas, aprovação/recusa/invalidação,
limites rígidos, imutabilidade dos planos e ausência de retry infinito.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.executor.correction import (
    CorrectionEngine,
    CorrectionProposal,
    CorrectionStatus,
    ExecutorNotPausedError,
    NoopCorrectionStrategy,
)
from app.executor.checkpoints import EveryTaskCheckpoints
from app.executor.handlers import HandlerError, TaskHandler
from app.executor.verification import TaskVerifier, VerificationResult
from app.planner.models import Plan, PlanStatus, PlannedTask


# ------------------------------------------------------------------ helpers
class ScriptedHandler(TaskHandler):
    """Handler que falha N vezes por tarefa e depois succeeds."""

    name = "scripted"

    def __init__(self, failures: dict[str, int], error: str = "quebrou") -> None:
        self._failures = dict(failures)
        self._error = error
        self.calls: list[str] = []

    def execute(self, task: PlannedTask) -> str:
        self.calls.append(task.id)
        remaining = self._failures.get(task.id, 0)
        if remaining > 0:
            self._failures[task.id] = remaining - 1
            raise HandlerError(f"{self._error} ({task.id})")
        return f"ok:{task.id}"


class OnceRejectingVerifier(TaskVerifier):
    """Verificador que reprova as tarefas dadas na 1ª vez; aprova depois."""

    name = "once-rejecting"

    def __init__(self, only: tuple[str, ...] = ("T1", "T2")) -> None:
        self._only = set(only)
        self.seen: set[str] = set()

    def verify(self, task: PlannedTask, result: str) -> VerificationResult:
        if task.id in self._only and task.id not in self.seen:
            self.seen.add(task.id)
            return VerificationResult(False, "resultado insatisfatório")
        return VerificationResult(True, "verificado")


class SwitchToolStrategy(NoopCorrectionStrategy):
    """Propõe trocar a tool da tarefa falha por 'fixed_tool'."""

    def propose_correction(self, task, run):
        if task.id != "T2":
            return None
        corrected = replace(task, tool="fixed_tool",
                            description=task.description + " [corrigido]")
        return CorrectionProposal(suggestion="trocar para fixed_tool",
                                  detail=f"falha: {run.error}",
                                  corrected_task=corrected,
                                  requires_approval=True)


class AutoApplyStrategy(SwitchToolStrategy):
    """Mesma proposta, sem exigir aprovação (aplicação imediata)."""

    def propose_correction(self, task, run):
        proposal = super().propose_correction(task, run)
        if proposal is not None:
            proposal = replace(proposal, requires_approval=False)
        return proposal


def plan_of(*tasks: PlannedTask) -> Plan:
    return Plan(id="PLN-C1", objective="correção", status=PlanStatus.READY,
                tasks=tasks)


def two_task_plan() -> Plan:
    return plan_of(
        PlannedTask(id="T1", description="primeira", order=1),
        PlannedTask(id="T2", description="segunda", order=2,
                    dependencies=("T1",)),
    )


def build(plan, handler, *, strategy=None, validator=None,
          checkpoints_factory=None, verifier=None, **kwargs):
    return CorrectionEngine(
        plan, lambda plan_id: handler,
        strategy=strategy or NoopCorrectionStrategy(),
        validator=validator, checkpoints_factory=checkpoints_factory,
        verifier_factory=(lambda: verifier) if verifier else None,
        **kwargs,
    )


# ------------------------------------------------------------- cenário base
def test_success_without_corrections():
    handler = ScriptedHandler({})
    engine = build(two_task_plan(), handler)
    report = engine.run()
    assert report.status is PlanStatus.COMPLETED
    assert report.corrections == ()
    assert report.success_after_correction is False
    assert engine.plan_ids == ("PLN-C1",)


def test_execution_failure_without_proposal_is_definitive():
    handler = ScriptedHandler({"T2": 99})  # sempre falha
    engine = build(two_task_plan(), handler)  # Noop: sem proposta
    report = engine.run()
    assert report.status is PlanStatus.FAILED
    statuses = [c.status for c in report.corrections]
    assert statuses == [CorrectionStatus.NO_PROPOSAL]
    assert handler.calls == ["T1", "T2"]  # nada repetiu
    assert engine.current_plan is engine._root_plan  # nenhum sucessor


def test_verification_failure_classified_and_correctable():
    handler = ScriptedHandler({})
    engine = build(two_task_plan(), handler, strategy=SwitchToolStrategy(),
                   verifier=OnceRejectingVerifier(only=("T2",)))
    engine.run()  # pausa na correção da reprovada
    assert engine.correction_pending is not None
    pending = engine.correction_pending
    assert pending.failure_kind == "verification"
    assert pending.task_id == "T2"
    assert pending.original_tool != "fixed_tool"


# ------------------------------------------------------------------ propostas
def test_proposal_generates_cycle_and_pending_view():
    handler = ScriptedHandler({"T2": 1})
    engine = build(two_task_plan(), handler, strategy=SwitchToolStrategy())
    engine.run()
    cycle = engine.cycles[0]
    assert cycle.status is CorrectionStatus.PROPOSED
    assert cycle.failure_kind == "execution"
    assert cycle.replacement_tool == "fixed_tool"
    pending = engine.correction_pending
    assert pending.suggestion == "trocar para fixed_tool"
    assert pending.corrected_tool == "fixed_tool"


def test_approved_correction_retries_and_succeeds():
    handler = ScriptedHandler({"T2": 1})  # falha 1x, depois ok
    engine = build(two_task_plan(), handler, strategy=SwitchToolStrategy())
    engine.run()
    report = engine.approve_correction("pode")
    assert report.status is PlanStatus.COMPLETED
    assert report.success_after_correction is True
    statuses = [c.status for c in engine.cycles]
    assert statuses == [
        CorrectionStatus.PROPOSED, CorrectionStatus.APPROVED,
        CorrectionStatus.APPLIED, CorrectionStatus.RETRIED,
        CorrectionStatus.SUCCEEDED,
    ]
    assert handler.calls.count("T2") == 2  # original + corrigida
    assert len(engine.plan_ids) == 2 and engine.plan_ids[1].endswith("#C1")


def test_refused_correction_applies_nothing_and_fails():
    handler = ScriptedHandler({"T2": 1})
    engine = build(two_task_plan(), handler, strategy=SwitchToolStrategy())
    engine.run()
    before = list(handler.calls)
    report = engine.refuse_correction("não quero")
    assert report.status is PlanStatus.FAILED
    assert handler.calls == before  # NADA executou após a recusa
    assert engine.cycles[-1].status is CorrectionStatus.REFUSED
    assert engine.plan_ids == ("PLN-C1",)  # nenhum sucessor criado


def test_invalid_correction_is_never_applied():
    handler = ScriptedHandler({"T2": 1})
    engine = build(two_task_plan(), handler, strategy=SwitchToolStrategy(),
                   validator=lambda task: "Permissão WRITE não concedida")
    report = engine.run()
    assert report.status is PlanStatus.FAILED
    assert engine.cycles[-1].status is CorrectionStatus.INVALID
    assert "WRITE" in engine.cycles[-1].decision_note
    assert engine.correction_pending is None
    assert handler.calls == ["T1", "T2"]  # nada além do original


def test_auto_apply_correction_without_approval():
    handler = ScriptedHandler({"T2": 1})
    engine = build(two_task_plan(), handler, strategy=AutoApplyStrategy())
    report = engine.run()
    assert report.status is PlanStatus.COMPLETED
    assert report.success_after_correction is True
    assert engine.correction_pending is None


def test_advice_only_proposal_is_recorded_and_stops():
    handler = ScriptedHandler({"T2": 5})
    engine = build(two_task_plan(), handler, strategy=NoopCorrectionStrategy())
    # Noop não propõe; testar proposta SEM corrected_task via stub:
    class AdviceOnly(NoopCorrectionStrategy):
        def propose_correction(self, task, run):
            return CorrectionProposal(suggestion="revisar a mão",
                                      corrected_task=None)

    engine = build(two_task_plan(), handler, strategy=AdviceOnly())
    report = engine.run()
    assert report.status is PlanStatus.FAILED
    assert engine.cycles[-1].status is CorrectionStatus.NO_PROPOSAL
    assert engine.cycles[-1].suggestion == "revisar a mão"


# ------------------------------------------------------------------- limites
def test_max_cycles_limit_produces_exhausted():
    handler = ScriptedHandler({"T2": 99})  # sempre falha
    engine = build(two_task_plan(), handler, strategy=AutoApplyStrategy(),
                   max_cycles=1)
    report = engine.run()
    assert report.status is PlanStatus.FAILED
    statuses = [(c.number, c.status) for c in engine.cycles]
    # ciclo 1 aplicado por completo; análise 2 exaurida (limite)
    assert statuses == [
        (1, CorrectionStatus.PROPOSED), (1, CorrectionStatus.APPROVED),
        (1, CorrectionStatus.APPLIED), (1, CorrectionStatus.RETRIED),
        (2, CorrectionStatus.EXHAUSTED),
    ]
    assert handler.calls.count("T2") == 2  # original + 1 correção — fim


def test_max_total_attempts_limits_executions():
    handler = ScriptedHandler({"T2": 99})
    engine = build(two_task_plan(), handler, strategy=AutoApplyStrategy(),
                   max_cycles=5, max_total_attempts=2)
    report = engine.run()
    assert report.status is PlanStatus.FAILED
    assert engine.cycles[-1].status is CorrectionStatus.EXHAUSTED
    assert "tentativas" in engine.cycles[-1].decision_note
    assert handler.calls.count("T2") == 1  # 1ª execução + limite atingido


def test_correction_failing_again_is_definitive_failure():
    handler = ScriptedHandler({"T2": 99})
    engine = build(two_task_plan(), handler, strategy=AutoApplyStrategy(),
                   max_cycles=2)
    report = engine.run()
    assert report.status is PlanStatus.FAILED
    assert engine.cycles[-1].status is CorrectionStatus.EXHAUSTED
    assert handler.calls.count("T2") == 3  # 1 + 2 correções — nunca infinito


def test_no_infinite_retry_guarantee():
    """Bound matemático: execuções da tarefa ≤ 1 + max_cycles."""
    handler = ScriptedHandler({"T2": 99})
    engine = build(two_task_plan(), handler, strategy=AutoApplyStrategy(),
                   max_cycles=3)
    engine.run()
    assert handler.calls.count("T2") == 1 + 3


def test_limits_are_validated():
    with pytest.raises(ValueError):
        build(two_task_plan(), ScriptedHandler({}), max_cycles=-1)
    with pytest.raises(ValueError):
        build(two_task_plan(), ScriptedHandler({}), max_total_attempts=0)


# --------------------------------------------------------------- checkpoints
def test_corrected_task_still_goes_through_checkpoint():
    """Checkpoints continuam valendo para a tarefa CORRIGIDA (sem bypass)."""
    handler = ScriptedHandler({"T2": 1})
    engine = build(two_task_plan(), handler, strategy=AutoApplyStrategy(),
                   checkpoints_factory=EveryTaskCheckpoints)
    engine.run()                            # pausa: checkpoint de T1
    assert engine.paused and not engine.waiting_decision
    engine.approve_checkpoint("T1 ok")
    engine.run()                            # pausa: checkpoint de T2 (original)
    assert engine.paused
    engine.approve_checkpoint("T2 original")  # roda e FALHA
    engine.run()                            # correção auto-aplica…
    assert engine.paused                    # …e pausa no checkpoint de T2'
    assert engine.current_plan.id.endswith("#C1")   # tarefa corrigida
    engine.approve_checkpoint("T2 corrigida ok")
    report = engine.run()
    assert report.status is PlanStatus.COMPLETED
    assert report.success_after_correction is True


def test_decisions_without_pending_raise():
    engine = build(two_task_plan(), ScriptedHandler({}))
    with pytest.raises(ExecutorNotPausedError):
        engine.approve_correction()
    with pytest.raises(ExecutorNotPausedError):
        engine.refuse_correction()
    with pytest.raises(ExecutorNotPausedError):
        engine.approve_checkpoint()


# ----------------------------------------------------------- imutabilidade
def test_original_plan_stays_immutable():
    original = two_task_plan()
    frozen = {t.id: (t.tool, t.description, t.parameters, t.order)
              for t in original.tasks}
    handler = ScriptedHandler({"T2": 1})
    engine = build(original, handler, strategy=AutoApplyStrategy())
    engine.run()
    successor = engine.current_plan
    assert successor is not original
    assert successor.id != original.id
    for task in original.tasks:
        assert (task.tool, task.description, task.parameters, task.order) \
            == frozen[task.id]
    # sucessor: tarefa corrigida com MESMO id + restantes; deps re-mapeadas
    corrected = successor.task_by_id("T2")
    assert corrected.tool == "fixed_tool"
    assert corrected.dependencies == ()  # T1 concluído não é carregado


# ---------------------------------------------------------------- auditoria
def test_listener_receives_every_state_change():
    seen: list[str] = []
    handler = ScriptedHandler({"T2": 1})
    engine = build(two_task_plan(), handler, strategy=SwitchToolStrategy(),
                   listener=lambda cycle: seen.append(cycle.status.value))
    engine.run()
    engine.approve_correction("vai")
    assert seen == ["PROPOSED", "APPROVED", "APPLIED", "RETRIED", "SUCCEEDED"]


def test_correction_error_and_failure_kind_separated():
    handler = ScriptedHandler({"T2": 2})  # falha, corrige, falha de novo
    engine = build(two_task_plan(), handler, strategy=AutoApplyStrategy(),
                   max_cycles=1)
    engine.run()
    kinds = [c.failure_kind for c in engine.cycles]
    assert all(kind == "execution" for kind in kinds)
    verifier_engine = build(two_task_plan(), ScriptedHandler({}),
                            strategy=SwitchToolStrategy(),
                            verifier=OnceRejectingVerifier())
    verifier_engine.run()
    assert verifier_engine.cycles[0].failure_kind == "verification"


def test_applied_correction_that_does_not_fix_ends_failed():
    """Correção aplicada que NÃO resolveu + sem nova proposta → FAILED (0.6.2)."""

    class OnceThenQuietStrategy(NoopCorrectionStrategy):
        """Propõe 1 correção (auto-apply); na 2ª análise, nada a dizer."""

        def __init__(self):
            self._proposed = False

        def propose_correction(self, task, run):
            if task.id != "T2" or self._proposed:
                return None
            self._proposed = True
            corrected = replace(task, tool="fixed_tool",
                                description=task.description + " [corrigido]")
            return CorrectionProposal(suggestion="trocar para fixed_tool",
                                      corrected_task=corrected,
                                      requires_approval=False)

    handler = ScriptedHandler({"T2": 99})  # falha sempre: correção não resolve
    engine = build(two_task_plan(), handler, strategy=OnceThenQuietStrategy())
    report = engine.run()
    assert report.status is PlanStatus.FAILED
    statuses = [(c.number, c.status) for c in engine.cycles]
    # ciclo 1 aplicado por completo; análise 2: correção não resolveu
    assert statuses == [
        (1, CorrectionStatus.PROPOSED), (1, CorrectionStatus.APPROVED),
        (1, CorrectionStatus.APPLIED), (1, CorrectionStatus.RETRIED),
        (2, CorrectionStatus.FAILED),
    ]
    assert "não resolveu" in engine.cycles[-1].decision_note
    assert handler.calls.count("T2") == 2  # original + 1 corrigida — finito
