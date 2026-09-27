from __future__ import annotations

from dataclasses import replace
from threading import RLock

from .models import (
    Candidate, Capability, CapabilityMeasurement, Decision, EvolutionRecord,
    EvolutionState, Experiment, PromotionDecision, RollbackRecord,
)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Capability] = {}
        self._measurements: dict[str, list[CapabilityMeasurement]] = {}
        self._lock = RLock()

    def register(self, capability: Capability) -> None:
        capability.validate()
        with self._lock:
            self._items[capability.capability_id] = capability

    def get(self, capability_id: str) -> Capability:
        with self._lock:
            try:
                return self._items[capability_id]
            except KeyError as exc:
                raise KeyError("unknown capability") from exc

    def measure(self, measurement: CapabilityMeasurement) -> None:
        measurement.validate()
        self.get(measurement.capability_id)
        with self._lock:
            self._measurements.setdefault(measurement.capability_id, []).append(measurement)

    def latest_measurement(self, capability_id: str) -> CapabilityMeasurement | None:
        self.get(capability_id)
        with self._lock:
            values = self._measurements.get(capability_id, [])
            return values[-1] if values else None

    def list(self) -> tuple[Capability, ...]:
        with self._lock:
            return tuple(self._items.values())


class ExperimentManager:
    _allowed = {
        EvolutionState.PROPOSED: {EvolutionState.RESEARCHING, EvolutionState.REJECTED},
        EvolutionState.RESEARCHING: {EvolutionState.HYPOTHESIS, EvolutionState.REJECTED},
        EvolutionState.HYPOTHESIS: {EvolutionState.PLANNED, EvolutionState.REJECTED},
        EvolutionState.PLANNED: {EvolutionState.EXPERIMENTAL, EvolutionState.REJECTED},
        EvolutionState.EXPERIMENTAL: {EvolutionState.BUILDING, EvolutionState.REJECTED},
        EvolutionState.BUILDING: {EvolutionState.TESTING, EvolutionState.REJECTED},
        EvolutionState.TESTING: {EvolutionState.BENCHMARKING, EvolutionState.REJECTED},
        EvolutionState.BENCHMARKING: {EvolutionState.SECURITY_REVIEW, EvolutionState.REJECTED},
        EvolutionState.SECURITY_REVIEW: {EvolutionState.PROMOTION_PENDING, EvolutionState.REJECTED},
        EvolutionState.PROMOTION_PENDING: {EvolutionState.APPROVED, EvolutionState.REJECTED},
        EvolutionState.APPROVED: {EvolutionState.PROMOTED},
        EvolutionState.PROMOTED: {EvolutionState.MONITORED, EvolutionState.ROLLED_BACK},
        EvolutionState.MONITORED: {EvolutionState.ROLLED_BACK},
    }

    def __init__(self) -> None:
        self._items: dict[str, Experiment] = {}

    def create(self, experiment: Experiment) -> None:
        experiment.validate()
        if experiment.evolution_id in self._items:
            raise ValueError("experiment already exists")
        self._items[experiment.evolution_id] = experiment

    def transition(self, evolution_id: str, state: EvolutionState) -> Experiment:
        current = self._items[evolution_id]
        if state not in self._allowed.get(current.state, set()):
            raise ValueError(f"invalid evolution transition: {current.state.value} -> {state.value}")
        updated = replace(current, state=state)
        self._items[evolution_id] = updated
        return updated

    def get(self, evolution_id: str) -> Experiment:
        return self._items[evolution_id]


class CandidateRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Candidate] = {}

    def register(self, candidate: Candidate) -> None:
        candidate.validate()
        if candidate.candidate_id in self._items:
            raise ValueError("candidate already exists")
        self._items[candidate.candidate_id] = candidate

    def get(self, candidate_id: str) -> Candidate:
        return self._items[candidate_id]

    def update_state(self, candidate_id: str, state: EvolutionState) -> Candidate:
        candidate = self.get(candidate_id)
        updated = replace(candidate, state=state)
        self._items[candidate_id] = updated
        return updated


class PromotionManager:
    def __init__(self) -> None:
        self._decisions: dict[str, PromotionDecision] = {}

    def decide(self, decision: PromotionDecision) -> None:
        if decision.decision is Decision.APPROVED and not decision.human_approved:
            raise ValueError("promotion approval requires explicit approval")
        self._decisions[decision.candidate_id] = decision

    def get(self, candidate_id: str) -> PromotionDecision | None:
        return self._decisions.get(candidate_id)


class RollbackManager:
    def __init__(self) -> None:
        self._records: list[RollbackRecord] = []

    def record(self, record: RollbackRecord) -> None:
        if not record.candidate_id.strip() or not record.previous_version.strip():
            raise ValueError("rollback record requires candidate and previous version")
        self._records.append(record)

    def history(self) -> tuple[RollbackRecord, ...]:
        return tuple(self._records)


class EvolutionMemory:
    def __init__(self) -> None:
        self._records: dict[str, EvolutionRecord] = {}

    def record(self, record: EvolutionRecord) -> None:
        record.validate()
        if record.evolution_id in self._records:
            raise ValueError("evolution record already exists")
        self._records[record.evolution_id] = record

    def update(self, record: EvolutionRecord) -> None:
        record.validate()
        if record.evolution_id not in self._records:
            raise KeyError("unknown evolution record")
        self._records[record.evolution_id] = record

    def get(self, evolution_id: str) -> EvolutionRecord:
        return self._records[evolution_id]

    def list(self) -> tuple[EvolutionRecord, ...]:
        return tuple(self._records.values())
