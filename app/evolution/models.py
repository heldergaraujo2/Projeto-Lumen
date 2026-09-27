from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvolutionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvolutionState(str, Enum):
    PROPOSED = "proposed"
    RESEARCHING = "researching"
    HYPOTHESIS = "hypothesis"
    PLANNED = "planned"
    EXPERIMENTAL = "experimental"
    BUILDING = "building"
    TESTING = "testing"
    BENCHMARKING = "benchmarking"
    SECURITY_REVIEW = "security_review"
    PROMOTION_PENDING = "promotion_pending"
    REJECTED = "rejected"
    APPROVED = "approved"
    PROMOTED = "promoted"
    MONITORED = "monitored"
    ROLLED_BACK = "rolled_back"


class Decision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Capability:
    capability_id: str
    name: str
    description: str = ""
    owner: str = ""
    critical: bool = False
    enabled: bool = True

    def validate(self) -> None:
        if not self.capability_id.strip() or not self.name.strip():
            raise ValueError("capability identity is required")


@dataclass(frozen=True)
class CapabilityMeasurement:
    capability_id: str
    score: float
    metric: str
    sample_size: int = 1
    evidence: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.capability_id.strip() or not self.metric.strip():
            raise ValueError("measurement identity is required")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("measurement score must be between 0 and 1")
        if self.sample_size < 1:
            raise ValueError("sample_size must be >= 1")


@dataclass(frozen=True)
class Diagnostic:
    capability_id: str
    status: str
    findings: tuple[str, ...] = ()
    measurements: tuple[CapabilityMeasurement, ...] = ()
    severity: EvolutionRisk = EvolutionRisk.LOW

    def validate(self) -> None:
        if not self.capability_id.strip() or not self.status.strip():
            raise ValueError("diagnostic identity and status are required")
        for item in self.measurements:
            item.validate()


@dataclass(frozen=True)
class ImprovementPlan:
    evolution_id: str
    capability_id: str
    problem: str
    baseline: CapabilityMeasurement
    objective: str
    risk: EvolutionRisk = EvolutionRisk.LOW
    changes: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.evolution_id.startswith("EVOLUTION-"):
            raise ValueError("invalid evolution identifier")
        if not self.problem.strip() or not self.objective.strip():
            raise ValueError("problem and objective are required")
        self.baseline.validate()


@dataclass(frozen=True)
class Hypothesis:
    evolution_id: str
    statement: str
    rationale: str
    expected_metric: str
    expected_delta: float

    def validate(self) -> None:
        if not self.evolution_id.startswith("EVOLUTION-") or not self.statement.strip():
            raise ValueError("invalid hypothesis")
        if not self.expected_metric.strip():
            raise ValueError("expected metric is required")


@dataclass(frozen=True)
class Experiment:
    evolution_id: str
    name: str
    workspace: str
    state: EvolutionState = EvolutionState.PROPOSED
    changes: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.evolution_id.startswith("EVOLUTION-") or not self.name.strip():
            raise ValueError("experiment identity is required")
        if not self.workspace.strip():
            raise ValueError("experimental workspace is required")


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    evolution_id: str
    version: str
    artifacts: tuple[str, ...] = ()
    state: EvolutionState = EvolutionState.EXPERIMENTAL

    def validate(self) -> None:
        if not self.candidate_id.strip() or not self.evolution_id.startswith("EVOLUTION-"):
            raise ValueError("candidate identity is invalid")
        if not self.version.strip():
            raise ValueError("candidate version is required")


@dataclass(frozen=True)
class BenchmarkResult:
    candidate_id: str
    metric: str
    baseline: float
    candidate: float
    sample_size: int = 1
    evidence: tuple[str, ...] = ()

    @property
    def delta(self) -> float:
        return self.candidate - self.baseline

    def validate(self) -> None:
        if not self.candidate_id.strip() or not self.metric.strip():
            raise ValueError("benchmark identity is required")
        if self.sample_size < 1:
            raise ValueError("benchmark sample_size must be >= 1")


@dataclass(frozen=True)
class RegressionReport:
    candidate_id: str
    regressed: bool
    metrics: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class SafetyReview:
    candidate_id: str
    passed: bool
    high_risk: bool = False
    violations: tuple[str, ...] = ()
    human_approval_required: bool = False


@dataclass(frozen=True)
class PromotionDecision:
    candidate_id: str
    decision: Decision
    reason: str
    human_approved: bool = False


@dataclass(frozen=True)
class RollbackRecord:
    candidate_id: str
    previous_version: str
    reason: str
    reference: str = ""


@dataclass(frozen=True)
class EvolutionRecord:
    evolution_id: str
    capability_id: str
    problem: str
    hypothesis: str = ""
    baseline: CapabilityMeasurement | None = None
    sources: tuple[str, ...] = ()
    changes: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    metrics: tuple[BenchmarkResult, ...] = ()
    regressions: tuple[str, ...] = ()
    decision: Decision = Decision.PENDING
    evidence: tuple[str, ...] = ()
    result: str = ""
    state: EvolutionState = EvolutionState.PROPOSED

    def validate(self) -> None:
        if not self.evolution_id.startswith("EVOLUTION-") or not self.capability_id.strip():
            raise ValueError("invalid evolution record")
        if self.baseline is not None:
            self.baseline.validate()
        for metric in self.metrics:
            metric.validate()
