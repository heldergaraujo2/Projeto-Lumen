from __future__ import annotations

"""F24 — Evolution Runtime Orchestrator.

Coordinates existing evolution gates. It does not execute providers, tools,
experiments, builds, deployments, drivers, or promotion side effects.
"""

from dataclasses import dataclass, replace
from threading import RLock

from .diagnostics import Diagnostic, ImprovementOpportunity, ResearchReport
from .engine import EvolutionEngine, HypothesisManager, SafetyValidator
from .models import (
    BenchmarkResult, Candidate, Decision, EvolutionRecord, EvolutionRisk,
    EvolutionState, Hypothesis, ImprovementPlan, SafetyReview,
)
from .promotion import BenchmarkSuite, BuildEvidence, PromotionAssessment, PromotionGate
from .registry import CandidateRegistry, ExperimentManager, EvolutionMemory


@dataclass(frozen=True)
class OrchestrationContext:
    evolution_id: str
    capability_id: str
    state: EvolutionState
    risk: EvolutionRisk
    diagnostic: Diagnostic | None = None
    research: ResearchReport | None = None
    opportunity: ImprovementOpportunity | None = None
    hypothesis: Hypothesis | None = None
    plan: ImprovementPlan | None = None
    experiment_id: str | None = None
    candidate: Candidate | None = None
    build: BuildEvidence | None = None
    benchmark: BenchmarkSuite | None = None
    safety: SafetyReview | None = None
    promotion: PromotionAssessment | None = None
    approval: bool = False
    monitoring_requested: bool = False

    def validate(self) -> None:
        if not self.evolution_id.startswith("EVOLUTION-"):
            raise ValueError("invalid evolution identity")
        if not self.capability_id.strip():
            raise ValueError("capability is required")
        if self.candidate is not None and self.candidate.evolution_id != self.evolution_id:
            raise ValueError("candidate belongs to another evolution")
        if self.plan is not None and self.plan.evolution_id != self.evolution_id:
            raise ValueError("plan belongs to another evolution")


class EvolutionRuntimeOrchestrator:
    """F24 coordinator for a single bounded evolution cycle.

    Every external/expensive operation is represented by caller-supplied
    evidence. The orchestrator only validates prerequisites and advances
    deterministic state; it never performs the operation itself.
    """

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
        EvolutionState.APPROVED: {EvolutionState.PROMOTED, EvolutionState.REJECTED},
        EvolutionState.PROMOTED: {EvolutionState.MONITORED, EvolutionState.ROLLED_BACK},
        EvolutionState.MONITORED: {EvolutionState.ROLLED_BACK},
    }

    def __init__(
        self,
        *,
        evolution: EvolutionEngine | None = None,
        memory: EvolutionMemory | None = None,
        experiments: ExperimentManager | None = None,
        candidates: CandidateRegistry | None = None,
        promotion: PromotionGate | None = None,
        safety: SafetyValidator | None = None,
    ) -> None:
        self.evolution = evolution or EvolutionEngine(memory=memory)
        self.memory = memory or self.evolution.memory
        self.experiments = experiments or ExperimentManager()
        self.candidates = candidates or CandidateRegistry()
        self.safety = safety or SafetyValidator()
        self.promotion = promotion or PromotionGate(
            candidates=self.candidates, experiments=self.experiments, safety=self.safety
        )
        self._contexts: dict[str, OrchestrationContext] = {}
        self._counter = 0
        self._lock = RLock()

    def _next_evolution_id(self) -> str:
        return self.evolution.next_id()

    def _transition(self, ctx: OrchestrationContext, state: EvolutionState, **changes) -> OrchestrationContext:
        if state not in self._allowed.get(ctx.state, set()):
            raise ValueError(f"invalid orchestration transition: {ctx.state.value} -> {state.value}")
        updated = replace(ctx, state=state, **changes)
        updated.validate()
        self._contexts[ctx.evolution_id] = updated
        return updated

    def detect(self, *, capability_id: str, problem: str, risk: EvolutionRisk = EvolutionRisk.LOW) -> OrchestrationContext:
        plan = self.evolution.start(capability_id, problem=problem, objective=problem, risk=risk)
        record = self.memory.get(plan.evolution_id)
        updated = replace(record, state=EvolutionState.PROPOSED)
        self.memory.update(updated)
        ctx = OrchestrationContext(plan.evolution_id, capability_id, EvolutionState.PROPOSED, risk, plan=plan)
        ctx.validate()
        self._contexts[ctx.evolution_id] = ctx
        return ctx

    def investigate(self, evolution_id: str, diagnostic: Diagnostic) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        diagnostic.validate()
        if diagnostic.capability_id != ctx.capability_id:
            raise ValueError("diagnostic targets another capability")
        return self._transition(ctx, EvolutionState.RESEARCHING, diagnostic=diagnostic)

    def research(self, evolution_id: str, report: ResearchReport, opportunity: ImprovementOpportunity | None = None) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        report.validate()
        if report.query.capability_id != ctx.capability_id:
            raise ValueError("research targets another capability")
        if opportunity is not None:
            opportunity.validate()
            if opportunity.capability_id != ctx.capability_id:
                raise ValueError("opportunity targets another capability")
        return self._transition(ctx, EvolutionState.HYPOTHESIS, research=report, opportunity=opportunity)

    def hypothesize(self, evolution_id: str, hypothesis: Hypothesis) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        hypothesis.validate()
        if hypothesis.evolution_id != evolution_id:
            raise ValueError("hypothesis belongs to another evolution")
        return self._transition(ctx, EvolutionState.PLANNED, hypothesis=hypothesis)

    def request_experiment(self, evolution_id: str, *, experiment_id: str, workspace: str, changes: tuple[str, ...] = ()) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        if not experiment_id.strip() or not workspace.strip():
            raise ValueError("experiment request requires identity and isolated workspace")
        from .models import Experiment
        self.experiments.create(Experiment(evolution_id, experiment_id, workspace, EvolutionState.PROPOSED, changes))
        return self._transition(ctx, EvolutionState.EXPERIMENTAL, experiment_id=experiment_id)

    def submit_build_request(self, evolution_id: str) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        if not ctx.experiment_id:
            raise ValueError("experiment request is required")
        return self._transition(ctx, EvolutionState.BUILDING)

    def record_candidate(self, evolution_id: str, candidate: Candidate) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        candidate.validate()
        if candidate.evolution_id != evolution_id:
            raise ValueError("candidate belongs to another evolution")
        self.candidates.register(candidate)
        return self._transition(ctx, EvolutionState.TESTING, candidate=candidate)

    def record_build(self, evolution_id: str, build: BuildEvidence) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        if ctx.candidate is None or build.candidate_id != ctx.candidate.candidate_id:
            raise ValueError("build evidence belongs to another candidate")
        build.validate()
        if not build.success:
            return self._transition(ctx, EvolutionState.REJECTED, build=build)
        return self._transition(ctx, EvolutionState.BENCHMARKING, build=build)

    def benchmark(self, evolution_id: str, suite: BenchmarkSuite) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        if ctx.candidate is None or suite.candidate_id != ctx.candidate.candidate_id:
            raise ValueError("benchmark belongs to another candidate")
        suite.validate()
        return self._transition(ctx, EvolutionState.SECURITY_REVIEW, benchmark=suite)

    def security_review(self, evolution_id: str, *, changed_components: tuple[str, ...] = ()) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        if ctx.candidate is None or ctx.build is None or ctx.benchmark is None:
            raise ValueError("candidate, build and benchmark evidence are required")
        assessment = self.promotion.assess(
            ctx.candidate, build=ctx.build, suite=ctx.benchmark, risk=ctx.risk,
            changed_components=changed_components,
        )
        if not assessment.eligible:
            safety = assessment.safety
            return self._transition(ctx, EvolutionState.REJECTED, safety=safety, promotion=assessment)
        return self._transition(ctx, EvolutionState.PROMOTION_PENDING, safety=assessment.safety, promotion=assessment)

    def request_approval(self, evolution_id: str) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        if ctx.promotion is None or not ctx.promotion.eligible:
            raise ValueError("eligible promotion assessment is required")
        return ctx

    def approve(self, evolution_id: str, *, reason: str) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        if ctx.promotion is None or not ctx.promotion.eligible:
            raise ValueError("eligible promotion assessment is required")
        self.promotion.submit_for_promotion(ctx.promotion)
        self.promotion.approve(ctx.promotion, human_approved=True, reason=reason)
        return self._transition(ctx, EvolutionState.APPROVED, approval=True)

    def promote(self, evolution_id: str) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        if not ctx.approval:
            raise ValueError("explicit human approval is required")
        if ctx.candidate is None:
            raise ValueError("candidate is required")
        self.promotion.promote_record(ctx.candidate.candidate_id)
        return self._transition(ctx, EvolutionState.PROMOTED)

    def monitor(self, evolution_id: str) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        if ctx.state is not EvolutionState.PROMOTED:
            raise ValueError("promotion must be completed before monitoring")
        return self._transition(ctx, EvolutionState.MONITORED, monitoring_requested=True)

    def reject(self, evolution_id: str, *, reason: str) -> OrchestrationContext:
        ctx = self._get(evolution_id)
        if not reason.strip():
            raise ValueError("rejection reason is required")
        return self._transition(ctx, EvolutionState.REJECTED)

    def get(self, evolution_id: str) -> OrchestrationContext:
        return self._get(evolution_id)

    def list(self) -> tuple[OrchestrationContext, ...]:
        with self._lock:
            return tuple(self._contexts.values())

    def digest(self, evolution_id: str) -> str:
        import hashlib, json
        ctx = self._get(evolution_id)
        payload = {
            "evolution_id": ctx.evolution_id, "capability_id": ctx.capability_id,
            "state": ctx.state.value, "risk": ctx.risk.value,
            "experiment_id": ctx.experiment_id,
            "candidate_id": None if ctx.candidate is None else ctx.candidate.candidate_id,
            "approval": ctx.approval, "monitoring_requested": ctx.monitoring_requested,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _get(self, evolution_id: str) -> OrchestrationContext:
        try:
            return self._contexts[evolution_id]
        except KeyError as exc:
            raise KeyError("unknown evolution orchestration") from exc
