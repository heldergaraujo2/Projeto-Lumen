"""Correção automática CONTROLADA (Lumen 0.4.x — ligada na 0.6.2).

Loop entregue (controlado, limitado e auditável):

    EXECUTAR → VERIFICAR → SUCESSO → seguir
                       ↘ FALHA → ANALISAR → PROPOR CORREÇÃO
                         → (validar permissões/viabilidade)
                         → CHECKPOINT/APROVAÇÃO quando necessário
                         → APLICAR (plano sucessor) → RETRY → VERIFICAR

Separação de responsabilidades preservada:

- o **Planner** segue sem lógica de execução (não participa do loop);
- o **núcleo do** :class:`~app.executor.executor.PlanExecutor` **não
  muda** — :class:`CorrectionEngine` o **compõe**: cada correção gera um
  *plano sucessor* (com a tarefa corrigida + as restantes) executado por
  um novo executor; o plano original permanece **imutável**;
- a análise concreta vive em uma :class:`CorrectionStrategy` (a
  ferramenta-aware vive na camada de tools — este módulo é genérico e
  **não importa** ``app.tools``);
- a viabilidade da correção é delegada a um ``validator`` injetado
  (permissões/política) — **correção inválida nunca é aplicada** (sem
  bypass de permissões).

Limites rígidos (nunca retry infinito):

- ``max_cycles`` — número máximo de correções por execução;
- ``max_total_attempts`` — teto de tentativas (execuções) da linhagem;
- cada ciclo é registrado (:class:`CorrectionCycle`) com desfecho claro:
  ``PROPOSED`` / ``INVALID`` / ``REFUSED`` / ``APPROVED`` / ``APPLIED`` /
  ``RETRIED`` / ``SUCCEEDED`` / ``FAILED`` / ``NO_PROPOSAL`` /
  ``EXHAUSTED``;
- falha de correção ⇒ estado final ``FAILED``/``REJECTED`` apropriado.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable

from app.executor.checkpoints import CheckpointPolicy, NeverCheckpoints
from app.executor.executor import (
    ExecutionReport,
    PlanExecutor,
    TaskRun,
)
from app.executor.handlers import TaskHandler
from app.executor.retry import RetryPolicy
from app.executor.verification import TaskVerifier
from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus

logger = logging.getLogger("lumen.executor.correction")

#: Classificação da falha que motivou o ciclo.
FAILURE_KIND_EXECUTION = "execution"
FAILURE_KIND_VERIFICATION = "verification"


@dataclass(frozen=True)
class CorrectionProposal:
    """Sugestão de correção para uma tarefa que falhou.

    Args:
        suggestion: descrição legível do que fazer.
        retry_recommended: se uma nova tentativa faz sentido.
        detail: detalhe técnico opcional.
        corrected_task: tarefa corrigida (mesmo id, tool/parameters
            ajustados) que substituirá a original no **plano sucessor**.
            Sem isto a proposta é apenas conselho — o engine registra e
            encerra (nada é aplicado automaticamente).
        requires_approval: se a correção precisa de aprovação explícita
            antes de ser aplicada (default **True** — controlado).
    """

    suggestion: str
    retry_recommended: bool = True
    detail: str = ""
    corrected_task: PlannedTask | None = None
    requires_approval: bool = True

    def to_dict(self) -> dict:
        return {
            "suggestion": self.suggestion,
            "retry_recommended": self.retry_recommended,
            "detail": self.detail,
            "corrected_task": (
                self.corrected_task.to_dict() if self.corrected_task else None
            ),
            "requires_approval": self.requires_approval,
        }


class CorrectionStrategy(ABC):
    """Contrato de análise/correção de falhas (0.4.x; ligado na 0.6.2)."""

    @abstractmethod
    def propose_correction(
        self, task: PlannedTask, run: TaskRun
    ) -> CorrectionProposal | None:
        """Analisa a falha e propõe uma correção (ou ``None``)."""
        raise NotImplementedError  # pragma: no cover


class NoopCorrectionStrategy(CorrectionStrategy):
    """Estratégia padrão: não propõe correção (falha permanece falha)."""

    def propose_correction(
        self, task: PlannedTask, run: TaskRun
    ) -> CorrectionProposal | None:
        return None


class CorrectionStatus(str, Enum):
    """Desfecho de um ciclo de correção (estados claramente separados)."""

    PROPOSED = "PROPOSED"          # proposta gerada (aguardando decisão/aplicação)
    INVALID = "INVALID"            # rejeitada pela validação de permissões/viabilidade
    REFUSED = "REFUSED"            # recusada pelo usuário (nada é aplicado)
    APPROVED = "APPROVED"          # aprovada explicitamente
    APPLIED = "APPLIED"            # plano sucessor criado (correção aplicada)
    RETRIED = "RETRIED"            # nova tentativa executada (resultado no run)
    SUCCEEDED = "SUCCEEDED"        # sucesso final APÓS correção
    FAILED = "FAILED"              # falha definitiva (correção não resolveu)
    NO_PROPOSAL = "NO_PROPOSAL"    # a estratégia não propôs nada
    EXHAUSTED = "EXHAUSTED"        # limite de ciclos/tentativas atingido


@dataclass(frozen=True)
class CorrectionCycle:
    """Registro imutável de UM ciclo de correção (auditoria do loop)."""

    number: int                    # 1-based
    plan_id: str                   # plano em que a falha ocorreu
    task_id: str
    failure_kind: str              # execution | verification
    error: str | None = None
    suggestion: str | None = None
    replacement_tool: str | None = None
    decision_note: str = ""
    status: CorrectionStatus = CorrectionStatus.PROPOSED

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "failure_kind": self.failure_kind,
            "error": self.error,
            "suggestion": self.suggestion,
            "replacement_tool": self.replacement_tool,
            "decision_note": self.decision_note,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class PendingCorrection:
    """Visão da correção aguardando decisão (UX de aprovação)."""

    cycle_number: int
    task_id: str
    plan_id: str
    failure_kind: str
    error: str | None
    suggestion: str
    detail: str
    original_tool: str | None
    corrected_tool: str | None
    original_parameters: dict
    corrected_parameters: dict
    requires_approval: bool = True

    def to_dict(self) -> dict:
        return {
            "cycle_number": self.cycle_number,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "failure_kind": self.failure_kind,
            "error": self.error,
            "suggestion": self.suggestion,
            "detail": self.detail,
            "original_tool": self.original_tool,
            "corrected_tool": self.corrected_tool,
            "original_parameters": dict(self.original_parameters),
            "corrected_parameters": dict(self.corrected_parameters),
            "requires_approval": self.requires_approval,
        }


@dataclass(frozen=True)
class CorrectionReport:
    """Resultado final da execução com correções (composição de planos)."""

    execution: ExecutionReport            # último relatório do executor
    corrections: tuple[CorrectionCycle, ...] = ()
    plan_ids: tuple[str, ...] = ()        # linhagem (original → sucessores)
    success_after_correction: bool = False
    correction_pending: PendingCorrection | None = None

    @property
    def status(self) -> PlanStatus:
        return self.execution.status

    def to_dict(self) -> dict:
        return {
            "execution": self.execution.to_dict(),
            "corrections": [cycle.to_dict() for cycle in self.corrections],
            "plan_ids": list(self.plan_ids),
            "success_after_correction": self.success_after_correction,
            "correction_pending": (
                self.correction_pending.to_dict()
                if self.correction_pending else None
            ),
        }


HandlerFactory = Callable[[str], TaskHandler]
CheckpointsFactory = Callable[[], CheckpointPolicy]
VerifierFactory = Callable[[], TaskVerifier | None]
ProposalValidator = Callable[[PlannedTask], str | None]
CycleListener = Callable[[CorrectionCycle], None]


class CorrectionEngine:
    """Driver do ciclo controlado EXECUTAR→VERIFICAR→(ANALISAR→PROPOR→
    APROVAR→APLICAR→RETRY→VERIFICAR)* com limites rígidos.

    Args:
        plan: plano READY original (permanece **imutável**).
        handler_factory: ``handler_factory(plan_id)`` constrói o handler
            de cada executor (a correção nunca reusa estado de handler).
        strategy: análise de falhas → propostas.
        validator: ``validator(corrected_task)`` devolve ``None`` quando
            a correção é viável (permissões/política) ou o **motivo** do
            bloqueio — proposta inválida **nunca** é aplicada.
        checkpoints_factory: política de checkpoints por executor (as
            tarefas corrigidas continuam sujeitas a checkpoints).
        verifier_factory: verificador opcional por executor.
        retry: política de tentativas por tarefa (default 1).
        max_cycles: teto de correções aplicadas (default 2).
        max_total_attempts: teto de execuções da linhagem (default 8).
        sleeper: espera injetável (testes).
        listener: callback por mudança de estado de ciclo (auditoria).
    """

    def __init__(
        self,
        plan: Plan,
        handler_factory: HandlerFactory,
        *,
        strategy: CorrectionStrategy,
        validator: ProposalValidator | None = None,
        checkpoints_factory: CheckpointsFactory | None = None,
        verifier_factory: VerifierFactory | None = None,
        retry: RetryPolicy | None = None,
        max_cycles: int = 2,
        max_total_attempts: int = 8,
        sleeper: Callable[[float], None] = time.sleep,
        listener: CycleListener | None = None,
    ) -> None:
        if max_cycles < 0:
            raise ValueError("max_cycles deve ser >= 0.")
        if max_total_attempts < 1:
            raise ValueError("max_total_attempts deve ser >= 1 (sem retry infinito).")
        self._root_plan = plan
        self._handler_factory = handler_factory
        self._strategy = strategy
        self._validator = validator
        self._checkpoints_factory = checkpoints_factory or (lambda: NeverCheckpoints())
        self._verifier_factory = verifier_factory or (lambda: None)
        self._retry = retry if retry is not None else RetryPolicy()
        self._max_cycles = int(max_cycles)
        self._max_total_attempts = int(max_total_attempts)
        self._sleep = sleeper
        self._listener = listener
        self._plans: list[Plan] = [plan]
        self._cycles: list[CorrectionCycle] = []
        self._pending: PendingCorrection | None = None
        self._pending_proposal: CorrectionProposal | None = None
        self._pending_run: TaskRun | None = None
        self._success_after_correction = False
        self._attempts_used = 0
        self._analysis_counter = 0
        self._finished = False
        self._executor = self._build_executor(plan)

    # ------------------------------------------------------------- montagem
    def _build_executor(self, plan: Plan) -> PlanExecutor:
        return PlanExecutor(
            plan,
            self._handler_factory(plan.id),
            checkpoints=self._checkpoints_factory(),
            verifier=self._verifier_factory(),
            retry=self._retry,
            sleeper=self._sleep,
        )

    @property
    def current_plan(self) -> Plan:
        return self._plans[-1]

    @property
    def executor(self) -> PlanExecutor:
        return self._executor

    @property
    def cycles(self) -> tuple[CorrectionCycle, ...]:
        return tuple(self._cycles)

    @property
    def plan_ids(self) -> tuple[str, ...]:
        return tuple(plan.id for plan in self._plans)

    # -------------------------------------------------------------- estados
    @property
    def paused(self) -> bool:
        """Pausado em checkpoint de TAREFA (delega ao executor)."""
        return self._executor.paused

    @property
    def correction_pending(self) -> PendingCorrection | None:
        return self._pending

    @property
    def waiting_decision(self) -> bool:
        return self._pending is not None

    def _emit(self, cycle: CorrectionCycle) -> None:
        self._cycles.append(cycle)
        if self._listener is not None:
            try:
                self._listener(cycle)
            except Exception:  # listener nunca derruba o loop
                logger.exception("Listener de correção falhou (ignorado).")

    def _last_cycle(self, **changes: object) -> CorrectionCycle:
        return replace(self._cycles[-1], **changes)  # type: ignore[arg-type]

    # ------------------------------------------------------------- execução
    def run(self) -> CorrectionReport:
        """Conduz até pausa (checkpoint/correção), sucesso ou falha final."""
        while not self._finished:
            while self._executor.step() is not None:
                pass
            if self._executor.paused:
                return self.report()  # checkpoint de tarefa: decisão externa
            report = self._executor.report()
            for run in report.tasks:
                self._attempts_used += run.attempts
            if report.status is PlanStatus.COMPLETED:
                if self._cycles:
                    self._emit(self._last_cycle(status=CorrectionStatus.SUCCEEDED))
                    self._success_after_correction = True
                self._finished = True
                return self.report()
            outcome = self._handle_failure(report)
            if outcome is None:
                return self.report()  # pausa: correção aguardando decisão
            if outcome is False:
                self._finished = True
                return self.report()
            # outcome True → proposta aplicada; continua o loop (novo executor)
        return self.report()

    def _handle_failure(self, report: ExecutionReport) -> bool | None:
        """Analisa a falha.

        Devolve ``True`` se uma correção foi aplicada (loop continua),
        ``None`` se a execução pausou aguardando decisão sobre a proposta
        e ``False`` em falha definitiva (sem proposta/inválida/limites).
        """
        failed = next(
            (run for run in report.tasks
             if run.status in (PlannedTaskStatus.FAILED, PlannedTaskStatus.REJECTED)),
            None,
        )
        if failed is None:  # pragma: no cover - FAILED sempre tem run falho
            return False
        plan = self.current_plan
        task = plan.task_by_id(failed.id)
        assert task is not None
        failure_kind = (
            FAILURE_KIND_VERIFICATION
            if failed.status is PlannedTaskStatus.REJECTED
            else FAILURE_KIND_EXECUTION
        )
        self._analysis_counter += 1
        number = self._analysis_counter
        if len(self._applied_cycles()) >= self._max_cycles:
            self._emit(CorrectionCycle(
                number=number, plan_id=plan.id, task_id=task.id,
                failure_kind=failure_kind, error=failed.error,
                status=CorrectionStatus.EXHAUSTED,
                decision_note=f"limite de ciclos ({self._max_cycles}) atingido",
            ))
            return False
        if self._attempts_used >= self._max_total_attempts:
            self._emit(CorrectionCycle(
                number=number, plan_id=plan.id, task_id=task.id,
                failure_kind=failure_kind, error=failed.error,
                status=CorrectionStatus.EXHAUSTED,
                decision_note=(
                    f"limite de tentativas ({self._max_total_attempts}) atingido"
                ),
            ))
            return False

        proposal = self._strategy.propose_correction(task, failed)
        if proposal is None or proposal.corrected_task is None:
            # Sem correção aplicada antes: nada a corrigir (NO_PROPOSAL).
            # Já houve correção aplicada e mesmo assim falhou: a correção
            # não resolveu — falha definitiva do ciclo (FAILED).
            already_corrected = bool(self._applied_cycles())
            self._emit(CorrectionCycle(
                number=number, plan_id=plan.id, task_id=task.id,
                failure_kind=failure_kind, error=failed.error,
                suggestion=None if proposal is None else proposal.suggestion,
                status=(
                    CorrectionStatus.FAILED if already_corrected
                    else CorrectionStatus.NO_PROPOSAL
                ),
                decision_note=(
                    (
                        "correção aplicada não resolveu e não há nova proposta"
                        if already_corrected else
                        "estratégia sem proposta aplicável"
                    ) if proposal is None else
                    (
                        "correção aplicada não resolveu (conselho sem tarefa)"
                        if already_corrected else
                        "proposta sem tarefa corrigida (somente conselho)"
                    )
                ),
            ))
            return False

        corrected = proposal.corrected_task
        self._emit(CorrectionCycle(
            number=number, plan_id=plan.id, task_id=task.id,
            failure_kind=failure_kind, error=failed.error,
            suggestion=proposal.suggestion,
            replacement_tool=corrected.tool,
            status=CorrectionStatus.PROPOSED,
        ))
        if self._validator is not None:
            reason = self._validator(corrected)
            if reason is not None:
                self._emit(self._last_cycle(
                    status=CorrectionStatus.INVALID, decision_note=reason,
                ))
                return False
        if proposal.requires_approval:
            self._pending_proposal = proposal
            self._pending_run = failed
            self._pending = PendingCorrection(
                cycle_number=number, task_id=task.id, plan_id=plan.id,
                failure_kind=failure_kind, error=failed.error,
                suggestion=proposal.suggestion, detail=proposal.detail,
                original_tool=task.tool, corrected_tool=corrected.tool,
                original_parameters=dict(task.parameters or {}),
                corrected_parameters=dict(corrected.parameters or {}),
            )
            return None  # pausa: aguarda approve_correction/refuse_correction
        self._apply(number, proposal, failed, note="aplicação automática")
        return True

    def _apply(self, number: int, proposal: CorrectionProposal, failed: TaskRun,
               *, note: str) -> None:
        corrected = proposal.corrected_task
        assert corrected is not None
        successor = self._build_successor(failed.id, corrected)
        self._emit(self._last_cycle(
            status=CorrectionStatus.APPROVED, decision_note=note,
        ))
        self._plans.append(successor)
        self._emit(self._last_cycle(
            status=CorrectionStatus.APPLIED,
            plan_id=successor.id,  # type: ignore[arg-type]
        ))
        self._executor = self._build_executor(successor)
        self._emit(self._last_cycle(status=CorrectionStatus.RETRIED))
        logger.info(
            "Correção #%d aplicada (tarefa %s): plano sucessor %s.",
            number, failed.id, successor.id,
        )

    def _build_successor(self, failed_id: str, corrected: PlannedTask) -> Plan:
        """Plano sucessor: tarefa corrigida + restantes (deps re-mapeadas).

        O plano original permanece imutável; o sucessor é um **novo**
        ``Plan`` (id ``<original>#C<n>``). Dependências já satisfeitas em
        planos anteriores são filtradas (executam apenas as restantes).
        """
        source = self.current_plan
        order = sorted(source.tasks, key=lambda t: t.order)
        position = next(
            index for index, task in enumerate(order) if task.id == failed_id
        )
        carried: list[PlannedTask] = [
            replace(corrected, order=order[position].order)
        ]
        for task in order[position + 1:]:
            carried.append(task)
        present = {task.id for task in carried}
        remapped: list[PlannedTask] = [
            replace(
                task,
                dependencies=tuple(
                    dep for dep in task.dependencies if dep in present
                ),
            )
            for task in carried
        ]
        successor_id = f"{self._root_plan.id}#C{len(self._applied_cycles()) + 1}"
        return Plan(
            id=successor_id,
            objective=source.objective,
            status=PlanStatus.READY,
            tasks=tuple(remapped),
        )

    def _applied_cycles(self) -> list[CorrectionCycle]:
        return [c for c in self._cycles if c.status is CorrectionStatus.APPLIED]

    # ---------------------------------------------------------- decisões
    def approve_correction(self, note: str = "") -> CorrectionReport:
        """Aprova a correção pendente: aplica, retoma e verifica."""
        if self._pending is None or self._pending_proposal is None:
            raise ExecutorNotPausedError("Nenhuma correção aguardando aprovação.")
        proposal = self._pending_proposal
        failed = self._pending_run
        number = self._pending.cycle_number
        self._pending = None
        self._pending_proposal = None
        self._pending_run = None
        assert failed is not None
        self._apply(number, proposal, failed, note=note or "aprovada pelo usuário")
        return self.run()

    def refuse_correction(self, reason: str = "") -> CorrectionReport:
        """Recusa a correção pendente: **nada é aplicado** — falha definitiva."""
        if self._pending is None:
            raise ExecutorNotPausedError("Nenhuma correção aguardando decisão.")
        self._emit(self._last_cycle(
            status=CorrectionStatus.REFUSED,
            decision_note=reason or "recusada pelo usuário",
        ))
        self._pending = None
        self._pending_proposal = None
        self._pending_run = None
        self._finished = True
        return self.report()

    # ------------------------------------------------- checkpoints de tarefa
    def approve_checkpoint(self, note: str = "") -> None:
        if not self.paused:
            raise ExecutorNotPausedError("Nenhum checkpoint aguardando aprovação.")
        self._executor.approve_checkpoint(note)

    def refuse_checkpoint(self, reason: str = "") -> None:
        if not self.paused:
            raise ExecutorNotPausedError("Nenhum checkpoint aguardando decisão.")
        self._executor.refuse_checkpoint(reason)

    def report(self) -> CorrectionReport:
        return CorrectionReport(
            execution=self._executor.report(),
            corrections=tuple(self._cycles),
            plan_ids=self.plan_ids,
            success_after_correction=self._success_after_correction,
            correction_pending=self._pending,
        )


class ExecutorNotPausedError(RuntimeError):
    """Uso incorreto do engine (decisão sem pendência correspondente)."""
