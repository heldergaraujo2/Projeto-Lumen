"""F32 — Closed-Loop Lumen Evolution.

Coordinates the existing F16/F22 monitoring and F24 evolution gates into one
bounded, durable state machine. It consumes caller-supplied evidence and emits
the next safe gate; it never executes remediation, providers, tools, drivers,
experiments, builds, deployments, or promotion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any

from .continuous import ContinuousEvolutionMonitor, StabilityAssessment
from .continuous_intelligence import (
    ContinuousIntelligenceEvolution,
    IntelligenceCycleState,
    IntelligenceObservation,
    IntelligenceTrigger,
)
from .models import CapabilityMeasurement, EvolutionRisk
from .orchestrator import EvolutionRuntimeOrchestrator, OrchestrationContext


class ClosedLoopState(str):
    OBSERVING = "observing"
    STABLE = "stable"
    TRIGGERED = "triggered"
    PLANNED = "planned"
    WAITING_EVIDENCE = "waiting_evidence"
    WAITING_APPROVAL = "waiting_approval"
    PROMOTED = "promoted"
    MONITORED = "monitored"
    CLOSED = "closed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ClosedLoopRecord:
    loop_id: str
    capability_id: str
    state: str
    baseline_score: float
    latest_score: float | None = None
    risk: EvolutionRisk = EvolutionRisk.MEDIUM
    reason: str = ""
    observation_ids: tuple[str, ...] = ()
    trigger_id: str | None = None
    plan_id: str | None = None
    evolution_id: str | None = None
    approval_required: bool = True

    def validate(self) -> None:
        if not self.loop_id.startswith("LOOP-"):
            raise ValueError("invalid closed-loop identity")
        if not self.capability_id.strip():
            raise ValueError("closed-loop capability is required")
        if not 0.0 <= self.baseline_score <= 1.0:
            raise ValueError("baseline must be between 0 and 1")
        if self.latest_score is not None and not 0.0 <= self.latest_score <= 1.0:
            raise ValueError("latest score must be between 0 and 1")
        if self.state not in {
            ClosedLoopState.OBSERVING, ClosedLoopState.STABLE, ClosedLoopState.TRIGGERED,
            ClosedLoopState.PLANNED, ClosedLoopState.WAITING_EVIDENCE,
            ClosedLoopState.WAITING_APPROVAL, ClosedLoopState.PROMOTED,
            ClosedLoopState.MONITORED, ClosedLoopState.CLOSED, ClosedLoopState.REJECTED,
        }:
            raise ValueError("invalid closed-loop state")
        if self.state not in {ClosedLoopState.CLOSED, ClosedLoopState.STABLE} and not self.approval_required:
            raise ValueError("active evolution loops require human approval")


@dataclass(frozen=True)
class ClosedLoopPlan:
    loop_id: str
    trigger_id: str
    actions: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    isolated: bool = True
    requires_human_approval: bool = True

    def validate(self) -> None:
        if not self.loop_id.startswith("LOOP-") or not self.trigger_id.startswith("CI-TRIGGER-"):
            raise ValueError("invalid closed-loop plan identity")
        if not self.actions or not self.evidence_ids:
            raise ValueError("closed-loop plan requires actions and evidence")
        if not self.isolated or not self.requires_human_approval:
            raise ValueError("closed-loop plans must remain isolated and approval-gated")


class ClosedLoopEvolution:
    """F32 coordinator: monitor → detect → plan → gates → monitor → repeat."""

    def __init__(
        self,
        *,
        intelligence: ContinuousIntelligenceEvolution | None = None,
        orchestrator: EvolutionRuntimeOrchestrator | None = None,
        history_limit: int = 100,
    ) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be >= 1")
        self.intelligence = intelligence or ContinuousIntelligenceEvolution(history_limit=history_limit)
        self.orchestrator = orchestrator or EvolutionRuntimeOrchestrator()
        self.history_limit = history_limit
        self._loops: dict[str, ClosedLoopRecord] = {}
        self._plans: dict[str, ClosedLoopPlan] = {}
        self._counter = 0
        self._lock = RLock()

    def _next_id(self) -> str:
        self._counter += 1
        return f"LOOP-{self._counter:06d}"

    def start(self, capability_id: str, baseline_score: float) -> ClosedLoopRecord:
        cycle = self.intelligence.start_cycle(capability_id, baseline_score)
        record = ClosedLoopRecord(self._next_id(), capability_id, ClosedLoopState.OBSERVING, baseline_score)
        record.validate()
        with self._lock:
            self._loops[record.loop_id] = record
        return record

    def observe(self, loop_id: str, observation: IntelligenceObservation) -> ClosedLoopRecord:
        current = self.get(loop_id)
        if current.state != ClosedLoopState.OBSERVING:
            raise ValueError("loop is not accepting an observation")
        cycle = self.intelligence._cycles_by_capability_for_loop(current, loop_id) if False else None
        # F22 remains the authoritative observation/assessment gate. The loop keeps
        # an explicit cycle reference by resolving the only active cycle for this
        # capability created through this controller.
        cycle_id = self._cycle_id_for(current)
        assessed = self.intelligence.assess(cycle_id, observation)
        if assessed.state is IntelligenceCycleState.ASSESSED:
            state = ClosedLoopState.STABLE
            reason = assessed.trigger_reason
        else:
            state = ClosedLoopState.TRIGGERED
            reason = assessed.trigger_reason
        updated = ClosedLoopRecord(
            current.loop_id, current.capability_id, state, current.baseline_score,
            observation.score, assessed.risk, reason, assessed.observation_ids,
            current.trigger_id, current.plan_id, current.evolution_id, True,
        )
        return self._store(updated)

    def trigger(self, loop_id: str) -> IntelligenceTrigger | None:
        current = self.get(loop_id)
        if current.state != ClosedLoopState.TRIGGERED:
            return None
        cycle_id = self._cycle_id_for(current)
        trigger = self.intelligence.trigger(cycle_id)
        if trigger is None:
            return None
        updated = ClosedLoopRecord(
            current.loop_id, current.capability_id, ClosedLoopState.TRIGGERED,
            current.baseline_score, current.latest_score, trigger.risk,
            trigger.reason, current.observation_ids, trigger.trigger_id,
            current.plan_id, current.evolution_id, True,
        )
        self._store(updated)
        return trigger

    def plan(self, loop_id: str, *, actions: tuple[str, ...], evidence_ids: tuple[str, ...]) -> ClosedLoopPlan:
        current = self.get(loop_id)
        if current.state != ClosedLoopState.TRIGGERED or not current.trigger_id:
            raise ValueError("a triggered loop is required")
        trigger = self._trigger(current.trigger_id)
        plan = self.intelligence.plan(trigger, actions=actions)
        if tuple(evidence_ids) != trigger.evidence_ids:
            raise ValueError("plan evidence must exactly match trigger evidence")
        result = ClosedLoopPlan(current.loop_id, trigger.trigger_id, actions, evidence_ids)
        result.validate()
        self._plans[result.trigger_id] = result
        return self._store(ClosedLoopRecord(
            current.loop_id, current.capability_id, ClosedLoopState.PLANNED,
            current.baseline_score, current.latest_score, current.risk,
            current.reason, current.observation_ids, current.trigger_id, plan.plan_id,
            current.evolution_id, True,
        ))

    def open_evolution_gate(self, loop_id: str, *, problem: str, risk: EvolutionRisk | None = None) -> OrchestrationContext:
        current = self.get(loop_id)
        if current.state != ClosedLoopState.PLANNED:
            raise ValueError("loop must have a plan before opening evolution gate")
        context = self.orchestrator.detect(
            capability_id=current.capability_id,
            problem=problem,
            risk=risk or current.risk,
        )
        return self._store(ClosedLoopRecord(
            current.loop_id, current.capability_id, ClosedLoopState.WAITING_EVIDENCE,
            current.baseline_score, current.latest_score, current.risk, current.reason,
            current.observation_ids, current.trigger_id, current.plan_id,
            context.evolution_id, True,
        )) and context

    def mark_waiting_approval(self, loop_id: str) -> ClosedLoopRecord:
        current = self.get(loop_id)
        if current.state != ClosedLoopState.WAITING_EVIDENCE:
            raise ValueError("loop is not waiting for approval")
        return self._store(self._replace_state(current, ClosedLoopState.WAITING_APPROVAL))

    def close_rejected(self, loop_id: str, *, reason: str) -> ClosedLoopRecord:
        if not reason.strip():
            raise ValueError("rejection reason is required")
        current = self.get(loop_id)
        return self._store(self._replace_state(current, ClosedLoopState.REJECTED, reason=reason))

    def mark_promoted(self, loop_id: str) -> ClosedLoopRecord:
        current = self.get(loop_id)
        if current.state != ClosedLoopState.WAITING_APPROVAL:
            raise ValueError("explicit approval gate must be reached first")
        return self._store(self._replace_state(current, ClosedLoopState.PROMOTED))

    def begin_monitoring(self, loop_id: str) -> ClosedLoopRecord:
        current = self.get(loop_id)
        if current.state != ClosedLoopState.PROMOTED:
            raise ValueError("promotion must precede monitoring")
        return self._store(self._replace_state(current, ClosedLoopState.MONITORED))

    def close_stable(self, loop_id: str) -> ClosedLoopRecord:
        current = self.get(loop_id)
        if current.state != ClosedLoopState.STABLE:
            raise ValueError("only stable observations can close a loop")
        return self._store(self._replace_state(current, ClosedLoopState.CLOSED))

    def get(self, loop_id: str) -> ClosedLoopRecord:
        try:
            return self._loops[loop_id]
        except KeyError as exc:
            raise KeyError("unknown closed-loop") from exc

    def plans(self) -> tuple[ClosedLoopPlan, ...]:
        return tuple(self._plans.values())

    def counts(self) -> dict[str, int]:
        return {"loops": len(self._loops), "plans": len(self._plans)}

    def digest(self) -> str:
        payload = {
            "loops": [asdict(x) for x in sorted(self._loops.values(), key=lambda x: x.loop_id)],
            "plans": [asdict(x) for x in sorted(self._plans.values(), key=lambda x: x.loop_id)],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=lambda x: x.value if hasattr(x, "value") else x, separators=(",", ":")).encode()).hexdigest()

    def _cycle_id_for(self, record: ClosedLoopRecord) -> str:
        matches = [c for c in self.intelligence._cycles.values() if c.capability_id == record.capability_id and c.baseline_score == record.baseline_score]
        if not matches:
            raise KeyError("closed-loop intelligence cycle not found")
        return sorted(matches, key=lambda x: x.cycle_id)[-1].cycle_id

    def _trigger(self, trigger_id: str) -> IntelligenceTrigger:
        for value in self.intelligence._triggers.values():
            if value.trigger_id == trigger_id:
                return value
        raise KeyError("closed-loop trigger not found")

    def _replace_state(self, current: ClosedLoopRecord, state: str, *, reason: str | None = None) -> ClosedLoopRecord:
        return self._store(ClosedLoopRecord(
            current.loop_id, current.capability_id, state, current.baseline_score,
            current.latest_score, current.risk, reason if reason is not None else current.reason,
            current.observation_ids, current.trigger_id, current.plan_id, current.evolution_id, True,
        ))

    def _store(self, record: ClosedLoopRecord) -> ClosedLoopRecord:
        record.validate()
        with self._lock:
            self._loops[record.loop_id] = record
            while len(self._loops) > self.history_limit:
                del self._loops[sorted(self._loops)[0]]
        return record


class PersistentClosedLoopEvolution(ClosedLoopEvolution):
    """F32 durable wrapper. Persistence contains metadata/evidence references only."""

    def __init__(self, path: str | Path, *, history_limit: int = 100) -> None:
        self.path = Path(path)
        super().__init__(history_limit=history_limit)
        self._load()

    def _save(self) -> None:
        payload = {
            "loops": {k: asdict(v) for k, v in self._loops.items()},
            "plans": {k: asdict(v) for k, v in self._plans.items()},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True, default=lambda x: x.value if hasattr(x, "value") else x), encoding="utf-8")
        tmp.replace(self.path)

    def _store(self, record: ClosedLoopRecord) -> ClosedLoopRecord:
        result = super()._store(record)
        self._save()
        return result

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("closed-loop store must contain an object")
        for key, value in raw.get("loops", {}).items():
            record = ClosedLoopRecord(
                loop_id=value["loop_id"], capability_id=value["capability_id"], state=value["state"],
                baseline_score=float(value["baseline_score"]), latest_score=value.get("latest_score"),
                risk=EvolutionRisk(value.get("risk", EvolutionRisk.MEDIUM.value)),
                reason=value.get("reason", ""), observation_ids=tuple(value.get("observation_ids", ())),
                trigger_id=value.get("trigger_id"), plan_id=value.get("plan_id"),
                evolution_id=value.get("evolution_id"), approval_required=bool(value.get("approval_required", True)),
            )
            if key != record.loop_id:
                raise ValueError("closed-loop key mismatch")
            record.validate()
            self._loops[key] = record
        for key, value in raw.get("plans", {}).items():
            plan = ClosedLoopPlan(key, value["trigger_id"], tuple(value["actions"]), tuple(value["evidence_ids"]),
                                  bool(value.get("isolated", True)), bool(value.get("requires_human_approval", True)))
            plan.validate()
            self._plans[key] = plan
