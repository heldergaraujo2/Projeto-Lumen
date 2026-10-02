"""Persistent progress controller for Lumen's autonomous evolution loop.

Execution-agnostic: it does not grant permissions or execute tools. It converts
action evidence into durable progress state and prevents planner stagnation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

DEFAULT_ACTION_ORDER = (
    "list_toolsets", "describe_toolset", "observe_unreal", "unreal_call",
    "research", "evolve_code", "done",
)

@dataclass
class ActionEvidence:
    action: str
    fingerprint: str
    success: bool
    new_information: bool
    result: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    recovery_attempt: int = 0

    def validate(self) -> None:
        if not self.action.strip():
            raise ValueError("action is required")
        if not self.fingerprint.strip():
            raise ValueError("action fingerprint is required")
        if self.recovery_attempt < 0:
            raise ValueError("recovery attempt cannot be negative")

@dataclass
class EvolutionProgressState:
    mission_id: str
    cycle: int = 0
    progress_epoch: int = 0
    stagnation_steps: int = 0
    last_action: str = ""
    last_fingerprint: str = ""
    last_result: str = ""
    last_error: str = ""
    current_gap: str = ""
    current_hypothesis: str = ""
    discovered_capabilities: list[str] = field(default_factory=list)
    validated_capabilities: list[str] = field(default_factory=list)
    known_toolsets: list[str] = field(default_factory=list)
    described_toolsets: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    research_findings: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    repeat_counts: dict[str, int] = field(default_factory=dict)
    failure_counts: dict[str, int] = field(default_factory=dict)
    recovery_counts: dict[str, int] = field(default_factory=dict)
    evidence: list[ActionEvidence] = field(default_factory=list)

    def validate(self) -> None:
        if not self.mission_id.strip():
            raise ValueError("mission_id is required")
        if self.cycle < 0 or self.progress_epoch < 0 or self.stagnation_steps < 0:
            raise ValueError("progress counters cannot be negative")
        for item in self.evidence:
            item.validate()

    def has_capability(self, capability: str) -> bool:
        return capability in self.discovered_capabilities

    def has_validated(self, capability: str) -> bool:
        return capability in self.validated_capabilities

@dataclass(frozen=True)
class ProgressDecision:
    action: str
    reason: str
    progress_required: bool
    recovery: bool = False

class AutonomousProgressController:
    """Durable anti-stagnation and progress controller.

    The controller is deterministic for the same state/context. The LLM may
    still choose actions, but callers can use admit() before executing a choice
    and recommend() when the planner repeats itself.
    """
    def __init__(
        self, path: str | Path, mission_id: str, *,
        repeat_limit: int = 2, max_recovery_attempts: int = 3,
        stagnation_limit: int = 3, evidence_limit: int = 500,
    ) -> None:
        if repeat_limit < 1:
            raise ValueError("repeat_limit must be >= 1")
        if max_recovery_attempts < 1:
            raise ValueError("max_recovery_attempts must be >= 1")
        if stagnation_limit < 1:
            raise ValueError("stagnation_limit must be >= 1")
        if evidence_limit < 1:
            raise ValueError("evidence_limit must be >= 1")
        self.path = Path(path)
        self.repeat_limit = repeat_limit
        self.max_recovery_attempts = max_recovery_attempts
        self.stagnation_limit = stagnation_limit
        self.evidence_limit = evidence_limit
        self._lock = RLock()
        self.state = self._load(mission_id)

    @staticmethod
    def fingerprint(action: str, payload: Any = None) -> str:
        normalized = json.dumps(
            {"action": action, "payload": payload}, sort_keys=True,
            ensure_ascii=False, default=str, separators=(",", ":"),
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _load(self, mission_id: str) -> EvolutionProgressState:
        if not self.path.exists():
            state = EvolutionProgressState(mission_id=mission_id)
            state.validate()
            return state
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("progress state must be an object")
        state = EvolutionProgressState(
            mission_id=str(raw.get("mission_id") or mission_id),
            cycle=int(raw.get("cycle", 0)),
            progress_epoch=int(raw.get("progress_epoch", 0)),
            stagnation_steps=int(raw.get("stagnation_steps", 0)),
            last_action=str(raw.get("last_action", "")),
            last_fingerprint=str(raw.get("last_fingerprint", "")),
            last_result=str(raw.get("last_result", "")),
            last_error=str(raw.get("last_error", "")),
            current_gap=str(raw.get("current_gap", "")),
            current_hypothesis=str(raw.get("current_hypothesis", "")),
            discovered_capabilities=list(raw.get("discovered_capabilities", [])),
            validated_capabilities=list(raw.get("validated_capabilities", [])),
            known_toolsets=list(raw.get("known_toolsets", [])),
            described_toolsets=list(raw.get("described_toolsets", [])),
            observations=list(raw.get("observations", [])),
            research_findings=list(raw.get("research_findings", [])),
            gaps=list(raw.get("gaps", [])),
            repeat_counts={str(k): int(v) for k, v in dict(raw.get("repeat_counts", {})).items()},
            failure_counts={str(k): int(v) for k, v in dict(raw.get("failure_counts", {})).items()},
            recovery_counts={str(k): int(v) for k, v in dict(raw.get("recovery_counts", {})).items()},
            evidence=[ActionEvidence(
                action=str(x["action"]), fingerprint=str(x["fingerprint"]),
                success=bool(x["success"]), new_information=bool(x["new_information"]),
                result=str(x.get("result", "")), details=dict(x.get("details", {})),
                recovery_attempt=int(x.get("recovery_attempt", 0)),
            ) for x in raw.get("evidence", [])],
        )
        if state.mission_id != mission_id:
            raise ValueError("progress state belongs to another mission")
        state.validate()
        return state

    def save(self) -> None:
        with self._lock:
            self.state.validate()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(asdict(self.state), ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)

    @staticmethod
    def _append_unique(collection: list[str], value: str) -> None:
        value = value.strip()
        if value and value not in collection:
            collection.append(value)

    def admit(self, action: str, fingerprint: str | None = None) -> bool:
        action = action.strip()
        if not action:
            raise ValueError("action is required")
        fp = fingerprint or self.fingerprint(action)
        key = f"{action}:{fp}"
        return self.state.repeat_counts.get(key, 0) < self.repeat_limit

    def record(
        self, *, action: str, result: str = "", success: bool = True,
        new_information: bool = False, fingerprint: str | None = None,
        details: Mapping[str, Any] | None = None, capability: str | None = None,
        gap: str | None = None, research_finding: str | None = None,
        observation: str | None = None, error: str | None = None,
    ) -> ActionEvidence:
        with self._lock:
            action = action.strip()
            if not action:
                raise ValueError("action is required")
            fp = fingerprint or self.fingerprint(action, details)
            key = f"{action}:{fp}"
            self.state.repeat_counts[key] = self.state.repeat_counts.get(key, 0) + 1
            evidence = ActionEvidence(
                action=action, fingerprint=fp, success=success,
                new_information=new_information, result=result,
                details=dict(details or {}),
                recovery_attempt=self.state.recovery_counts.get(action, 0),
            )
            evidence.validate()
            self.state.last_action = action
            self.state.last_fingerprint = fp
            self.state.last_result = result
            self.state.last_error = error or ""
            if success and new_information:
                self.state.progress_epoch += 1
                self.state.stagnation_steps = 0
            else:
                self.state.stagnation_steps += 1
            if not success:
                self.state.failure_counts[action] = self.state.failure_counts.get(action, 0) + 1
            else:
                self.state.failure_counts.pop(action, None)
            if capability:
                self._append_unique(self.state.discovered_capabilities, capability)
            if observation:
                self._append_unique(self.state.observations, observation)
            if research_finding:
                self._append_unique(self.state.research_findings, research_finding)
            if gap:
                self._append_unique(self.state.gaps, gap)
                self.state.current_gap = gap
            self.state.evidence.append(evidence)
            if len(self.state.evidence) > self.evidence_limit:
                del self.state.evidence[:-self.evidence_limit]
            self.save()
            return evidence

    def mark_validated(self, capability: str, *, evidence: str) -> None:
        with self._lock:
            capability = capability.strip()
            if not capability or not evidence.strip():
                raise ValueError("validated capability and evidence are required")
            self._append_unique(self.state.discovered_capabilities, capability)
            self._append_unique(self.state.validated_capabilities, capability)
            self._append_unique(self.state.observations, evidence)
            self.state.progress_epoch += 1
            self.state.stagnation_steps = 0
            self.save()

    def set_hypothesis(self, hypothesis: str) -> None:
        with self._lock:
            self.state.current_hypothesis = hypothesis.strip()
            self.save()

    def begin_recovery(self, action: str) -> int:
        with self._lock:
            current = self.state.recovery_counts.get(action, 0)
            if current >= self.max_recovery_attempts:
                raise RuntimeError(f"recovery budget exhausted for {action}")
            current += 1
            self.state.recovery_counts[action] = current
            self.save()
            return current

    def recovery_available(self, action: str) -> bool:
        return self.state.recovery_counts.get(action, 0) < self.max_recovery_attempts

    def recommend(self, available_actions: tuple[str, ...] | list[str], *, context: Mapping[str, Any] | None = None) -> ProgressDecision:
        available = tuple(dict.fromkeys(str(x) for x in available_actions))
        ctx = dict(context or {})
        toolsets = tuple(str(x) for x in ctx.get("toolsets", self.state.known_toolsets))
        described = tuple(str(x) for x in ctx.get("described_toolsets", self.state.described_toolsets))
        for item in toolsets:
            self._append_unique(self.state.known_toolsets, item)
        for item in described:
            self._append_unique(self.state.described_toolsets, item)
        self.save()

        if self.state.stagnation_steps >= self.stagnation_limit:
            for candidate in ("describe_toolset", "observe_unreal", "unreal_call", "research", "evolve_code"):
                if candidate in available and self.admit(candidate):
                    self.state.stagnation_steps = 0
                    self.save()
                    return ProgressDecision(candidate, "stagnation guard forced a new capability step", True)

        if self.state.last_action == "list_toolsets" and toolsets:
            for item in toolsets:
                if item not in described and "describe_toolset" in available:
                    return ProgressDecision("describe_toolset", f"toolsets already discovered; inspect {item} instead of repeating discovery", True)

        if self.state.last_action == "research":
            if ctx.get("capability_gap") and ctx.get("can_evolve_code") and "evolve_code" in available and self.admit("evolve_code"):
                return ProgressDecision("evolve_code", "research identified a capability gap; implement a bounded candidate", True)
            if ctx.get("can_observe") and "observe_unreal" in available and self.admit("observe_unreal"):
                return ProgressDecision("observe_unreal", "research completed; validate the finding against the live Unreal state", True)

        if self.state.last_action == "describe_toolset":
            if ctx.get("can_observe") and "observe_unreal" in available and self.admit("observe_unreal"):
                return ProgressDecision("observe_unreal", "toolset described; validate perception against Unreal", True)

        if self.state.last_action == "observe_unreal":
            if ctx.get("can_unreal_call") and "unreal_call" in available and self.admit("unreal_call"):
                return ProgressDecision("unreal_call", "Unreal state observed; exercise an advertised capability", True)
            if ctx.get("can_research") and "research" in available and self.admit("research"):
                return ProgressDecision("research", "observation exposed a gap; research a bounded solution", True)

        if self.state.last_action == "unreal_call":
            if self.state.last_error and self.recovery_available("unreal_call") and "research" in available:
                return ProgressDecision("research", "Unreal action failed; diagnose/research before retrying", True, True)
            if ctx.get("capability_gap") and "evolve_code" in available and self.admit("evolve_code"):
                return ProgressDecision("evolve_code", "Unreal action exposed a capability gap; evolve the tool in isolation", True)

        if ctx.get("capability_gap") and "research" in available and self.admit("research"):
            return ProgressDecision("research", "a capability gap is known and needs evidence", True)

        if self.state.known_toolsets and "observe_unreal" in available and ctx.get("can_observe") and self.admit("observe_unreal"):
            return ProgressDecision("observe_unreal", "existing MCP discovery should be converted into a live observation", True)

        if "list_toolsets" in available and not self.state.known_toolsets and self.admit("list_toolsets"):
            return ProgressDecision("list_toolsets", "no toolset inventory exists yet", True)

        for candidate in DEFAULT_ACTION_ORDER:
            if candidate == "done":
                continue
            if candidate in available and self.admit(candidate):
                return ProgressDecision(candidate, "next admissible action in bounded fallback order", True)

        return ProgressDecision(
            "research" if "research" in available else (available[0] if available else "research"),
            "no preferred action remained; planner must provide new evidence", True,
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self.state)

    def planner_context(self, *, max_evidence: int = 12) -> dict[str, Any]:
        if max_evidence < 1:
            raise ValueError("max_evidence must be >= 1")
        with self._lock:
            return {
                "mission_id": self.state.mission_id,
                "cycle": self.state.cycle,
                "progress_epoch": self.state.progress_epoch,
                "stagnation_steps": self.state.stagnation_steps,
                "current_gap": self.state.current_gap,
                "current_hypothesis": self.state.current_hypothesis,
                "discovered_capabilities": tuple(self.state.discovered_capabilities),
                "validated_capabilities": tuple(self.state.validated_capabilities),
                "known_toolsets": tuple(self.state.known_toolsets),
                "described_toolsets": tuple(self.state.described_toolsets),
                "observations": tuple(self.state.observations[-max_evidence:]),
                "research_findings": tuple(self.state.research_findings[-max_evidence:]),
                "recent_evidence": tuple(asdict(x) for x in self.state.evidence[-max_evidence:]),
                "failure_counts": dict(self.state.failure_counts),
                "recovery_counts": dict(self.state.recovery_counts),
            }

    def digest(self) -> str:
        payload = json.dumps(self.snapshot(), ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
