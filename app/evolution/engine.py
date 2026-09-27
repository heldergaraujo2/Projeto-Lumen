from __future__ import annotations

import re
from dataclasses import replace
from threading import RLock

from .models import (
    BenchmarkResult, Capability, CapabilityMeasurement, Candidate, Diagnostic,
    EvolutionRecord, EvolutionRisk, EvolutionState, Hypothesis, ImprovementPlan,
    PromotionDecision, RegressionReport, SafetyReview,
)
from .registry import CapabilityRegistry, EvolutionMemory


class ImprovementPlanner:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def diagnose(self, capability_id: str, *, status: str, findings: tuple[str, ...] = ()) -> Diagnostic:
        capability = self.registry.get(capability_id)
        measurement = self.registry.latest_measurement(capability_id)
        severity = EvolutionRisk.HIGH if capability.critical else EvolutionRisk.LOW
        return Diagnostic(capability_id, status, findings, (() if measurement is None else (measurement,)), severity)

    def plan(self, *, evolution_id: str, capability_id: str, problem: str, objective: str,
             risk: EvolutionRisk = EvolutionRisk.LOW, changes: tuple[str, ...] = (),
             sources: tuple[str, ...] = ()) -> ImprovementPlan:
        baseline = self.registry.latest_measurement(capability_id)
        if baseline is None:
            raise ValueError("baseline measurement is required")
        plan = ImprovementPlan(evolution_id, capability_id, problem, baseline, objective, risk, changes, sources)
        plan.validate()
        return plan


class HypothesisManager:
    def create(self, *, evolution_id: str, statement: str, rationale: str,
               expected_metric: str, expected_delta: float) -> Hypothesis:
        hypothesis = Hypothesis(evolution_id, statement, rationale, expected_metric, expected_delta)
        hypothesis.validate()
        return hypothesis


class BenchmarkEngine:
    def compare(self, *, candidate_id: str, metric: str, baseline: float,
                candidate: float, sample_size: int = 1,
                evidence: tuple[str, ...] = ()) -> BenchmarkResult:
        result = BenchmarkResult(candidate_id, metric, baseline, candidate, sample_size, evidence)
        result.validate()
        return result


class RegressionDetector:
    def detect(self, *, candidate_id: str, benchmarks: tuple[BenchmarkResult, ...],
               tolerance: float = 0.0) -> RegressionReport:
        if tolerance < 0:
            raise ValueError("tolerance must be >= 0")
        regressions = tuple(b.metric for b in benchmarks if b.delta < -tolerance)
        return RegressionReport(candidate_id, bool(regressions), regressions,
                                "metric below baseline beyond tolerance" if regressions else "")


class SafetyValidator:
    """Policy boundary for F12; it validates metadata and never executes changes."""

    PROTECTED = frozenset({
        "PermissionManager", "Policy Engine", "Sandbox", "Checkpoint", "Audit",
        "Promotion Rules", "Rollback", "Secrets", "Security Core",
    })

    def review(self, candidate: Candidate, *, changed_components: tuple[str, ...],
               risk: EvolutionRisk, human_approved: bool = False) -> SafetyReview:
        candidate.validate()
        normalized = {item.casefold().strip() for item in changed_components}
        protected = {item.casefold() for item in self.PROTECTED}
        violations = tuple(sorted(item for item in normalized if item in protected))
        high_risk = risk is EvolutionRisk.HIGH or bool(violations)
        passed = not violations and (not high_risk or human_approved)
        return SafetyReview(candidate.candidate_id, passed, high_risk, violations,
                            human_approval_required=high_risk)

    def is_protected(self, component: str) -> bool:
        return component.casefold().strip() in {x.casefold() for x in self.PROTECTED}


class EvolutionEngine:
    def __init__(self, *, capabilities: CapabilityRegistry | None = None,
                 memory: EvolutionMemory | None = None) -> None:
        self.capabilities = capabilities or CapabilityRegistry()
        self.memory = memory or EvolutionMemory()
        self._counter = 0
        self._lock = RLock()

    def next_id(self) -> str:
        with self._lock:
            self._counter += 1
            return f"EVOLUTION-{self._counter:06d}"

    def register_capability(self, capability: Capability) -> None:
        self.capabilities.register(capability)

    def baseline(self, measurement: CapabilityMeasurement) -> None:
        self.capabilities.measure(measurement)

    def start(self, capability_id: str, *, problem: str, objective: str,
              risk: EvolutionRisk = EvolutionRisk.LOW) -> ImprovementPlan:
        evolution_id = self.next_id()
        plan = ImprovementPlanner(self.capabilities).plan(
            evolution_id=evolution_id, capability_id=capability_id,
            problem=problem, objective=objective, risk=risk,
        )
        self.memory.record(EvolutionRecord(
            evolution_id=evolution_id, capability_id=capability_id,
            problem=problem, baseline=plan.baseline, state=EvolutionState.PROPOSED,
        ))
        return plan

    def close(self, record: EvolutionRecord) -> None:
        self.memory.update(record)

    @staticmethod
    def identifier_is_valid(evolution_id: str) -> bool:
        return bool(re.fullmatch(r"EVOLUTION-\\d{6}", evolution_id))
