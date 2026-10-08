from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.computer_control.recovery import RecoveryAction


class StepState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    VERIFIED = "verified"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"


class RunState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class AutonomyLimits:
    max_steps: int = 20
    max_recoveries: int = 3
    max_step_attempts: int = 3

    def validate(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        if self.max_recoveries < 0:
            raise ValueError("max_recoveries must be >= 0")
        if self.max_step_attempts < 1:
            raise ValueError("max_step_attempts must be >= 1")


@dataclass(frozen=True)
class AutonomyGrant:
    grant_id: str
    scope_id: str
    max_steps: int
    human_approved: bool = False

    def validate(self) -> None:
        if not self.grant_id.strip() or not self.scope_id.strip():
            raise ValueError("autonomy grant identity is required")
        if self.max_steps < 1:
            raise ValueError("autonomy grant max_steps must be >= 1")


@dataclass(frozen=True)
class MultiStep:
    step_id: str
    description: str
    action: object
    requires_human_approval: bool = False

    def validate(self) -> None:
        if not self.step_id.strip() or not self.description.strip():
            raise ValueError("step identity and description are required")
        if self.action is None:
            raise ValueError("step action is required")


@dataclass(frozen=True)
class MultiStepTask:
    task_id: str
    goal: str
    steps: tuple[MultiStep, ...]

    def validate(self) -> None:
        if not self.task_id.strip() or not self.goal.strip():
            raise ValueError("task identity and goal are required")
        if not self.steps:
            raise ValueError("task requires at least one step")
        seen: set[str] = set()
        for step in self.steps:
            step.validate()
            if step.step_id in seen:
                raise ValueError("task step ids must be unique")
            seen.add(step.step_id)


@dataclass(frozen=True)
class StepResult:
    step_id: str
    state: StepState
    reason: str
    attempts: int = 0
    recovery: RecoveryAction | None = None


@dataclass(frozen=True)
class AutonomousRun:
    task_id: str
    state: RunState
    steps: tuple[StepResult, ...]
    recoveries: int = 0

    @property
    def completed_steps(self) -> int:
        return sum(x.state is StepState.VERIFIED for x in self.steps)
