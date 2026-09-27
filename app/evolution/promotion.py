from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .engine import RegressionDetector, SafetyValidator
from .models import (
    BenchmarkResult, Candidate, Decision, EvolutionRisk, EvolutionState,
    PromotionDecision, RegressionReport, SafetyReview,
)
from .registry import CandidateRegistry, ExperimentManager, PromotionManager


@dataclass(frozen=True)
class BuildEvidence:
    candidate_id: str
    build_id: str
    success: bool
    version: str
    artifacts: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    log_references: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.candidate_id.strip() or not self.build_id.strip() or not self.version.strip():
            raise ValueError("build evidence identity is required")
        if not self.success:
            return
        if not self.artifacts:
            raise ValueError("successful build requires artifacts")
        if not self.tests:
            raise ValueError("successful build requires test evidence")


@dataclass(frozen=True)
class BenchmarkSuite:
    candidate_id: str
    results: tuple[BenchmarkResult, ...]
    minimum_samples: int = 1

    def validate(self) -> None:
        if not self.candidate_id.strip() or not self.results:
            raise ValueError("benchmark suite requires candidate and results")
        if self.minimum_samples < 1:
            raise ValueError("minimum_samples must be >= 1")
        for result in self.results:
            result.validate()
            if result.candidate_id != self.candidate_id:
                raise ValueError("benchmark belongs to another candidate")
            if result.sample_size < self.minimum_samples:
                raise ValueError("benchmark sample is below required minimum")


@dataclass(frozen=True)
class PromotionAssessment:
    candidate_id: str
    build: BuildEvidence
    regression: RegressionReport
    safety: SafetyReview
    eligible: bool
    reasons: tuple[str, ...] = ()

    def validate(self) -> None:
        self.build.validate()
        if self.regression.candidate_id != self.candidate_id:
            raise ValueError("regression report belongs to another candidate")
        if self.safety.candidate_id != self.candidate_id:
            raise ValueError("safety review belongs to another candidate")


class CandidateBuilder:
    """Records a caller-owned build result; it never invokes a compiler or process."""

    def build_record(
        self,
        candidate: Candidate,
        *,
        build_id: str,
        success: bool,
        artifacts: tuple[str, ...] = (),
        tests: tuple[str, ...] = (),
        log_references: tuple[str, ...] = (),
    ) -> BuildEvidence:
        candidate.validate()
        evidence = BuildEvidence(
            candidate.candidate_id, build_id, success, candidate.version,
            artifacts, tests, log_references,
        )
        evidence.validate()
        return evidence


class CandidateBenchmark:
    def __init__(self, regression_detector: RegressionDetector | None = None) -> None:
        self.regression_detector = regression_detector or RegressionDetector()

    def validate_suite(self, suite: BenchmarkSuite) -> BenchmarkSuite:
        suite.validate()
        return suite

    def assess_regression(
        self,
        suite: BenchmarkSuite,
        *,
        tolerance: float = 0.0,
    ) -> RegressionReport:
        suite.validate()
        return self.regression_detector.detect(
            candidate_id=suite.candidate_id,
            benchmarks=suite.results,
            tolerance=tolerance,
        )


class PromotionGate:
    """F15 promotion gate. It records an approval; it never deploys artifacts."""

    def __init__(
        self,
        *,
        candidates: CandidateRegistry | None = None,
        experiments: ExperimentManager | None = None,
        promotions: PromotionManager | None = None,
        safety: SafetyValidator | None = None,
    ) -> None:
        self.candidates = candidates or CandidateRegistry()
        self.experiments = experiments or ExperimentManager()
        self.promotions = promotions or PromotionManager()
        self.safety = safety or SafetyValidator()

    def assess(
        self,
        candidate: Candidate,
        *,
        build: BuildEvidence,
        suite: BenchmarkSuite,
        risk: EvolutionRisk,
        changed_components: tuple[str, ...] = (),
        tolerance: float = 0.0,
        human_approved: bool = False,
    ) -> PromotionAssessment:
        candidate.validate()
        build.validate()
        if build.candidate_id != candidate.candidate_id:
            raise ValueError("build belongs to another candidate")
        suite.validate()
        if suite.candidate_id != candidate.candidate_id:
            raise ValueError("benchmark belongs to another candidate")

        regression = CandidateBenchmark().assess_regression(suite, tolerance=tolerance)
        safety = self.safety.review(
            candidate,
            changed_components=changed_components,
            risk=risk,
            human_approved=human_approved,
        )
        reasons: list[str] = []
        if not build.success:
            reasons.append("build failed")
        if regression.regressed:
            reasons.append("benchmark regression detected")
        if not safety.passed:
            reasons.append("security review failed")
        if not suite.results:
            reasons.append("no benchmark evidence")
        eligible = not reasons
        assessment = PromotionAssessment(
            candidate.candidate_id, build, regression, safety, eligible, tuple(reasons)
        )
        assessment.validate()
        return assessment

    def approve(
        self,
        assessment: PromotionAssessment,
        *,
        human_approved: bool,
        reason: str,
    ) -> PromotionDecision:
        assessment.validate()
        if not assessment.eligible:
            raise ValueError("candidate is not eligible for promotion")
        if not human_approved:
            raise ValueError("promotion requires explicit human approval")
        decision = PromotionDecision(
            assessment.candidate_id, Decision.APPROVED, reason, human_approved=True
        )
        self.promotions.decide(decision)
        return decision

    def reject(self, assessment: PromotionAssessment, *, reason: str) -> PromotionDecision:
        assessment.validate()
        decision = PromotionDecision(
            assessment.candidate_id, Decision.REJECTED, reason, human_approved=False
        )
        self.promotions.decide(decision)
        return decision

    def promote_record(self, candidate_id: str) -> Candidate:
        decision = self.promotions.get(candidate_id)
        if decision is None or decision.decision is not Decision.APPROVED or not decision.human_approved:
            raise ValueError("approved human promotion decision is required")
        candidate = self.candidates.get(candidate_id)
        if candidate.state is not EvolutionState.PROMOTION_PENDING:
            raise ValueError("candidate must be in PROMOTION_PENDING state")
        return self.candidates.update_state(candidate_id, EvolutionState.PROMOTED)
