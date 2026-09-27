from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .diagnostics import ImprovementOpportunity, ResearchReport
from .models import Candidate, CapabilityMeasurement, EvolutionRisk, EvolutionState
from .registry import CandidateRegistry, CapabilityRegistry, EvolutionMemory


class MonitoringStatus(str, Enum):
    STABLE = "stable"
    DEGRADED = "degraded"
    REGRESSED = "regressed"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class MonitoringPolicy:
    min_samples: int = 1
    regression_tolerance: float = 0.0
    degradation_observations: int = 2
    history_limit: int = 50

    def validate(self) -> None:
        if self.min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        if self.regression_tolerance < 0:
            raise ValueError("regression_tolerance must be >= 0")
        if self.degradation_observations < 1:
            raise ValueError("degradation_observations must be >= 1")
        if self.history_limit < 1:
            raise ValueError("history_limit must be >= 1")


@dataclass(frozen=True)
class PostPromotionObservation:
    observation_id: str
    candidate_id: str
    evolution_id: str
    capability_id: str
    measurement: CapabilityMeasurement

    def validate(self) -> None:
        if not self.observation_id.strip() or not self.candidate_id.strip():
            raise ValueError("monitoring observation identity is required")
        if not self.evolution_id.startswith("EVOLUTION-"):
            raise ValueError("monitoring observation has invalid evolution identifier")
        if self.measurement.capability_id != self.capability_id:
            raise ValueError("measurement belongs to another capability")
        self.measurement.validate()


@dataclass(frozen=True)
class StabilityAssessment:
    candidate_id: str
    capability_id: str
    status: MonitoringStatus
    baseline: float | None
    latest: float | None
    delta: float | None
    sample_count: int
    degraded_streak: int
    reasons: tuple[str, ...] = ()

    @property
    def needs_improvement(self) -> bool:
        return self.status in {MonitoringStatus.DEGRADED, MonitoringStatus.REGRESSED}


@dataclass(frozen=True)
class EvolutionTrigger:
    candidate_id: str
    evolution_id: str
    capability_id: str
    reason: str
    risk: EvolutionRisk
    observation_ids: tuple[str, ...] = ()
    requires_human_approval: bool = True


class ContinuousEvolutionMonitor:
    """F16 post-promotion observation; never executes remediation or deployment."""

    def __init__(
        self,
        *,
        candidates: CandidateRegistry | None = None,
        capabilities: CapabilityRegistry | None = None,
        memory: EvolutionMemory | None = None,
        policy: MonitoringPolicy | None = None,
    ) -> None:
        self.candidates = candidates or CandidateRegistry()
        self.capabilities = capabilities or CapabilityRegistry()
        self.memory = memory or EvolutionMemory()
        self.policy = policy or MonitoringPolicy()
        self.policy.validate()
        self._observations: dict[str, list[PostPromotionObservation]] = {}
        self._baselines: dict[str, float] = {}
        self._counter = 0

    def start_monitoring(self, candidate: Candidate, *, baseline: CapabilityMeasurement) -> Candidate:
        candidate.validate()
        baseline.validate()
        if not any(c.capability_id == baseline.capability_id for c in self.capabilities.list()):
            raise ValueError("baseline capability is not registered")
        if candidate.state is not EvolutionState.PROMOTED:
            raise ValueError("candidate must be PROMOTED before monitoring")
        self.candidates.get(candidate.candidate_id)
        self._baselines[candidate.candidate_id] = baseline.score
        return self.candidates.update_state(candidate.candidate_id, EvolutionState.MONITORED)

    def _next_observation_id(self) -> str:
        self._counter += 1
        return f"MONITOR-{self._counter:06d}"

    def observe(self, candidate: Candidate, *, measurement: CapabilityMeasurement) -> StabilityAssessment:
        candidate.validate()
        measurement.validate()
        if candidate.state is not EvolutionState.MONITORED:
            raise ValueError("candidate must be MONITORED before observation")
        baseline = self._baselines.get(candidate.candidate_id)
        if baseline is None:
            raise ValueError("monitoring baseline is required")
        if measurement.sample_size < self.policy.min_samples:
            raise ValueError("monitoring sample is below required minimum")

        observation = PostPromotionObservation(
            self._next_observation_id(),
            candidate.candidate_id,
            candidate.evolution_id,
            measurement.capability_id,
            measurement,
        )
        observation.validate()
        history = self._observations.setdefault(candidate.candidate_id, [])
        history.append(observation)
        del history[:-self.policy.history_limit]

        recent = history[-self.policy.degradation_observations:]
        degraded_flags = tuple(
            item.measurement.score < baseline - self.policy.regression_tolerance
            for item in recent
        )
        streak = 0
        for flag in reversed(degraded_flags):
            if not flag:
                break
            streak += 1

        delta = measurement.score - baseline
        if measurement.score < baseline - self.policy.regression_tolerance:
            if streak >= self.policy.degradation_observations:
                status = MonitoringStatus.REGRESSED
                reasons = ("repeated post-promotion regression",)
            else:
                status = MonitoringStatus.DEGRADED
                reasons = ("post-promotion metric below baseline",)
        else:
            status = MonitoringStatus.STABLE
            reasons = ()

        return StabilityAssessment(
            candidate.candidate_id,
            measurement.capability_id,
            status,
            baseline,
            measurement.score,
            delta,
            len(history),
            streak,
            reasons,
        )

    def trigger_if_needed(
        self, candidate: Candidate, assessment: StabilityAssessment
    ) -> EvolutionTrigger | None:
        candidate.validate()
        if assessment.candidate_id != candidate.candidate_id:
            raise ValueError("assessment belongs to another candidate")
        if not assessment.needs_improvement:
            return None
        observations = self._observations.get(candidate.candidate_id, ())
        relevant = tuple(
            item.observation_id
            for item in observations[-self.policy.degradation_observations:]
        )
        risk = EvolutionRisk.HIGH if assessment.status is MonitoringStatus.REGRESSED else EvolutionRisk.MEDIUM
        return EvolutionTrigger(
            candidate.candidate_id,
            candidate.evolution_id,
            assessment.capability_id,
            assessment.reasons[0] if assessment.reasons else "post-promotion degradation",
            risk,
            relevant,
            True,
        )

    def history(self, candidate_id: str) -> tuple[PostPromotionObservation, ...]:
        return tuple(self._observations.get(candidate_id, ()))

    def baseline(self, candidate_id: str) -> float | None:
        return self._baselines.get(candidate_id)


class ContinuousEvolutionPlanner:
    """Connects a monitoring trigger to caller-supplied research evidence."""

    def create_opportunity(
        self, trigger: EvolutionTrigger, *, report: ResearchReport
    ) -> ImprovementOpportunity:
        report.validate()
        if report.query.capability_id != trigger.capability_id:
            raise ValueError("research report targets another capability")
        confidence = (
            min(1.0, sum(e.relevance for e in report.evidence) / len(report.evidence))
            if report.evidence else 0.0
        )
        return ImprovementOpportunity(
            trigger.capability_id,
            trigger.reason,
            tuple(e.evidence_id for e in report.evidence),
            confidence,
            "post-promotion monitoring identified a measurable opportunity and research supplied evidence",
        )
