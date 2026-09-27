from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum


class OptimizationDimension(str, Enum):
    QUALITY = "quality"
    LATENCY = "latency"
    COST = "cost"
    RELIABILITY = "reliability"
    CONTEXT = "context"
    TOOL_SUCCESS = "tool_success"


@dataclass(frozen=True)
class OptimizationObjective:
    objective_id: str
    capability_id: str
    dimension: OptimizationDimension
    target: float
    weight: float = 1.0
    maximize: bool = True

    def validate(self) -> None:
        if not self.objective_id.startswith("OPT-OBJ-"):
            raise ValueError("invalid optimization objective identifier")
        if not self.capability_id.strip():
            raise ValueError("optimization capability is required")
        if not 0.0 <= self.weight <= 1.0 or self.weight == 0.0:
            raise ValueError("objective weight must be in (0, 1]")
        if not 0.0 <= self.target <= 1.0:
            raise ValueError("objective target must be between 0 and 1")


@dataclass(frozen=True)
class StrategyVariant:
    variant_id: str
    capability_id: str
    parameters: tuple[tuple[str, str], ...]
    isolated: bool = True

    def validate(self) -> None:
        if not self.variant_id.startswith("OPT-VAR-"):
            raise ValueError("invalid optimization variant identifier")
        if not self.capability_id.strip():
            raise ValueError("variant capability is required")
        if not self.parameters:
            raise ValueError("variant requires declared parameters")
        if not self.isolated:
            raise ValueError("optimization variants must remain isolated")


@dataclass(frozen=True)
class OptimizationEvidence:
    evidence_id: str
    variant_id: str
    objective_id: str
    score: float
    sample_size: int
    source: str

    def validate(self) -> None:
        if not self.evidence_id.startswith("OPT-EV-"):
            raise ValueError("invalid optimization evidence identifier")
        if not self.variant_id.strip() or not self.objective_id.strip() or not self.source.strip():
            raise ValueError("optimization evidence identity is required")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("optimization evidence score must be between 0 and 1")
        if self.sample_size < 1:
            raise ValueError("optimization evidence sample_size must be >= 1")


@dataclass(frozen=True)
class OptimizationAssessment:
    variant_id: str
    objective_id: str
    score: float
    target: float
    delta_to_target: float
    sample_size: int
    evidence_ids: tuple[str, ...]

    @property
    def meets_target(self) -> bool:
        return self.score >= self.target


@dataclass(frozen=True)
class OptimizationRecommendation:
    recommendation_id: str
    capability_id: str
    selected_variant_id: str
    score: float
    rationale: str
    evidence_ids: tuple[str, ...]
    requires_human_approval: bool = True
    isolated: bool = True

    def validate(self) -> None:
        if not self.recommendation_id.startswith("OPT-REC-"):
            raise ValueError("invalid optimization recommendation identifier")
        if not self.capability_id.strip() or not self.selected_variant_id.strip():
            raise ValueError("recommendation identity is required")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("recommendation score must be between 0 and 1")
        if not self.rationale.strip() or not self.evidence_ids:
            raise ValueError("recommendation requires rationale and evidence")
        if not self.requires_human_approval:
            raise ValueError("self-optimization recommendations require human approval")
        if not self.isolated:
            raise ValueError("recommendation must remain isolated")


@dataclass(frozen=True)
class OptimizationPolicy:
    min_samples: int = 1
    max_variants: int = 20
    min_improvement: float = 0.0

    def validate(self) -> None:
        if self.min_samples < 1 or self.max_variants < 1:
            raise ValueError("optimization limits must be positive")
        if not 0.0 <= self.min_improvement <= 1.0:
            raise ValueError("min_improvement must be between 0 and 1")


class SelfOptimizingIntelligence:
    """F20: deterministic strategy selection over supplied evidence.

    This component never executes a model, changes the live stack, deploys a
    candidate, grants authority, or mutates stable runtime state.
    """

    def __init__(self, *, policy: OptimizationPolicy | None = None) -> None:
        self.policy = policy or OptimizationPolicy()
        self.policy.validate()
        self._objectives: dict[str, OptimizationObjective] = {}
        self._variants: dict[str, StrategyVariant] = {}
        self._evidence: dict[str, OptimizationEvidence] = {}

    def register_objective(self, objective: OptimizationObjective) -> None:
        objective.validate()
        if objective.objective_id in self._objectives:
            raise ValueError("optimization objective already exists")
        self._objectives[objective.objective_id] = objective

    def register_variant(self, variant: StrategyVariant) -> None:
        variant.validate()
        if variant.variant_id in self._variants:
            raise ValueError("optimization variant already exists")
        if sum(v.capability_id == variant.capability_id for v in self._variants.values()) >= self.policy.max_variants:
            raise ValueError("optimization variant limit reached")
        self._variants[variant.variant_id] = variant

    def record_evidence(self, evidence: OptimizationEvidence) -> None:
        evidence.validate()
        objective = self._objectives.get(evidence.objective_id)
        variant = self._variants.get(evidence.variant_id)
        if objective is None or variant is None:
            raise KeyError("optimization evidence references unknown objective or variant")
        if objective.capability_id != variant.capability_id:
            raise ValueError("objective and variant target different capabilities")
        if evidence.sample_size < self.policy.min_samples:
            raise ValueError("evidence sample is below policy minimum")
        if evidence.evidence_id in self._evidence:
            raise ValueError("optimization evidence already exists")
        self._evidence[evidence.evidence_id] = evidence

    def assess(self, variant_id: str, objective_id: str) -> OptimizationAssessment:
        objective = self._objectives[objective_id]
        variant = self._variants[variant_id]
        if objective.capability_id != variant.capability_id:
            raise ValueError("objective and variant target different capabilities")
        evidence = tuple(
            e for e in self._evidence.values()
            if e.variant_id == variant_id and e.objective_id == objective_id
        )
        if not evidence:
            raise ValueError("variant requires optimization evidence")
        score = sum(e.score * e.sample_size for e in evidence) / sum(e.sample_size for e in evidence)
        return OptimizationAssessment(
            variant_id, objective_id, score, objective.target,
            score - objective.target, sum(e.sample_size for e in evidence),
            tuple(e.evidence_id for e in evidence),
        )

    def recommend(self, capability_id: str, objective_id: str) -> OptimizationRecommendation:
        objective = self._objectives[objective_id]
        if objective.capability_id != capability_id:
            raise ValueError("objective targets another capability")
        candidates = [
            self.assess(v.variant_id, objective_id)
            for v in self._variants.values()
            if v.capability_id == capability_id
        ]
        if not candidates:
            raise ValueError("no evidenced optimization variants available")
        candidates.sort(key=lambda a: (-a.score if objective.maximize else a.score, a.variant_id))
        selected = candidates[0]
        if selected.delta_to_target < self.policy.min_improvement:
            raise ValueError("no variant satisfies optimization improvement threshold")
        recommendation = OptimizationRecommendation(
            f"OPT-REC-{len(self._evidence) + 1:06d}",
            capability_id,
            selected.variant_id,
            selected.score,
            f"selected deterministic best-supported variant for {objective.dimension.value}",
            selected.evidence_ids,
        )
        recommendation.validate()
        return recommendation

    def digest(self) -> str:
        payload = {
            "objectives": sorted((x.objective_id, x.capability_id, x.target, x.weight, x.maximize)
                                 for x in self._objectives.values()),
            "variants": sorted((x.variant_id, x.capability_id, x.parameters)
                               for x in self._variants.values()),
            "evidence": sorted((x.evidence_id, x.variant_id, x.objective_id, x.score, x.sample_size)
                               for x in self._evidence.values()),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def counts(self) -> dict[str, int]:
        return {"objectives": len(self._objectives), "variants": len(self._variants), "evidence": len(self._evidence)}
