from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable

from .models import (
    Capability,
    CapabilityMeasurement,
    Diagnostic,
    EvolutionRisk,
    ImprovementPlan,
)


class ResearchKind(str, Enum):
    DOCUMENTATION = "documentation"
    PAPER = "paper"
    REPOSITORY = "repository"
    BENCHMARK = "benchmark"
    OBSERVATION = "observation"


@dataclass(frozen=True)
class ResearchEvidence:
    evidence_id: str
    kind: ResearchKind
    source: str
    claim: str
    relevance: float = 1.0

    def validate(self) -> None:
        if not self.evidence_id.strip() or not self.source.strip() or not self.claim.strip():
            raise ValueError("research evidence requires identity, source and claim")
        if not 0.0 <= self.relevance <= 1.0:
            raise ValueError("evidence relevance must be between 0 and 1")


@dataclass(frozen=True)
class ResearchQuery:
    query_id: str
    capability_id: str
    question: str
    topics: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.query_id.strip() or not self.capability_id.strip() or not self.question.strip():
            raise ValueError("research query is incomplete")


@dataclass(frozen=True)
class ResearchReport:
    query: ResearchQuery
    evidence: tuple[ResearchEvidence, ...]
    findings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def validate(self) -> None:
        self.query.validate()
        for item in self.evidence:
            item.validate()


@dataclass(frozen=True)
class ImprovementOpportunity:
    capability_id: str
    problem: str
    evidence_ids: tuple[str, ...]
    confidence: float
    rationale: str

    def validate(self) -> None:
        if not self.capability_id.strip() or not self.problem.strip() or not self.rationale.strip():
            raise ValueError("improvement opportunity is incomplete")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("opportunity confidence must be between 0 and 1")


class SelfDiagnostics:
    """Deterministic diagnosis over supplied measurements; never executes improvements."""

    def diagnose(
        self,
        capability: Capability,
        measurements: Iterable[CapabilityMeasurement],
        *,
        threshold: float = 0.8,
    ) -> Diagnostic:
        capability.validate()
        values = tuple(measurements)
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        for item in values:
            item.validate()
            if item.capability_id != capability.capability_id:
                raise ValueError("measurement belongs to another capability")
        if not values:
            return Diagnostic(capability.capability_id, "NO_DATA", ("no measurements",), (), EvolutionRisk.MEDIUM)
        avg = sum(x.score for x in values) / len(values)
        findings = ("below target",) if avg < threshold else ("within target",)
        severity = EvolutionRisk.HIGH if avg < threshold * 0.5 else (
            EvolutionRisk.MEDIUM if avg < threshold else EvolutionRisk.LOW
        )
        status = "DEGRADED" if avg < threshold else "HEALTHY"
        return Diagnostic(capability.capability_id, status, findings, values, severity)


class ImprovementPlanner:
    def create_plan(
        self,
        *,
        evolution_id: str,
        diagnostic: Diagnostic,
        baseline: CapabilityMeasurement,
        objective: str,
        research: ResearchReport | None = None,
    ) -> ImprovementPlan:
        diagnostic.validate()
        baseline.validate()
        if baseline.capability_id != diagnostic.capability_id:
            raise ValueError("baseline belongs to another capability")
        if diagnostic.status == "HEALTHY":
            raise ValueError("cannot create improvement plan for healthy capability")
        sources = tuple(e.source for e in research.evidence) if research else ()
        return ImprovementPlan(
            evolution_id=evolution_id,
            capability_id=diagnostic.capability_id,
            problem="; ".join(diagnostic.findings) or diagnostic.status,
            baseline=baseline,
            objective=objective,
            risk=diagnostic.severity,
            sources=sources,
        )


class ResearchEngine:
    """Consumes supplied evidence or a caller-owned provider; it does not browse or execute tools."""

    def collect(self, query: ResearchQuery, provider: Callable[[ResearchQuery], Iterable[ResearchEvidence]]) -> ResearchReport:
        query.validate()
        evidence = tuple(provider(query))
        report = ResearchReport(query, evidence)
        report.validate()
        return report

    def identify_opportunities(
        self,
        diagnostic: Diagnostic,
        report: ResearchReport,
    ) -> tuple[ImprovementOpportunity, ...]:
        diagnostic.validate()
        report.validate()
        if diagnostic.capability_id != report.query.capability_id:
            raise ValueError("research targets another capability")
        if diagnostic.status == "HEALTHY" or not report.evidence:
            return ()
        confidence = min(1.0, (sum(e.relevance for e in report.evidence) / len(report.evidence)))
        return (
            ImprovementOpportunity(
                diagnostic.capability_id,
                "; ".join(diagnostic.findings),
                tuple(e.evidence_id for e in report.evidence),
                confidence,
                "research evidence is linked to the measured diagnostic gap",
            ),
        )
