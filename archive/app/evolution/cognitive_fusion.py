"""LUMEN Cognitive Fusion Core.

A dependency-light orchestration layer that makes the evolution subsystems
operate as one system. It does not bypass existing security/promotion gates.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import random
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from .autonomous_progress import AutonomousProgressController


@dataclass(frozen=True)
class Experience:
    experience_id: str
    objective: str
    context: dict[str, Any]
    action: str
    outcome: str
    success: bool
    lesson: str = ""
    error: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class CapabilityGap:
    capability_id: str
    description: str
    severity: float = 0.5
    evidence: tuple[str, ...] = ()
    def validate(self) -> None:
        if not self.capability_id.strip() or not self.description.strip():
            raise ValueError("capability gap identity is required")
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError("gap severity must be between 0 and 1")


@dataclass(frozen=True)
class WorldFact:
    key: str
    value: Any
    source: str
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    def validate(self) -> None:
        if not self.key.strip() or not self.source.strip():
            raise ValueError("world fact identity is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("world fact confidence must be between 0 and 1")


@dataclass(frozen=True)
class ResearchFinding:
    finding_id: str
    query: str
    summary: str
    sources: tuple[str, ...] = ()
    confidence: float = 0.5
    def validate(self) -> None:
        if not self.finding_id.strip() or not self.query.strip() or not self.summary.strip():
            raise ValueError("research finding requires identity, query and summary")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("research confidence must be between 0 and 1")


@dataclass(frozen=True)
class ToolCandidate:
    tool_id: str
    purpose: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    tests: tuple[str, ...] = ()
    risk: str = "low"
    def validate(self) -> None:
        if not self.tool_id.strip() or not self.purpose.strip():
            raise ValueError("tool candidate identity is required")
        if self.risk not in {"low", "medium", "high"}:
            raise ValueError("invalid tool risk")


@dataclass(frozen=True)
class EvolutionHypothesis:
    hypothesis_id: str
    gap_id: str
    statement: str
    expected_gain: float
    experiment: str
    def validate(self) -> None:
        if not self.hypothesis_id.strip() or not self.gap_id.strip() or not self.statement.strip():
            raise ValueError("hypothesis identity is required")
        if not 0.0 <= self.expected_gain <= 1.0:
            raise ValueError("expected gain must be between 0 and 1")


class ExperienceMemory:
    def __init__(self, limit: int = 2000) -> None:
        if limit < 1:
            raise ValueError("memory limit must be positive")
        self.limit, self._items = limit, []
    def add(self, item: Experience) -> None:
        if any(x.experience_id == item.experience_id for x in self._items):
            raise ValueError("experience id already exists")
        self._items.append(item)
        if len(self._items) > self.limit:
            del self._items[:-self.limit]
    def recall(self, *, objective: str = "", action: str = "", limit: int = 12) -> tuple[Experience, ...]:
        terms = {x.lower() for x in (objective + " " + action).split() if len(x) > 2}
        scored = []
        for item in self._items:
            hay = f"{item.objective} {item.action} {item.outcome} {item.lesson}".lower()
            score = sum(1 for term in terms if term in hay)
            if score:
                scored.append((score, item.timestamp, item))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return tuple(x[2] for x in scored[:limit])
    def lessons(self, limit: int = 32) -> tuple[str, ...]:
        seen = []
        for item in reversed(self._items):
            if item.lesson and item.lesson not in seen:
                seen.append(item.lesson)
            if len(seen) >= limit:
                break
        return tuple(seen)


class WorldModel:
    def __init__(self, limit: int = 2000) -> None:
        self.limit, self._facts = limit, {}
    def observe(self, fact: WorldFact) -> None:
        fact.validate()
        old = self._facts.get(fact.key)
        if old is None or fact.confidence >= old.confidence or fact.timestamp >= old.timestamp:
            self._facts[fact.key] = fact
        if len(self._facts) > self.limit:
            oldest = min(self._facts, key=lambda k: self._facts[k].timestamp)
            del self._facts[oldest]
    def get(self, key: str, default: Any = None) -> Any:
        fact = self._facts.get(key)
        return default if fact is None else fact.value
    def facts(self) -> tuple[WorldFact, ...]:
        return tuple(self._facts.values())
    def contradiction(self, key: str, value: Any) -> bool:
        old = self._facts.get(key)
        return old is not None and old.value != value and old.confidence >= 0.8
    def digest(self) -> str:
        payload = [(x.key, x.value, x.source, x.confidence) for x in sorted(self._facts.values(), key=lambda x: x.key)]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class CapabilityGraph:
    def __init__(self) -> None:
        self._gaps, self._validated = {}, set()
    def add_gap(self, gap: CapabilityGap) -> None:
        gap.validate()
        self._gaps[gap.capability_id] = gap
    def validate(self, capability_id: str, evidence: str) -> None:
        if not capability_id.strip() or not evidence.strip():
            raise ValueError("capability validation requires evidence")
        self._validated.add(capability_id)
        self._gaps.pop(capability_id, None)
    def gaps(self) -> tuple[CapabilityGap, ...]:
        return tuple(sorted(self._gaps.values(), key=lambda x: (-x.severity, x.capability_id)))
    def is_validated(self, capability_id: str) -> bool:
        return capability_id in self._validated


class QuantumInspiredOptimizer:
    """Classical reproducible search; future Qiskit backends can replace it."""
    def __init__(self, seed: int = 7) -> None:
        self.seed = seed
    def rank(self, candidates: Iterable[Mapping[str, Any]], *, key: str = "score") -> tuple[dict[str, Any], ...]:
        items = [dict(x) for x in candidates]
        rng = random.Random(self.seed)
        for item in items:
            base, risk, novelty = float(item.get(key, 0.0)), float(item.get("risk", 0.0)), float(item.get("novelty", 0.0))
            item["_quantum_inspired_score"] = base + 0.15 * novelty - 0.20 * risk + rng.random() * 1e-9
        items.sort(key=lambda x: x["_quantum_inspired_score"], reverse=True)
        return tuple(items)
    def anneal(self, values: Iterable[float], steps: int = 64) -> tuple[float, ...]:
        values = tuple(float(x) for x in values)
        if not values or steps < 1:
            return values
        best, current, rng = list(values), list(values), random.Random(self.seed)
        for step in range(steps):
            temperature = max(0.01, 1.0 - step / steps)
            i = rng.randrange(len(current))
            candidate = current[:]
            candidate[i] += rng.uniform(-temperature, temperature)
            delta = sum(candidate) - sum(current)
            if delta >= 0 or rng.random() < math.exp(delta / temperature):
                current = candidate
            if sum(current) > sum(best):
                best = current[:]
        return tuple(best)


class TemporalEventLearner:
    """CPU-safe transition learner with a replaceable SNN/HTM backend."""
    def __init__(self) -> None:
        self.transitions: dict[tuple[str, str], int] = {}
    def observe(self, events: Iterable[str]) -> None:
        seq = tuple(str(x) for x in events if str(x))
        for a, b in zip(seq, seq[1:]):
            self.transitions[(a, b)] = self.transitions.get((a, b), 0) + 1
    def predict(self, current: str, limit: int = 5) -> tuple[str, ...]:
        pairs = [(count, b) for (a, b), count in self.transitions.items() if a == current]
        pairs.sort(reverse=True)
        return tuple(b for _, b in pairs[:limit])


class EvolutionGovernor:
    def admit(self, *, risk: str, approved: bool = False, isolated: bool = True) -> bool:
        return isolated and not (risk == "high" and not approved)
    def require_validation(self, *, tests_passed: bool, benchmarked: bool, rollback_ready: bool) -> bool:
        return bool(tests_passed and benchmarked and rollback_ready)


class CognitiveFusion:
    """Single control plane over memory, world model, learning and evolution."""
    VERSION = "1.0"
    def __init__(self, state_dir: str | Path, mission_id: str) -> None:
        self.state_dir = Path(state_dir)
        self.progress = AutonomousProgressController(self.state_dir / "autonomous_progress.json", mission_id)
        self.memory, self.world, self.capabilities = ExperienceMemory(), WorldModel(), CapabilityGraph()
        self.quantum, self.temporal, self.governor = QuantumInspiredOptimizer(), TemporalEventLearner(), EvolutionGovernor()
        self._findings, self._tools, self._hypotheses = {}, {}, {}
    def ingest_world(self, facts: Iterable[WorldFact]) -> None:
        for fact in facts: self.world.observe(fact)
    def learn(self, finding: ResearchFinding) -> None:
        finding.validate(); self._findings[finding.finding_id] = finding
        self.progress.record(action="research", result=finding.finding_id, success=True, new_information=True,
                             research_finding=finding.summary, details={"sources": finding.sources, "query": finding.query})
    def observe_experience(self, experience: Experience) -> None:
        self.memory.add(experience); self.temporal.observe((experience.action, experience.outcome))
        self.progress.record(action=experience.action, result=experience.outcome, success=experience.success,
                             new_information=bool(experience.lesson), observation=experience.lesson or experience.outcome,
                             error=experience.error)
    def register_gap(self, gap: CapabilityGap) -> None:
        self.capabilities.add_gap(gap)
        self.progress.record(action="capability_gap", result=gap.capability_id, success=True, new_information=True, gap=gap.description)
    def propose_hypothesis(self, hypothesis: EvolutionHypothesis) -> None:
        hypothesis.validate()
        if self.capabilities.is_validated(hypothesis.gap_id):
            raise ValueError("cannot hypothesize against a validated capability")
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        self.progress.set_hypothesis(hypothesis.statement)
    def propose_tool(self, tool: ToolCandidate) -> None:
        tool.validate()
        if tool.risk == "high":
            raise PermissionError("high-risk tool candidates require governed promotion")
        self._tools[tool.tool_id] = tool
    def select_next(self, available_actions: Iterable[str], context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return asdict(self.progress.recommend(tuple(available_actions), context=context))
    def validate_capability(self, capability_id: str, evidence: str) -> None:
        self.capabilities.validate(capability_id, evidence); self.progress.mark_validated(capability_id, evidence=evidence)
    def should_promote(self, *, tests_passed: bool, benchmarked: bool, rollback_ready: bool, risk: str = "low", approved: bool = False) -> bool:
        return self.governor.admit(risk=risk, approved=approved) and self.governor.require_validation(
            tests_passed=tests_passed, benchmarked=benchmarked, rollback_ready=rollback_ready)
    def planner_context(self) -> dict[str, Any]:
        return {
            "version": self.VERSION, "progress": self.progress.planner_context(),
            "world_facts": [asdict(x) for x in self.world.facts()],
            "capability_gaps": [asdict(x) for x in self.capabilities.gaps()],
            "research": [asdict(x) for x in self._findings.values()],
            "tools": [asdict(x) for x in self._tools.values()],
            "hypotheses": [asdict(x) for x in self._hypotheses.values()],
            "lessons": self.memory.lessons(),
            "temporal_predictions": {"after_last_action": self.temporal.predict(self.progress.state.last_action)},
            "world_digest": self.world.digest(),
        }
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.planner_context(), sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    def persist_snapshot(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.state_dir / "cognitive_fusion_snapshot.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.planner_context(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return target
