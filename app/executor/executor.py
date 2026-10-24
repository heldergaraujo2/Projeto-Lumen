"""Executor de Planos (Lumen 0.4.x — fundação + checkpoints/retry/verificação).

Recebe um :class:`~app.planner.models.Plan` **pronto** (``READY``,
produzido pelo Planner) e executa suas tarefas de maneira controlada e
determinística, **exclusivamente via handlers simulados/in-memory**.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable

from app.executor.checkpoints import (
    CheckpointPolicy,
    CheckpointRequest,
    CheckpointStatus,
    NeverCheckpoints,
)
from app.executor.handlers import HandlerError, TaskHandler
from app.executor.retry import AttemptRecord, RetryPolicy
from app.executor.verification import TaskVerifier, VerificationResult
from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus

# ------------------------------------------------------------- data-flow (8B)
_DATA_REF_PATTERN = re.compile(r"\$\{T(\d+)\.data\.([A-Za-z_][A-Za-z0-9_]*)\}")

_EXPORTABLE_FIELDS: dict[str, frozenset[str]] = {
    "read_file": frozenset({"content", "resolved_path"}),
}

_MAX_RESOLVED_BYTES = 16 * 1024
_MAX_REFERENCES_PER_PARAMETER = 4

logger = logging.getLogger("lumen.executor")

Sleeper = Callable[[float], None]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutorError(RuntimeError):
    """Falha do Executor (plano inválido para execução, uso incorreto)."""


@dataclass(frozen=True)
class ExecutionEvent:
    """Evento imutável da linha do tempo de execução."""

    kind: str
    task_id: str | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "task_id": self.task_id, "detail": self.detail}


@dataclass(frozen=True)
class TaskRun:
    """Estado de execução de UMA tarefa (snapshot do progresso)."""

    id: str
    description: str
    order: int
    dependencies: tuple[str, ...]
    status: PlannedTaskStatus = PlannedTaskStatus.PENDING
    result: str | None = None
    error: str | None = None
    attempts: int = 0
    verified: bool | None = None
    attempt_log: tuple[AttemptRecord, ...] = ()
    conversation_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "order": self.order,
            "dependencies": list(self.dependencies),
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
            "verified": self.verified,
            "attempt_log": [attempt.to_dict() for attempt in self.attempt_log],
            "conversation_id": self.conversation_id,
        }


@dataclass(frozen=True)
class ExecutionReport:
    """Resultado (parcial ou final) da execução de um plano."""

    plan_id: str
    objective: str
    status: PlanStatus
    tasks: tuple[TaskRun, ...]
    events: tuple[ExecutionEvent, ...]
    error: str | None = None
    started_at: str = ""
    finished_at: str = ""
    checkpoints: tuple[CheckpointRequest, ...] = ()
    pending_checkpoint: CheckpointRequest | None = None
    conversation_id: str | None = None

    @property
    def completed(self) -> bool:
        return self.status is PlanStatus.COMPLETED

    def task_run(self, task_id: str) -> TaskRun:
        for run in self.tasks:
            if run.id == task_id:
                return run
        raise ExecutorError(f"Tarefa {task_id!r} não existe no relatório.")

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "objective": self.objective,
            "status": self.status.value,
            "tasks": [run.to_dict() for run in self.tasks],
            "events": [event.to_dict() for event in self.events],
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "pending_checkpoint": (
                self.pending_checkpoint.to_dict() if self.pending_checkpoint else None
            ),
            "conversation_id": self.conversation_id,
        }


class ExecutionObserver:
    """Gancho para observadores de execução (NO-OP por padrão)."""

    def on_task_started(self, run: TaskRun) -> None:
        """Chamado antes de cada tarefa elegível ser executada."""

    def on_task_finished(self, run: TaskRun) -> None:
        """Chamado após cada tarefa terminar."""

    def on_plan_finished(self, report: ExecutionReport) -> None:
        """Chamado quando o plano atinge um estado terminal."""


class PlanExecutor:
    """Executa um plano ``READY`` tarefa por tarefa, de forma controlada."""

    def __init__(
        self,
        plan: Plan,
        handler: TaskHandler,
        observer: ExecutionObserver | None = None,
        *,
        verifier: TaskVerifier | None = None,
        retry: RetryPolicy | None = None,
        checkpoints: CheckpointPolicy | None = None,
        sleeper: Sleeper = time.sleep,
        conversation_id: str | None = None,
        initial_runs: Mapping[str, TaskRun] | None = None,
    ) -> None:
        self._validate_plan(plan)
        self._plan = plan
        self._handler = handler
        self._observer = observer or ExecutionObserver()
        self._verifier = verifier
        self._retry = retry if retry is not None else RetryPolicy()
        self._checkpoint_policy = (
            checkpoints if checkpoints is not None else NeverCheckpoints()
        )
        self._sleep = sleeper
        self._conversation_id = conversation_id or getattr(
            plan, "conversation_id", None
        )
        self._runs: dict[str, TaskRun] = {}
        for task in sorted(plan.tasks, key=lambda t: t.order):
            if initial_runs and task.id in initial_runs:
                self._runs[task.id] = initial_runs[task.id]
            else:
                self._runs[task.id] = TaskRun(
                    id=task.id,
                    description=task.description,
                    order=task.order,
                    dependencies=tuple(task.dependencies),
                    conversation_id=self._conversation_id,
                )
        self._events: list[ExecutionEvent] = []
        self._status = PlanStatus.RUNNING
        self._started_at = _now_iso()
        self._finished_at: str | None = None
        self._checkpoint_requests: list[CheckpointRequest] = []
        self._pending: CheckpointRequest | None = None
        self._approved_checkpoints: set[str] = set()
        self._checkpoint_counter = 0
        self._failure_reason: str | None = None
        logger.info(
            "Executor montado para o plano %s (%d tarefas, handler=%s, "
            "retry=%d tentativa(s), verifier=%s, checkpoints=%s).",
            plan.id, len(self._runs), handler.name, self._retry.max_attempts,
            getattr(self._verifier, "name", None) or "nenhum",
            type(self._checkpoint_policy).__name__,
        )

    @staticmethod
    def _validate_plan(plan: Plan) -> None:
        if plan.status is not PlanStatus.READY:
            raise ExecutorError(
                f"O plano {plan.id} não está pronto para execução "
                f"(status={plan.status.value}; esperado READY)."
            )
        if not plan.tasks:
            raise ExecutorError(f"O plano {plan.id} não possui tarefas.")
        ids = {task.id for task in plan.tasks}
        for task in plan.tasks:
            for dep in task.dependencies:
                if dep not in ids:
                    raise ExecutorError(
                        f"O plano {plan.id} é inválido: a tarefa {task.id} "
                        f"depende de {dep!r}, que não existe."
                    )
        PlanExecutor._ensure_acyclic(plan)

    @staticmethod
    def _ensure_acyclic(plan: Plan) -> None:
        dependents: dict[str, list[str]] = {task.id: [] for task in plan.tasks}
        in_degree: dict[str, int] = {task.id: 0 for task in plan.tasks}
        for task in plan.tasks:
            for dep in task.dependencies:
                dependents[dep].append(task.id)
                in_degree[task.id] += 1
        queue = deque(t for t, degree in in_degree.items() if degree == 0)
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for dependent in dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        if visited != len(plan.tasks):
            raise ExecutorError(
                f"O plano {plan.id} é inválido: dependências cíclicas."
            )

    @property
    def status(self) -> PlanStatus:
        return self._status

    @property
    def finished(self) -> bool:
        return self._finished_at is not None

    @property
    def paused(self) -> bool:
        return self._pending is not None and not self.finished

    @property
    def pending_checkpoint(self) -> CheckpointRequest | None:
        return self._pending

    def _next_eligible(self) -> TaskRun | None:
        for run in sorted(self._runs.values(), key=lambda r: r.order):
            if run.status is not PlannedTaskStatus.PENDING:
                continue
            if all(
                self._runs[dep].status is PlannedTaskStatus.DONE
                for dep in run.dependencies
            ):
                return run
        return None

    def approve_checkpoint(self, note: str = "") -> CheckpointRequest:
        if self._pending is None:
            raise ExecutorError("Nenhum checkpoint aguardando aprovação.")
        approved = replace(
            self._pending,
            status=CheckpointStatus.APPROVED,
            note=note,
            decided_at=_now_iso(),
        )
        self._replace_checkpoint(approved)
        self._approved_checkpoints.add(approved.task_id)
        task_id = approved.task_id
        self._pending = None
        self._record("checkpoint_approved", task_id, approved.id)
        logger.info("Checkpoint %s aprovado (tarefa %s).", approved.id, task_id)
        return approved

    def refuse_checkpoint(self, reason: str = "") -> CheckpointRequest:
        if self._pending is None:
            raise ExecutorError("Nenhum checkpoint aguardando decisão.")
        refused = replace(
            self._pending,
            status=CheckpointStatus.REFUSED,
            note=reason,
            decided_at=_now_iso(),
        )
        self._replace_checkpoint(refused)
        task_id = refused.task_id
        self._pending = None
        self._record("checkpoint_refused", task_id, refused.id)
        logger.warning("Checkpoint %s recusado (tarefa %s).", refused.id, task_id)

        message = "Checkpoint recusado" + (f": {reason}" if reason else "") + "."
        run = self._runs.get(task_id)
        if run is not None and run.status is PlannedTaskStatus.PENDING:
            skipped = replace(
                run, status=PlannedTaskStatus.SKIPPED,
                error=f"{message} A tarefa não foi executada.",
            )
            self._runs[task_id] = skipped
            self._record("task_skipped", task_id)
        self._interrupt(message)
        return refused

    def _replace_checkpoint(self, request: CheckpointRequest) -> None:
        self._checkpoint_requests = [
            request if item.id == request.id else item
            for item in self._checkpoint_requests
        ]

    def _maybe_checkpoint(self, run: TaskRun) -> bool:
        task = self._plan.task_by_id(run.id)
        if not self._checkpoint_policy.requires_checkpoint(task):
            return False
        if run.id in self._approved_checkpoints:
            return False
        if self._pending is not None and self._pending.task_id == run.id:
            return True
        self._checkpoint_counter += 1
        self._pending = CheckpointRequest(
            id=f"CP-{self._checkpoint_counter:04d}",
            task_id=run.id,
            reason=task.description,
        )
        self._checkpoint_requests.append(self._pending)
        self._record("checkpoint_requested", run.id, self._pending.id)
        logger.info(
            "Checkpoint %s solicitado antes da tarefa %s — execução pausada.",
            self._pending.id, run.id,
        )
        return True

    @staticmethod
    def _resolve_references(
        parameters: dict,
        prior_runs: dict[str, "TaskRun"],
        *,
        task: PlannedTask | None = None,
        tools_by_id: dict[str, str] | None = None,
    ) -> dict:
        resolved = dict(parameters or {})
        for key, value in list(resolved.items()):
            if not isinstance(value, str) or not _DATA_REF_PATTERN.search(value):
                continue
            references = _DATA_REF_PATTERN.findall(value)
            if len(references) > _MAX_REFERENCES_PER_PARAMETER:
                raise ExecutorError(
                    f"Parâmetro {key!r} usa {len(references)} referências de "
                    f"dados (máximo {_MAX_REFERENCES_PER_PARAMETER})."
                )
            whole = _DATA_REF_PATTERN.fullmatch(value)
            if whole is not None:
                value = PlanExecutor._reference_value(
                    whole, prior_runs, task=task, tools_by_id=tools_by_id,
                )
            else:
                value = _DATA_REF_PATTERN.sub(
                    lambda match: PlanExecutor._text_of(PlanExecutor._reference_value(
                        match, prior_runs, task=task, tools_by_id=tools_by_id,
                    )),
                    value,
                )
            if isinstance(value, str):
                size = len(value.encode("utf-8"))
                if size > _MAX_RESOLVED_BYTES:
                    raise ExecutorError(
                        f"Parâmetro {key!r} resolvido excede o limite de "
                        f"{_MAX_RESOLVED_BYTES} bytes ({size} bytes)."
                    )
            resolved[key] = value
        return resolved

    @staticmethod
    def _reference_value(
        match: "re.Match[str]",
        prior_runs: dict[str, "TaskRun"],
        *,
        task: PlannedTask | None,
        tools_by_id: dict[str, str] | None,
    ):
        referenced = f"T{match.group(1)}"
        field = match.group(2)
        if task is not None and referenced not in task.dependencies:
            raise ExecutorError(
                f"A tarefa {task.id} referencia {referenced} sem dependência "
                "declarada — referência de dados exige dependência explícita."
            )
        if tools_by_id is not None and referenced not in tools_by_id:
            raise ExecutorError(
                f"Referência a tarefa inexistente no plano: {referenced}."
            )
        prior = prior_runs.get(referenced)
        if prior is None or prior.status is not PlannedTaskStatus.DONE:
            raise ExecutorError(
                f"Referência {referenced}.{field}: a tarefa referida não "
                "está concluída (DONE)."
            )
        tool = (tools_by_id or {}).get(referenced) or ""
        if field not in _EXPORTABLE_FIELDS.get(tool, frozenset()):
            raise ExecutorError(
                f"Campo {field!r} do resultado de {referenced} "
                f"(ferramenta {tool!r}) não é exportável (allowlist)."
            )
        try:
            payload = json.loads(prior.result) if prior.result else None
        except ValueError:
            payload = None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or field not in data:
            raise ExecutorError(
                f"Campo {field!r} ausente no resultado de {referenced}."
            )
        return data[field]

    @staticmethod
    def _text_of(value: object) -> str:
        if not isinstance(value, str):
            raise ExecutorError(
                "Somente campos textuais podem ser interpolados no meio de "
                "um texto; use a referência sozinha para outros tipos."
            )
        return value

    def step(self) -> TaskRun | None:
        if self.finished:
            return None
        run = self._next_eligible()
        if run is None:
            self._finish()
            return None

        task = self._plan.task_by_id(run.id)
        if task is not None:
            try:
                resolved_params = self._resolve_references(
                    dict(task.parameters or {}),
                    {
                        task_id: done_run
                        for task_id, done_run in self._runs.items()
                        if done_run.status is PlannedTaskStatus.DONE
                    },
                    task=task,
                    tools_by_id={
                        planned.id: (planned.tool or "")
                        for planned in self._plan.tasks
                    },
                )
            except ExecutorError as exc:
                message = f"Referência de dados inválida: {exc}"
                logger.error(
                    "Tarefa %s no plano %s: %s", run.id, self._plan.id, message,
                )
                final = replace(
                    run, status=PlannedTaskStatus.FAILED, error=message,
                )
                self._runs[run.id] = final
                self._record("task_failed", run.id, message)
                self._interrupt(message)
                return final
            if isinstance(task.parameters, dict) and task.parameters != resolved_params:
                task.parameters.clear()
                task.parameters.update(resolved_params)

        if self._maybe_checkpoint(run):
            return None

        self._record("task_started", run.id)
        self._observer.on_task_started(run)
        final = self._execute_with_retry(run)
        self._runs[run.id] = final
        self._observer.on_task_finished(final)

        if final.status is PlannedTaskStatus.DONE:
            self._record("task_completed", run.id)
            if final.verified:
                self._record("task_verification_passed", run.id)
            if self._next_eligible() is None:
                self._finish()
            return final

        if final.status is PlannedTaskStatus.REJECTED:
            self._record("task_verification_failed", run.id, final.error or "")
            logger.error(
                "Tarefa %s reprovada na verificação (plano %s): %s",
                run.id, self._plan.id, final.error,
            )
            self._interrupt(final.error or "reprovada na verificação")
            return final

        self._record("task_failed", run.id, final.error or "")
        logger.error(
            "Tarefa %s falhou no plano %s após %d tentativa(s): %s",
            run.id, self._plan.id, final.attempts, final.error,
        )
        self._interrupt(final.error or "falha de execução")
        return final

    def _execute_with_retry(self, run: TaskRun) -> TaskRun:
        task = self._plan.task_by_id(run.id)
        attempt_log: list[AttemptRecord] = []
        for attempt in range(1, self._retry.max_attempts + 1):
            if attempt > 1:
                delay = self._retry.backoff_seconds * (attempt - 1)
                if delay > 0:
                    self._sleep(delay)
            try:
                result = self._handler.execute(task)
            except HandlerError as exc:
                attempt_log.append(
                    AttemptRecord(number=attempt, error=str(exc))
                )
                if attempt < self._retry.max_attempts:
                    self._record(
                        "task_retry", run.id,
                        f"tentativa {attempt} falhou; repetindo "
                        f"({self._retry.max_attempts - attempt} restante(s))",
                    )
                    continue
                return replace(
                    run, status=PlannedTaskStatus.FAILED, error=str(exc),
                    attempts=attempt, attempt_log=tuple(attempt_log),
                )
            except Exception as exc:
                error = f"Erro inesperado do handler: {exc}"
                attempt_log.append(
                    AttemptRecord(number=attempt, error=error)
                )
                return replace(
                    run, status=PlannedTaskStatus.FAILED, error=error,
                    attempts=attempt, attempt_log=tuple(attempt_log),
                )

            attempt_log.append(AttemptRecord(number=attempt, result=result))
            if self._verifier is not None:
                try:
                    outcome = self._verifier.verify(task, result)
                except Exception as exc:
                    outcome = VerificationResult(
                        passed=False, detail=f"verificador falhou: {exc}"
                    )
                if outcome.applied and not outcome.passed:
                    return replace(
                        run, status=PlannedTaskStatus.REJECTED,
                        result=result, verified=False,
                        error=f"Verificação falhou: {outcome.detail}",
                        attempts=attempt, attempt_log=tuple(attempt_log),
                    )
                if outcome.applied:
                    return replace(
                        run, status=PlannedTaskStatus.DONE, result=result,
                        verified=True, attempts=attempt,
                        attempt_log=tuple(attempt_log),
                    )
            return replace(
                run, status=PlannedTaskStatus.DONE, result=result,
                attempts=attempt, attempt_log=tuple(attempt_log),
            )
        raise ExecutorError("Loop de tentativas encerrado sem resultado.")

    def run_all(self) -> ExecutionReport:
        while self.step() is not None:
            pass
        return self.report()

    def _interrupt(self, reason: str) -> None:
        for run in sorted(self._runs.values(), key=lambda r: r.order):
            if run.status is PlannedTaskStatus.PENDING:
                skipped = replace(
                    run, status=PlannedTaskStatus.SKIPPED,
                    error="Interrompida: o plano foi abortado por uma falha "
                          f"anterior ({reason}).",
                )
                self._runs[run.id] = skipped
                self._record("task_skipped", run.id)
        self._finish(failed=True, error=reason)

    def _finish(self, failed: bool = False, error: str | None = None) -> None:
        if self.finished:
            return
        self._finished_at = _now_iso()
        if failed:
            self._status = PlanStatus.FAILED
            self._failure_reason = error or self._failure_reason
        elif all(r.status is PlannedTaskStatus.DONE for r in self._runs.values()):
            self._status = PlanStatus.COMPLETED
        else:
            self._status = PlanStatus.FAILED
            error = error or "Plano encerrado com tarefas pendentes."
        self._record("plan_finished", None, self._status.value)
        logger.info("Plano %s finalizado: %s.", self._plan.id, self._status.value)
        self._observer.on_plan_finished(self.report())

    def _record(self, kind: str, task_id: str | None, detail: str = "") -> None:
        self._events.append(
            ExecutionEvent(kind=kind, task_id=task_id, detail=detail)
        )

    def report(self) -> ExecutionReport:
        tasks = tuple(sorted(self._runs.values(), key=lambda r: r.order))
        error = None
        if self._status is PlanStatus.FAILED:
            failures = [
                r for r in tasks
                if r.status in (PlannedTaskStatus.FAILED, PlannedTaskStatus.REJECTED)
            ]
            error = self._failure_reason or (
                failures[0].error if failures else "Execução interrompida."
            )
        return ExecutionReport(
            plan_id=self._plan.id,
            objective=self._plan.objective,
            status=self._status,
            tasks=tasks,
            events=tuple(self._events),
            error=error,
            started_at=self._started_at,
            finished_at=self._finished_at or "",
            checkpoints=tuple(self._checkpoint_requests),
            pending_checkpoint=self._pending,
            conversation_id=self._conversation_id,
        )
