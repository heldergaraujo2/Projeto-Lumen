from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any


class WorkflowRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkflowOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    INCONCLUSIVE = "inconclusive"


class WorkflowEligibility(str, Enum):
    REUSABLE = "reusable"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class WorkflowStep:
    """Learned step data only; it has no execution authority."""

    action: str
    parameters: tuple[tuple[str, Any], ...] = ()
    expectation_kind: str | None = None
    expectation_value: str | None = None
    risk: WorkflowRisk = WorkflowRisk.LOW
    rationale: str = ""

    def validate(self) -> None:
        if not self.action.strip():
            raise ValueError("workflow step action is required")
        if self.expectation_kind is not None:
            if self.expectation_kind not in {
                "target_visible", "target_absent", "window_focused",
                "state_changed", "state_unchanged",
            }:
                raise ValueError("unsupported workflow verification expectation")
            if self.expectation_kind in {"target_visible", "target_absent", "window_focused"} and not self.expectation_value:
                raise ValueError("workflow expectation value is required")
        for key, _ in self.parameters:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("workflow parameter names must be non-empty")

    def as_payload(self) -> dict[str, Any]:
        self.validate()
        return {
            "action": self.action,
            "parameters": dict(self.parameters),
            "expectation_kind": self.expectation_kind,
            "expectation_value": self.expectation_value,
            "risk": self.risk.value,
        }


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    name: str
    goal: str
    steps: tuple[WorkflowStep, ...]
    variables: tuple[str, ...] = ()
    source: str = "learned"
    version: int = 1
    enabled: bool = True

    def validate(self) -> None:
        if not self.workflow_id.strip() or not self.name.strip() or not self.goal.strip():
            raise ValueError("workflow identity and goal are required")
        if self.version < 1:
            raise ValueError("workflow version must be >= 1")
        if not self.steps:
            raise ValueError("workflow must contain at least one step")
        if len(set(self.variables)) != len(self.variables):
            raise ValueError("workflow variables must be unique")
        for variable in self.variables:
            if not variable.strip():
                raise ValueError("workflow variable cannot be blank")
        for step in self.steps:
            step.validate()

    @property
    def fingerprint(self) -> str:
        self.validate()
        payload = {
            "workflow_id": self.workflow_id,
            "name": " ".join(self.name.casefold().split()),
            "goal": " ".join(self.goal.casefold().split()),
            "steps": [step.as_payload() for step in self.steps],
            "variables": self.variables,
            "version": self.version,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @property
    def requires_human_approval(self) -> bool:
        return any(step.risk is WorkflowRisk.HIGH for step in self.steps)


@dataclass(frozen=True)
class WorkflowEvidence:
    workflow_id: str
    outcome: WorkflowOutcome
    verification_status: str
    observation_fingerprint: str
    reason: str = ""
    source: str = "runtime"
    attempt: int = 1

    def validate(self) -> None:
        if not self.workflow_id.strip() or not self.observation_fingerprint.strip():
            raise ValueError("workflow evidence requires identity and observation fingerprint")
        if self.attempt < 1:
            raise ValueError("workflow evidence attempt must be >= 1")
        if self.verification_status not in {"verified", "failed", "inconclusive"}:
            raise ValueError("invalid workflow verification status")
        if self.outcome is WorkflowOutcome.SUCCESS and self.verification_status != "verified":
            raise ValueError("successful workflow evidence requires verified status")
        if self.outcome is WorkflowOutcome.FAILURE and self.verification_status == "verified":
            raise ValueError("failed workflow evidence cannot be marked verified")


@dataclass(frozen=True)
class WorkflowStats:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    inconclusive: int = 0
    last_outcome: WorkflowOutcome | None = None

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    @property
    def eligibility(self) -> WorkflowEligibility:
        if self.attempts == 0:
            return WorkflowEligibility.INCONCLUSIVE
        if self.last_outcome is WorkflowOutcome.FAILURE:
            return WorkflowEligibility.BLOCKED
        if self.successes:
            return WorkflowEligibility.REUSABLE
        return WorkflowEligibility.INCONCLUSIVE
