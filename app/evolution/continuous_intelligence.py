from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from .continuous import MonitoringStatus
from .models import EvolutionRisk


class IntelligenceCycleState(str, Enum):
    OBSERVED = "observed"
    ASSESSED = "assessed"
    TRIGGERED = "triggered"
    PLANNED = "planned"
    WAITING_GATES = "waiting_gates"
    CLOSED = "closed"


@dataclass(frozen=True)
class IntelligenceObservation:
    observation_id: str
    capability_id: str
    score: float
    sample_size: int
    source: str
    baseline_score: float

    def validate(self) -> None:
        if not self.observation_id.startswith("CI-EV-"):
            raise ValueError("invalid continuous intelligence evidence identifier")
        if not self.capability_id.strip() or not self.source.strip():
            raise ValueError("observation identity and source are required")
        if not 0.0 <= self.score <= 1.0 or not 0.0 <= self.baseline_score <= 1.0:
            raise ValueError("observation scores must be between 0 and 1")
        if self.sample_size < 1:
            raise ValueError("observation sample_size must be >= 1")


@dataclass(frozen=True)
class IntelligenceCycle:
    cycle_id: str
    capability_id: str
    state: IntelligenceCycleState
    baseline_score: float
    latest_score: float | None = None
    observation_ids: tuple[str, ...] = ()
    trigger_reason: str = ""
    risk: EvolutionRisk = EvolutionRisk.MEDIUM
    requires_human_approval: bool = True

    def validate(self) -> None:
        if not self.cycle_id.startswith("CI-CYCLE-"):
            raise ValueError("invalid continuous intelligence cycle identifier")
        if not self.capability_id.strip():
            raise ValueError("cycle capability is required")
        if not 0.0 <= self.baseline_score <= 1.0:
            raise ValueError("cycle baseline must be between 0 and 1")
        if self.latest_score is not None and not 0.0 <= self.latest_score <= 1.0:
            raise ValueError("cycle latest score must be between 0 and 1")
        if self.state in {IntelligenceCycleState.TRIGGERED, IntelligenceCycleState.PLANNED, IntelligenceCycleState.WAITING_GATES} and not self.trigger_reason.strip():
            raise ValueError("triggered cycles require a reason")
        if self.state is not IntelligenceCycleState.CLOSED and not self.requires_human_approval:
            raise ValueError("continuous intelligence cycles require human approval")


@dataclass(frozen=True)
class IntelligenceTrigger:
    trigger_id: str
    cycle_id: str
    capability_id: str
    status: MonitoringStatus
    reason: str
    risk: EvolutionRisk
    evidence_ids: tuple[str, ...]
    starts_new_cycle: bool = True

    def validate(self) -> None:
        if not self.trigger_id.startswith("CI-TRIGGER-") or not self.cycle_id.startswith("CI-CYCLE-"):
            raise ValueError("invalid continuous intelligence trigger identity")
        if not self.capability_id.strip() or not self.reason.strip():
            raise ValueError("trigger requires capability and reason")
        if not self.evidence_ids:
            raise ValueError("trigger requires evidence")


@dataclass(frozen=True)
class ContinuousIntelligencePlan:
    plan_id: str
    source_trigger_id: str
    capability_id: str
    actions: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    isolated: bool = True
    requires_human_approval: bool = True

    def validate(self) -> None:
        if not self.plan_id.startswith("CI-PLAN-") or not self.source_trigger_id.startswith("CI-TRIGGER-"):
            raise ValueError("invalid continuous intelligence plan identity")
        if not self.capability_id.strip() or not self.actions or not self.evidence_ids:
            raise ValueError("continuous intelligence plan is incomplete")
        if not self.isolated:
            raise ValueError("continuous intelligence plans must remain isolated")
        if not self.requires_human_approval:
            raise ValueError("continuous intelligence plans require human approval")


class ContinuousIntelligenceEvolution:
    """F22 closed-loop intelligence evolution coordinator.

    It observes caller-supplied measurements, detects degradation and creates
    bounded plans for the existing F12-F21 gates. It never executes remediation.
    """

    def __init__(self, *, min_samples: int = 1, degradation_threshold: float = 0.0, history_limit: int = 100) -> None:
        if min_samples < 1 or history_limit < 1 or degradation_threshold < 0:
            raise ValueError("invalid continuous intelligence policy")
        self.min_samples = min_samples
        self.degradation_threshold = degradation_threshold
        self.history_limit = history_limit
        self._observations: dict[str, IntelligenceObservation] = {}
        self._cycles: dict[str, IntelligenceCycle] = {}
        self._triggers: dict[str, IntelligenceTrigger] = {}
        self._plans: dict[str, ContinuousIntelligencePlan] = {}
        self._counter = 0

    def _id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter:06d}"

    def observe(self, observation: IntelligenceObservation) -> IntelligenceObservation:
        observation.validate()
        if observation.sample_size < self.min_samples:
            raise ValueError("observation sample is below minimum")
        if observation.observation_id in self._observations:
            raise ValueError("observation already exists")
        self._observations[observation.observation_id] = observation
        if len(self._observations) > self.history_limit:
            oldest = next(iter(self._observations))
            del self._observations[oldest]
        return observation

    def start_cycle(self, capability_id: str, baseline_score: float) -> IntelligenceCycle:
        if not capability_id.strip() or not 0.0 <= baseline_score <= 1.0:
            raise ValueError("invalid intelligence cycle baseline")
        cycle = IntelligenceCycle(self._id("CI-CYCLE-"), capability_id, IntelligenceCycleState.OBSERVED, baseline_score)
        cycle.validate()
        self._cycles[cycle.cycle_id] = cycle
        return cycle

    def assess(self, cycle_id: str, observation: IntelligenceObservation) -> IntelligenceCycle:
        cycle = self._cycles[cycle_id]
        observation.validate()
        if observation.sample_size < self.min_samples:
            raise ValueError("observation sample is below minimum")
        if observation.capability_id != cycle.capability_id:
            raise ValueError("observation targets another capability")
        if observation.baseline_score != cycle.baseline_score:
            raise ValueError("observation baseline differs from cycle baseline")
        if observation.observation_id not in self._observations:
            self.observe(observation)
        degraded = observation.score < cycle.baseline_score - self.degradation_threshold
        state = IntelligenceCycleState.TRIGGERED if degraded else IntelligenceCycleState.ASSESSED
        reason = "continuous intelligence degradation detected" if degraded else "observation remains within baseline tolerance"
        updated = IntelligenceCycle(cycle.cycle_id, cycle.capability_id, state, cycle.baseline_score, observation.score, cycle.observation_ids + (observation.observation_id,), reason, EvolutionRisk.HIGH if degraded else EvolutionRisk.MEDIUM)
        updated.validate()
        self._cycles[cycle_id] = updated
        return updated

    def trigger(self, cycle_id: str) -> IntelligenceTrigger | None:
        cycle = self._cycles[cycle_id]
        if cycle.state is not IntelligenceCycleState.TRIGGERED:
            return None
        if any(t.cycle_id == cycle_id for t in self._triggers.values()):
            raise ValueError("cycle already has a trigger")
        trigger = IntelligenceTrigger(self._id("CI-TRIGGER-"), cycle.cycle_id, cycle.capability_id, MonitoringStatus.REGRESSED, cycle.trigger_reason, cycle.risk, cycle.observation_ids)
        trigger.validate()
        self._triggers[trigger.trigger_id] = trigger
        return trigger

    def plan(self, trigger: IntelligenceTrigger, *, actions: tuple[str, ...]) -> ContinuousIntelligencePlan:
        trigger.validate()
        if trigger.trigger_id not in self._triggers:
            raise KeyError("unknown trigger")
        if any(p.source_trigger_id == trigger.trigger_id for p in self._plans.values()):
            raise ValueError("trigger already has a plan")
        plan = ContinuousIntelligencePlan(self._id("CI-PLAN-"), trigger.trigger_id, trigger.capability_id, actions, trigger.evidence_ids)
        plan.validate()
        self._plans[plan.plan_id] = plan
        cycle = self._cycles[trigger.cycle_id]
        self._cycles[trigger.cycle_id] = IntelligenceCycle(cycle.cycle_id, cycle.capability_id, IntelligenceCycleState.WAITING_GATES, cycle.baseline_score, cycle.latest_score, cycle.observation_ids, cycle.trigger_reason, cycle.risk)
        return plan

    def digest(self) -> str:
        payload = {
            "observations": sorted((x.observation_id, x.capability_id, x.score, x.sample_size, x.baseline_score) for x in self._observations.values()),
            "cycles": sorted((x.cycle_id, x.capability_id, x.state.value, x.baseline_score, x.latest_score, x.observation_ids) for x in self._cycles.values()),
            "triggers": sorted((x.trigger_id, x.cycle_id, x.status.value, x.evidence_ids) for x in self._triggers.values()),
            "plans": sorted((x.plan_id, x.source_trigger_id, x.actions, x.evidence_ids) for x in self._plans.values()),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def counts(self) -> dict[str, int]:
        return {"observations": len(self._observations), "cycles": len(self._cycles), "triggers": len(self._triggers), "plans": len(self._plans)}