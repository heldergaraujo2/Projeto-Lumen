"""Unified Lumen operational brain.

This is the runtime-facing cognitive façade over the evolution stack. It turns
memory, world state, capability gaps, research, planning, experiments and
validation into one persistent control loop.

The brain does not bypass existing permission/security/promotion gates.
It is provider-neutral: a local LLM can supply reasoning, while deterministic
controllers provide durable state, anti-stagnation and evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .cognitive_fusion import (
    CapabilityGap,
    CognitiveFusion,
    Experience,
    EvolutionHypothesis,
    ResearchFinding,
    ToolCandidate,
    WorldFact,
)


@dataclass
class BrainState:
    mission_id: str
    objective: str
    phase: str = "ORIENT"
    cycle: int = 0
    completed: bool = False
    last_decision: str = ""
    last_reason: str = ""
    last_outcome: str = ""
    last_error: str = ""
    recovery_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def validate(self) -> None:
        if not self.mission_id.strip():
            raise ValueError("mission_id is required")
        if not self.objective.strip():
            raise ValueError("objective is required")
        if self.cycle < 0 or self.recovery_count < 0:
            raise ValueError("brain counters cannot be negative")


@dataclass(frozen=True)
class BrainDecision:
    action: str
    phase: str
    reason: str
    context_digest: str
    recovery: bool = False


@dataclass(frozen=True)
class ActionOutcome:
    action: str
    success: bool
    result: str = ""
    error: str = ""
    new_information: bool = False
    evidence: Mapping[str, Any] = field(default_factory=dict)


class OperationalBrain:
    """One durable control plane for the Lumen cognitive/evolution stack."""

    VERSION = "1.0"

    _PHASE_BY_ACTION = {
        "list_toolsets": "DISCOVER",
        "describe_toolset": "UNDERSTAND",
        "observe_unreal": "OBSERVE",
        "research": "RESEARCH",
        "evolve_code": "EXPERIMENT",
        "unreal_call": "ACT",
        "done": "COMPLETE",
    }

    def __init__(
        self,
        state_dir: str | Path,
        mission_id: str,
        objective: str,
        *,
        max_recovery_attempts: int = 3,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / "operational_brain.json"
        self.fusion = CognitiveFusion(self.state_dir, mission_id)
        self.max_recovery_attempts = max_recovery_attempts
        if max_recovery_attempts < 1:
            raise ValueError("max_recovery_attempts must be >= 1")
        self.state = self._load_state(mission_id, objective)
        self._persist()

    def _load_state(self, mission_id: str, objective: str) -> BrainState:
        if not self.state_path.exists():
            state = BrainState(mission_id=mission_id, objective=objective)
            state.validate()
            return state
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        if str(raw.get("mission_id")) != mission_id:
            raise ValueError("operational brain belongs to another mission")
        state = BrainState(
            mission_id=mission_id,
            objective=str(raw.get("objective") or objective),
            phase=str(raw.get("phase") or "ORIENT"),
            cycle=int(raw.get("cycle", 0)),
            completed=bool(raw.get("completed", False)),
            last_decision=str(raw.get("last_decision", "")),
            last_reason=str(raw.get("last_reason", "")),
            last_outcome=str(raw.get("last_outcome", "")),
            last_error=str(raw.get("last_error", "")),
            recovery_count=int(raw.get("recovery_count", 0)),
            created_at=float(raw.get("created_at", time.time())),
            updated_at=float(raw.get("updated_at", time.time())),
        )
        state.validate()
        return state

    def _persist(self) -> None:
        self.state.updated_at = time.time()
        self.state.validate()
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self.state), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)
        self.fusion.persist_snapshot(self.state_dir / "cognitive_fusion_snapshot.json")

    def set_goal(self, objective: str) -> None:
        objective = objective.strip()
        if not objective:
            raise ValueError("objective is required")
        self.state.objective = objective
        self.state.completed = False
        self.state.phase = "ORIENT"
        self._persist()

    def ingest_world(self, facts: Iterable[WorldFact]) -> None:
        self.fusion.ingest_world(facts)
        self._persist()

    def register_gap(self, gap: CapabilityGap) -> None:
        self.fusion.register_gap(gap)
        self._persist()

    def absorb_research(self, finding: ResearchFinding) -> None:
        self.fusion.learn(finding)
        self._persist()

    def remember(self, experience: Experience) -> None:
        self.fusion.observe_experience(experience)
        self._persist()

    def propose(self, hypothesis: EvolutionHypothesis) -> None:
        self.fusion.propose_hypothesis(hypothesis)
        self._persist()

    def create_tool_candidate(self, tool: ToolCandidate) -> None:
        self.fusion.propose_tool(tool)
        self._persist()

    def decide(
        self,
        available_actions: Iterable[str],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> BrainDecision:
        if self.state.completed:
            return BrainDecision("done", "COMPLETE", "mission is already complete", self.fusion.digest())

        merged = dict(context or {})
        merged.setdefault("objective", self.state.objective)
        merged.setdefault("phase", self.state.phase)
        merged.setdefault("can_observe", "observe_unreal" in available_actions)
        merged.setdefault("can_research", "research" in available_actions)
        merged.setdefault("can_evolve_code", "evolve_code" in available_actions)
        merged.setdefault("can_unreal_call", "unreal_call" in available_actions)
        decision = self.fusion.select_next(tuple(available_actions), merged)
        action = str(decision.get("action") or "research")
        phase = self._PHASE_BY_ACTION.get(action, self.state.phase)
        self.state.last_decision = action
        self.state.last_reason = str(decision.get("reason") or "")
        self.state.phase = phase
        self.state.cycle += 1
        self._persist()
        return BrainDecision(
            action=action,
            phase=phase,
            reason=self.state.last_reason,
            context_digest=self.fusion.digest(),
            recovery=bool(decision.get("recovery", False)),
        )

    def execute(
        self,
        decision: BrainDecision,
        executor: Callable[[str], Any],
    ) -> ActionOutcome:
        """Execute one already-selected action and feed its evidence back."""
        try:
            raw = executor(decision.action)
            outcome = raw if isinstance(raw, ActionOutcome) else ActionOutcome(
                action=decision.action, success=True, result=str(raw), new_information=True,
            )
        except Exception as exc:  # bounded recovery is handled by recover()
            outcome = ActionOutcome(
                action=decision.action, success=False, error=f"{type(exc).__name__}: {exc}",
            )

        self.fusion.observe_experience(Experience(
            experience_id=f"{self.state.mission_id}:{self.state.cycle}:{decision.action}",
            objective=self.state.objective,
            context={"phase": decision.phase, "reason": decision.reason},
            action=decision.action,
            outcome=outcome.result,
            success=outcome.success,
            lesson=str(outcome.evidence.get("lesson", "")),
            error=outcome.error,
        ))
        self.state.last_outcome = outcome.result
        self.state.last_error = outcome.error
        if not outcome.success:
            self.state.phase = "RECOVER"
        elif decision.action == "done":
            self.state.completed = True
            self.state.phase = "COMPLETE"
        else:
            self.state.phase = "LEARN"
        self._persist()
        return outcome

    def recover(self, failed_action: str, *, reason: str = "") -> bool:
        if self.state.recovery_count >= self.max_recovery_attempts:
            self.state.phase = "BLOCKED"
            self.state.last_error = reason or f"recovery budget exhausted for {failed_action}"
            self._persist()
            return False
        self.state.recovery_count += 1
        self.state.phase = "RESEARCH"
        self.fusion.progress.begin_recovery(failed_action)
        self.fusion.progress.record(
            action="recover",
            result=failed_action,
            success=True,
            new_information=True,
            details={"reason": reason, "attempt": self.state.recovery_count},
        )
        self._persist()
        return True

    def validate_capability(self, capability_id: str, evidence: str) -> None:
        self.fusion.validate_capability(capability_id, evidence)
        self.state.phase = "LEARN"
        self._persist()

    def promotion_ready(
        self,
        *,
        tests_passed: bool,
        benchmarked: bool,
        rollback_ready: bool,
        risk: str = "low",
        approved: bool = False,
    ) -> bool:
        return self.fusion.should_promote(
            tests_passed=tests_passed,
            benchmarked=benchmarked,
            rollback_ready=rollback_ready,
            risk=risk,
            approved=approved,
        )

    def reasoning_context(self) -> dict[str, Any]:
        """Return the complete structured context a local provider can reason over."""
        return {
            "brain": asdict(self.state),
            "objective": self.state.objective,
            "cognitive_fusion": self.fusion.planner_context(),
            "instructions": {
                "continue_until_objective_is_validated": True,
                "prefer_new_evidence_over_repetition": True,
                "research_before_guessing_when_capability_is_missing": True,
                "learn_from_success_and_failure": True,
                "recover_within_bounded_budget": True,
                "never_bypass_governance": True,
            },
        }

    def snapshot(self) -> dict[str, Any]:
        return self.reasoning_context()

    def digest(self) -> str:
        return self.fusion.digest()
