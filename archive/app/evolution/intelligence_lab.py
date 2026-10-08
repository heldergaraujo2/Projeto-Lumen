from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from threading import RLock

from .adaptation import AdaptationEvidence, ModelAdaptationLab
from .diagnostics import ResearchEvidence, ResearchReport, ResearchQuery
from .intelligence_stack import StackEvidence
from .lab import EvolutionLab, LabWorkspace
from .models import Capability, CapabilityMeasurement, EvolutionRisk
from .registry import CapabilityRegistry, EvolutionMemory, ExperimentManager, CandidateRegistry


class IntelligenceTrack(str, Enum):
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    VISION = "vision"
    CODING = "coding"
    RESEARCH = "research"
    PLANNING = "planning"
    COMPUTER_CONTROL = "computer_control"
    WORKFLOW_LEARNING = "workflow_learning"
    AUTONOMY = "autonomy"


@dataclass(frozen=True)
class IntelligenceCapability:
    capability_id: str
    name: str
    track: IntelligenceTrack
    description: str = ""
    critical: bool = False

    def validate(self) -> None:
        if not self.capability_id.strip() or not self.name.strip():
            raise ValueError("intelligence capability identity is required")
        if not isinstance(self.track, IntelligenceTrack):
            raise ValueError("invalid intelligence track")


@dataclass(frozen=True)
class IntelligenceBaseline:
    capability_id: str
    measurement: CapabilityMeasurement
    source: str
    recorded_at: str

    def validate(self) -> None:
        if self.measurement.capability_id != self.capability_id:
            raise ValueError("baseline measurement belongs to another capability")
        self.measurement.validate()
        if not self.source.strip() or not self.recorded_at.strip():
            raise ValueError("baseline provenance is required")


@dataclass(frozen=True)
class IntelligenceResearch:
    research_id: str
    capability_id: str
    query: ResearchQuery
    report: ResearchReport

    def validate(self) -> None:
        if not self.research_id.strip() or not self.capability_id.strip():
            raise ValueError("research identity is required")
        if self.query.capability_id != self.capability_id:
            raise ValueError("research query targets another capability")
        self.query.validate()
        self.report.validate()
        if self.report.query.query_id != self.query.query_id:
            raise ValueError("research report belongs to another query")


@dataclass(frozen=True)
class IntelligenceHypothesis:
    hypothesis_id: str
    evolution_id: str
    capability_id: str
    statement: str
    expected_metric: str
    expected_delta: float
    risk: EvolutionRisk = EvolutionRisk.MEDIUM

    def validate(self) -> None:
        if not self.hypothesis_id.startswith("INT-HYP-"):
            raise ValueError("invalid intelligence hypothesis identifier")
        if not self.evolution_id.startswith("EVOLUTION-"):
            raise ValueError("invalid evolution identifier")
        if not self.capability_id.strip() or not self.statement.strip():
            raise ValueError("intelligence hypothesis is incomplete")
        if not self.expected_metric.strip():
            raise ValueError("hypothesis metric is required")


@dataclass(frozen=True)
class IntelligenceFinding:
    finding_id: str
    capability_id: str
    evidence_ids: tuple[str, ...]
    baseline_score: float
    candidate_score: float
    confidence: float
    conclusion: str
    limitations: tuple[str, ...] = ()

    @property
    def delta(self) -> float:
        return self.candidate_score - self.baseline_score

    def validate(self) -> None:
        if not self.finding_id.startswith("INT-FIND-"):
            raise ValueError("invalid intelligence finding identifier")
        if not self.capability_id.strip() or not self.evidence_ids:
            raise ValueError("finding identity and evidence are required")
        if not 0.0 <= self.baseline_score <= 1.0 or not 0.0 <= self.candidate_score <= 1.0:
            raise ValueError("finding scores must be between 0 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("finding confidence must be between 0 and 1")
        if not self.conclusion.strip():
            raise ValueError("finding conclusion is required")


@dataclass(frozen=True)
class IntelligenceOpportunity:
    opportunity_id: str
    capability_id: str
    problem: str
    research_ids: tuple[str, ...]
    priority: float
    risk: EvolutionRisk
    rationale: str

    def validate(self) -> None:
        if not self.opportunity_id.startswith("INT-OPP-"):
            raise ValueError("invalid intelligence opportunity identifier")
        if not self.capability_id.strip() or not self.problem.strip():
            raise ValueError("intelligence opportunity is incomplete")
        if not self.research_ids:
            raise ValueError("opportunity requires research references")
        if not 0.0 <= self.priority <= 1.0:
            raise ValueError("opportunity priority must be between 0 and 1")
        if not self.rationale.strip():
            raise ValueError("opportunity rationale is required")


@dataclass(frozen=True)
class IntelligenceAssessment:
    capability_id: str
    baseline: IntelligenceBaseline
    findings: tuple[IntelligenceFinding, ...]
    opportunities: tuple[IntelligenceOpportunity, ...]
    evidence_count: int
    regression_detected: bool

    def validate(self) -> None:
        self.baseline.validate()
        for finding in self.findings:
            finding.validate()
            if finding.capability_id != self.capability_id:
                raise ValueError("finding targets another capability")
        for opportunity in self.opportunities:
            opportunity.validate()
            if opportunity.capability_id != self.capability_id:
                raise ValueError("opportunity targets another capability")
        if self.evidence_count < 0:
            raise ValueError("evidence count cannot be negative")


class IntelligenceEvidenceLedger:
    def __init__(self, *, history_limit: int = 1000) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be >= 1")
        self._history_limit = history_limit
        self._items: dict[str, object] = {}
        self._order: list[str] = []
        self._lock = RLock()

    def record(self, evidence_id: str, evidence: object) -> None:
        if not evidence_id.strip():
            raise ValueError("evidence identity is required")
        validator = getattr(evidence, "validate", None)
        if validator is None or not callable(validator):
            raise ValueError("ledger evidence must expose validate()")
        validator()
        with self._lock:
            if evidence_id in self._items:
                raise ValueError("evidence already recorded")
            self._items[evidence_id] = evidence
            self._order.append(evidence_id)
            while len(self._order) > self._history_limit:
                expired = self._order.pop(0)
                self._items.pop(expired, None)

    def get(self, evidence_id: str) -> object:
        with self._lock:
            return self._items[evidence_id]

    def ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._order)

    def size(self) -> int:
        return len(self._order)


class LumenIntelligenceLab:
    """F19 research layer; coordinates evidence but never executes it."""

    def __init__(self, *, capabilities: CapabilityRegistry | None = None,
                 memory: EvolutionMemory | None = None,
                 evolution_lab: EvolutionLab | None = None,
                 adaptation_lab: ModelAdaptationLab | None = None,
                 experiments: ExperimentManager | None = None,
                 candidates: CandidateRegistry | None = None,
                 history_limit: int = 1000) -> None:
        self.capabilities = capabilities or CapabilityRegistry()
        self.memory = memory or EvolutionMemory()
        self.evolution_lab = evolution_lab or EvolutionLab(experiments=experiments, candidates=candidates)
        self.adaptation_lab = adaptation_lab or ModelAdaptationLab(evolution_lab=self.evolution_lab)
        self.evidence = IntelligenceEvidenceLedger(history_limit=history_limit)
        self._capabilities: dict[str, IntelligenceCapability] = {}
        self._baselines: dict[str, IntelligenceBaseline] = {}
        self._research: dict[str, IntelligenceResearch] = {}
        self._hypotheses: dict[str, IntelligenceHypothesis] = {}
        self._findings: dict[str, IntelligenceFinding] = {}
        self._opportunities: dict[str, IntelligenceOpportunity] = {}

    def register_capability(self, capability: IntelligenceCapability) -> None:
        capability.validate()
        if capability.capability_id in self._capabilities:
            raise ValueError("intelligence capability already exists")
        self._capabilities[capability.capability_id] = capability
        self.capabilities.register(Capability(capability.capability_id, capability.name, capability.description, "Lumen Intelligence Lab", capability.critical, True))

    def capability(self, capability_id: str) -> IntelligenceCapability:
        try:
            return self._capabilities[capability_id]
        except KeyError as exc:
            raise KeyError("unknown intelligence capability") from exc

    def record_baseline(self, baseline: IntelligenceBaseline) -> None:
        baseline.validate()
        self.capability(baseline.capability_id)
        self.capabilities.measure(baseline.measurement)
        evidence_id = f"BASELINE:{baseline.capability_id}:{baseline.recorded_at}"
        self.evidence.record(evidence_id, baseline)
        self._baselines[baseline.capability_id] = baseline

    def baseline(self, capability_id: str) -> IntelligenceBaseline:
        try:
            return self._baselines[capability_id]
        except KeyError as exc:
            raise KeyError("baseline not recorded") from exc

    def record_research(self, research: IntelligenceResearch) -> None:
        research.validate()
        self.capability(research.capability_id)
        if research.research_id in self._research:
            raise ValueError("research already recorded")
        self._research[research.research_id] = research
        for item in research.report.evidence:
            self.evidence.record(f"RESEARCH:{research.research_id}:{item.evidence_id}", item)

    def research(self, research_id: str) -> IntelligenceResearch:
        try:
            return self._research[research_id]
        except KeyError as exc:
            raise KeyError("unknown intelligence research") from exc

    def propose_hypothesis(self, hypothesis: IntelligenceHypothesis) -> None:
        hypothesis.validate()
        self.capability(hypothesis.capability_id)
        if hypothesis.hypothesis_id in self._hypotheses:
            raise ValueError("hypothesis already exists")
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis

    def record_stack_evidence(self, evidence: StackEvidence) -> None:
        evidence.validate()
        self.evidence.record(f"STACK:{evidence.request_id}:{evidence.provider_id}:{evidence.model_id}:{evidence.metric}", evidence)

    def record_adaptation_evidence(self, evidence: AdaptationEvidence) -> None:
        evidence.validate()
        self.evidence.record(f"ADAPTATION:{evidence.experiment_id}:{evidence.reproducibility_key}", evidence)

    def assess(self, capability_id: str, *, candidate_score: float, finding_id: str, evidence_ids: tuple[str, ...], conclusion: str, confidence: float, limitations: tuple[str, ...] = ()) -> IntelligenceAssessment:
        baseline = self.baseline(capability_id)
        if not evidence_ids:
            raise ValueError("assessment requires evidence")
        for evidence_id in evidence_ids:
            self.evidence.get(evidence_id)
        finding = IntelligenceFinding(finding_id, capability_id, evidence_ids, baseline.measurement.score, candidate_score, confidence, conclusion, limitations)
        finding.validate()
        if finding_id in self._findings:
            raise ValueError("finding already exists")
        self._findings[finding_id] = finding
        opportunities = tuple(x for x in self._opportunities.values() if x.capability_id == capability_id)
        assessment = IntelligenceAssessment(capability_id, baseline, (finding,), opportunities, len(evidence_ids), candidate_score < baseline.measurement.score)
        assessment.validate()
        self.evidence.record(f"FINDING:{finding_id}", finding)
        return assessment

    def create_opportunity(self, opportunity: IntelligenceOpportunity) -> None:
        opportunity.validate()
        self.capability(opportunity.capability_id)
        for research_id in opportunity.research_ids:
            self.research(research_id)
        if opportunity.opportunity_id in self._opportunities:
            raise ValueError("opportunity already exists")
        self._opportunities[opportunity.opportunity_id] = opportunity

    def workspace(self, *, evolution_id: str, workspace_id: str) -> LabWorkspace:
        return self.adaptation_lab.create_workspace(evolution_id=evolution_id, workspace_id=workspace_id)

    def digest(self, capability_id: str) -> str:
        self.capability(capability_id)
        payload = {
            "capability_id": capability_id,
            "baseline": self.baseline(capability_id).measurement.score,
            "research": sorted(x.research_id for x in self._research.values() if x.capability_id == capability_id),
            "hypotheses": sorted(x.hypothesis_id for x in self._hypotheses.values() if x.capability_id == capability_id),
            "findings": sorted(x.finding_id for x in self._findings.values() if x.capability_id == capability_id),
            "opportunities": sorted(x.opportunity_id for x in self._opportunities.values() if x.capability_id == capability_id),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def summary(self) -> dict[str, int]:
        return {"capabilities": len(self._capabilities), "baselines": len(self._baselines), "research": len(self._research), "hypotheses": len(self._hypotheses), "findings": len(self._findings), "opportunities": len(self._opportunities), "evidence": self.evidence.size()}