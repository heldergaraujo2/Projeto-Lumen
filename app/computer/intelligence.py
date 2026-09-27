from __future__ import annotations

from dataclasses import dataclass

from app.computer_control.actions import CCActionRequest
from app.computer_control.verification import VerificationResult
from .actions import ActionPlanner, ExecutionResolver
from .models import ActionPlan, ComputerObservation, ExecutionMechanism, IntelligenceResult
from .perception import PerceptionPipeline
from .recovery import IntelligenceRecovery
from .regression import RegressionDetector, RegressionResult
from .targeting import TargetingEngine
from .verification import IntelligenceVerifier


@dataclass
class ComputerIntelligence:
    """Computer loop: observe → understand → target → plan → act → verify → recover."""

    perception: PerceptionPipeline
    targeting: TargetingEngine
    actions: ActionPlanner
    execution: ExecutionResolver
    verification: IntelligenceVerifier
    recovery_engine: IntelligenceRecovery
    regression: RegressionDetector

    @classmethod
    def from_provider(cls, provider, *, min_confidence: float = 0.80, max_recovery_attempts: int = 2):
        return cls(
            perception=PerceptionPipeline(provider),
            targeting=TargetingEngine(min_confidence=min_confidence),
            actions=ActionPlanner(),
            execution=ExecutionResolver(),
            verification=IntelligenceVerifier(),
            recovery_engine=IntelligenceRecovery(max_attempts=max_recovery_attempts),
            regression=RegressionDetector(),
        )

    def observe(self) -> ComputerObservation:
        return self.perception.observe()

    def identify_state(self, observation: ComputerObservation) -> str:
        observation.validate()
        return observation.fingerprint

    def resolve_target(self, observation: ComputerObservation, label: str, *, candidates=()):
        return self.targeting.resolve(observation, label, candidates=tuple(candidates))

    def plan_click(self, observation: ComputerObservation, label: str, *, rationale: str = "", candidates=()):
        target = self.resolve_target(observation, label, candidates=candidates)
        if target.target is None:
            return IntelligenceResult(False, target.reason, observation=observation, target=target)
        intent = self.actions.click(target.target, rationale=rationale)
        plan = self.actions.build(observation.fingerprint, intent, rationale=rationale)
        return IntelligenceResult(True, "action_planned", observation, target, plan)

    def resolve_plan_requests(self, plan: ActionPlan, *, mechanism: ExecutionMechanism) -> tuple[CCActionRequest, ...]:
        plan.validate()
        return tuple(self.execution.resolve(intent, mechanism=mechanism) for intent in plan.intents)

    def verify_target(self, observation: ComputerObservation, label: str) -> VerificationResult:
        return self.verification.target(observation, label=label)

    def verify_state_change(self, before: ComputerObservation, after: ComputerObservation) -> VerificationResult:
        return self.verification.state_changed(before, after)

    def verify_state_unchanged(self, before: ComputerObservation, after: ComputerObservation) -> VerificationResult:
        return self.verification.state_unchanged(before, after)

    def compare_regression(self, *, baseline: ComputerObservation, candidate: ComputerObservation) -> RegressionResult:
        return self.regression.compare_fingerprints(
            baseline=baseline.fingerprint,
            candidate=candidate.fingerprint,
        )

    def recovery(self, *, failure_reason: str, attempt: int):
        return self.recovery_engine.decide(failure_reason=failure_reason, attempt=attempt)
