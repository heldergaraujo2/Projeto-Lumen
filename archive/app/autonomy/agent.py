from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.computer_control.recovery import RecoveryAction, RecoveryDecision, RecoveryEngine
from app.computer_control.verification import VerificationStatus
from app.workflows import WorkflowMatcher, WorkflowRegistry

from .models import (
    AutonomyGrant,
    AutonomyLimits,
    AutonomousRun,
    MultiStep,
    MultiStepTask,
    RunState,
    StepResult,
    StepState,
)


class StepExecutor(Protocol):
    """Execution adapter owned by the secure runtime, never by the planner."""

    def execute(self, step: MultiStep) -> tuple[bool, str]: ...


@dataclass
class AutonomousMultiStepAgent:
    """Bounded multi-step orchestration; it never grants its own authority."""

    recovery: RecoveryEngine
    limits: AutonomyLimits
    workflows: WorkflowRegistry | None = None

    @classmethod
    def create(cls, *, limits: AutonomyLimits | None = None, workflows: WorkflowRegistry | None = None):
        effective = limits or AutonomyLimits()
        effective.validate()
        return cls(
            recovery=RecoveryEngine(max_attempts=effective.max_step_attempts - 1),
            limits=effective,
            workflows=workflows,
        )

    def validate_authorization(self, *, grant: AutonomyGrant, task: MultiStepTask) -> None:
        grant.validate()
        task.validate()
        if not grant.human_approved:
            raise PermissionError("autonomy grant requires explicit human approval")
        if grant.max_steps > self.limits.max_steps:
            raise PermissionError("autonomy grant exceeds configured autonomy limit")
        if len(task.steps) > grant.max_steps:
            raise PermissionError("task exceeds granted step budget")
        for step in task.steps:
            if step.requires_human_approval:
                raise PermissionError("task contains a step requiring additional human approval")

    def run(
        self,
        *,
        task: MultiStepTask,
        grant: AutonomyGrant,
        executor: StepExecutor,
    ) -> AutonomousRun:
        self.validate_authorization(grant=grant, task=task)
        results: list[StepResult] = []
        recoveries = 0

        for step in task.steps:
            state = StepState.RUNNING
            attempts = 0
            last_reason = ""
            last_recovery = None

            while attempts < self.limits.max_step_attempts:
                attempts += 1
                ok, reason = executor.execute(step)
                last_reason = reason
                if ok:
                    state = StepState.VERIFIED
                    break

                decision = self.recovery.decide(failure_reason=reason, attempt=attempts - 1)
                last_recovery = decision.action
                if decision.action is RecoveryAction.ABORT:
                    state = StepState.BLOCKED if decision.failure_kind.value in {"permission", "scope"} else StepState.FAILED
                    break
                recoveries += 1
                if recoveries > self.limits.max_recoveries:
                    state = StepState.FAILED
                    last_reason = "autonomy_recovery_budget_exhausted"
                    break

            results.append(
                StepResult(step.step_id, state, last_reason, attempts, last_recovery)
            )
            if state is not StepState.VERIFIED:
                final = RunState.BLOCKED if state is StepState.BLOCKED else RunState.FAILED
                return AutonomousRun(task.task_id, final, tuple(results), recoveries)

        return AutonomousRun(task.task_id, RunState.COMPLETED, tuple(results), recoveries)

    def suggest_workflow(self, *, goal: str, limit: int = 3):
        if self.workflows is None:
            return ()
        return WorkflowMatcher().match(goal, registry=self.workflows, limit=limit)
