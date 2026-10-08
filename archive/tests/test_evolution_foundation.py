import pytest

from app.evolution import (
    BenchmarkEngine, CandidateRegistry, Capability, CapabilityMeasurement,
    CapabilityRegistry, EvolutionEngine, EvolutionMemory, EvolutionState,
    ExperimentManager, EvolutionRisk, HypothesisManager, ImprovementPlanner,
    PromotionManager, RegressionDetector, RollbackManager, SafetyValidator,
)
from app.evolution.models import Candidate, Decision, Experiment, EvolutionRecord, PromotionDecision, RollbackRecord


def registry_with_baseline():
    registry = CapabilityRegistry()
    registry.register(Capability("computer.grounding", "Computer Grounding"))
    registry.measure(CapabilityMeasurement("computer.grounding", .70, "accuracy", 100))
    return registry


def test_capability_registry_requires_known_capability():
    registry = registry_with_baseline()
    assert registry.latest_measurement("computer.grounding").score == .70
    with pytest.raises(KeyError):
        registry.measure(CapabilityMeasurement("unknown", .5, "x"))


def test_measurement_validation():
    with pytest.raises(ValueError):
        CapabilityMeasurement("x", 1.1, "accuracy").validate()


def test_deterministic_evolution_ids_and_format():
    engine = EvolutionEngine(capabilities=registry_with_baseline())
    assert engine.next_id() == "EVOLUTION-000001"
    assert engine.next_id() == "EVOLUTION-000002"
    assert EvolutionEngine.identifier_is_valid("EVOLUTION-000042")
    assert not EvolutionEngine.identifier_is_valid("EVOLUTION-42")
    assert not EvolutionEngine.identifier_is_valid("EVOLUTION-000042x")


def test_start_requires_baseline_and_creates_memory():
    memory = EvolutionMemory()
    engine = EvolutionEngine(capabilities=registry_with_baseline(), memory=memory)
    plan = engine.start("computer.grounding", problem="grounding is weak", objective="increase accuracy")
    assert plan.evolution_id == "EVOLUTION-000001"
    assert memory.get(plan.evolution_id).baseline.score == .70


def test_diagnosis_uses_current_measurement():
    diagnostic = ImprovementPlanner(registry_with_baseline()).diagnose(
        "computer.grounding", status="degraded", findings=("false positives",)
    )
    assert diagnostic.measurements[0].score == .70


def test_hypothesis_contract():
    hypothesis = HypothesisManager().create(
        evolution_id="EVOLUTION-000001", statement="UIA first improves grounding",
        rationale="structured evidence is less ambiguous", expected_metric="accuracy",
        expected_delta=.10,
    )
    assert hypothesis.expected_delta == .10


def test_experiment_lifecycle_is_bounded():
    manager = ExperimentManager()
    manager.create(Experiment("EVOLUTION-000001", "test", "evolution-lab/experiments/1"))
    for state in (
        EvolutionState.RESEARCHING, EvolutionState.HYPOTHESIS, EvolutionState.PLANNED,
        EvolutionState.EXPERIMENTAL, EvolutionState.BUILDING, EvolutionState.TESTING,
        EvolutionState.BENCHMARKING, EvolutionState.SECURITY_REVIEW,
        EvolutionState.PROMOTION_PENDING,
    ):
        manager.transition("EVOLUTION-000001", state)
    with pytest.raises(ValueError):
        manager.transition("EVOLUTION-000001", EvolutionState.PROMOTED)


def test_benchmark_and_regression_detection():
    result = BenchmarkEngine().compare(
        candidate_id="C-1", metric="accuracy", baseline=.70, candidate=.85, sample_size=20
    )
    assert result.delta == pytest.approx(.15)
    regression = RegressionDetector().detect(
        candidate_id="C-1", benchmarks=(result,)
    )
    assert not regression.regressed


def test_regression_is_detected():
    result = BenchmarkEngine().compare(
        candidate_id="C-1", metric="latency_quality", baseline=.80, candidate=.70
    )
    assert RegressionDetector().detect(candidate_id="C-1", benchmarks=(result,)).regressed


def test_safety_blocks_protected_security_core():
    candidate = Candidate("C-1", "EVOLUTION-000001", "1")
    review = SafetyValidator().review(
        candidate, changed_components=("Security Core",), risk=EvolutionRisk.LOW
    )
    assert not review.passed
    assert review.violations


def test_high_risk_requires_human_approval():
    candidate = Candidate("C-1", "EVOLUTION-000001", "1")
    validator = SafetyValidator()
    assert not validator.review(candidate, changed_components=(), risk=EvolutionRisk.HIGH).passed
    assert validator.review(candidate, changed_components=(), risk=EvolutionRisk.HIGH, human_approved=True).passed


def test_promotion_cannot_be_approved_without_human_gate():
    manager = PromotionManager()
    with pytest.raises(ValueError):
        manager.decide(PromotionDecision("C-1", Decision.APPROVED, "looks better"))


def test_rejection_can_be_recorded_without_human_approval():
    manager = PromotionManager()
    manager.decide(PromotionDecision("C-1", Decision.REJECTED, "regression detected"))
    assert manager.get("C-1").decision is Decision.REJECTED


def test_candidate_registry_prevents_duplicates():
    registry = CandidateRegistry()
    candidate = Candidate("C-1", "EVOLUTION-000001", "1")
    registry.register(candidate)
    with pytest.raises(ValueError):
        registry.register(candidate)


def test_rollback_is_memory_only():
    manager = RollbackManager()
    manager.record(RollbackRecord("C-1", "stable-1", "post-promotion regression", "git:abc"))
    assert manager.history()[0].previous_version == "stable-1"


def test_evolution_memory_preserves_failures():
    memory = EvolutionMemory()
    record = EvolutionRecord(
        "EVOLUTION-000001", "computer.grounding", "failed hypothesis",
        decision=Decision.REJECTED, state=EvolutionState.REJECTED,
        result="candidate regressed",
    )
    memory.record(record)
    assert memory.get("EVOLUTION-000001").decision is Decision.REJECTED


def test_safety_validator_never_grants_authority():
    validator = SafetyValidator()
    assert validator.is_protected("PermissionManager")
    assert validator.is_protected("Audit")
