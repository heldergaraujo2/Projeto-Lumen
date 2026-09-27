import pytest

from app.evolution import (
    Candidate, CandidateBenchmark, CandidateBuilder, CandidateRegistry,
    EvolutionRisk, EvolutionState, BenchmarkResult, PromotionGate,
)
from app.evolution.promotion import BenchmarkSuite, BuildEvidence


def candidate():
    return Candidate("C-1", "EVOLUTION-000001", "1.0")


def build_ok():
    return BuildEvidence("C-1", "BUILD-1", True, "1.0", ("artifact.bin",), ("pytest",))


def suite_ok():
    return BenchmarkSuite("C-1", (BenchmarkResult("C-1", "accuracy", .70, .85, 20),))


def test_successful_build_requires_artifacts_and_tests():
    CandidateBuilder().build_record(candidate(), build_id="B", success=True, artifacts=("x",), tests=("t",))


def test_successful_build_without_artifact_rejected():
    with pytest.raises(ValueError):
        CandidateBuilder().build_record(candidate(), build_id="B", success=True, tests=("t",))


def test_failed_build_can_be_recorded_without_artifacts():
    result = CandidateBuilder().build_record(candidate(), build_id="B", success=False)
    assert not result.success


def test_benchmark_suite_requires_same_candidate():
    with pytest.raises(ValueError):
        BenchmarkSuite("C-1", (BenchmarkResult("C-2", "accuracy", .7, .8),)).validate()


def test_benchmark_minimum_sample_is_enforced():
    with pytest.raises(ValueError):
        BenchmarkSuite("C-1", (BenchmarkResult("C-1", "accuracy", .7, .8, 1),), minimum_samples=2).validate()


def test_benchmark_assessment_detects_regression():
    suite = BenchmarkSuite("C-1", (BenchmarkResult("C-1", "accuracy", .8, .7),))
    report = CandidateBenchmark().assess_regression(suite)
    assert report.regressed


def test_promotion_assessment_requires_build_benchmark_and_safety():
    registry = CandidateRegistry()
    c = candidate()
    registry.register(c)
    gate = PromotionGate(candidates=registry)
    assessment = gate.assess(c, build=build_ok(), suite=suite_ok(), risk=EvolutionRisk.LOW)
    assert assessment.eligible


def test_high_risk_requires_human_approval_before_eligible():
    registry = CandidateRegistry()
    c = candidate()
    registry.register(c)
    gate = PromotionGate(candidates=registry)
    assessment = gate.assess(c, build=build_ok(), suite=suite_ok(), risk=EvolutionRisk.HIGH)
    assert not assessment.eligible
    assert "security review failed" in assessment.reasons


def test_protected_component_blocks_promotion():
    registry = CandidateRegistry()
    c = candidate()
    registry.register(c)
    gate = PromotionGate(candidates=registry)
    assessment = gate.assess(
        c, build=build_ok(), suite=suite_ok(), risk=EvolutionRisk.LOW,
        changed_components=("Audit",),
    )
    assert not assessment.eligible


def test_regression_blocks_promotion():
    registry = CandidateRegistry()
    c = candidate()
    registry.register(c)
    gate = PromotionGate(candidates=registry)
    assessment = gate.assess(
        c, build=build_ok(),
        suite=BenchmarkSuite("C-1", (BenchmarkResult("C-1", "accuracy", .8, .7),)),
        risk=EvolutionRisk.LOW,
    )
    assert not assessment.eligible


def test_approval_requires_human_and_eligible_candidate():
    registry = CandidateRegistry()
    c = candidate()
    registry.register(c)
    gate = PromotionGate(candidates=registry)
    assessment = gate.assess(c, build=build_ok(), suite=suite_ok(), risk=EvolutionRisk.LOW)
    with pytest.raises(ValueError):
        gate.approve(assessment, human_approved=False, reason="x")


def test_approved_candidate_can_be_promoted_as_metadata_only():
    registry = CandidateRegistry()
    c = candidate()
    registry.register(c)
    gate = PromotionGate(candidates=registry)
    assessment = gate.assess(c, build=build_ok(), suite=suite_ok(), risk=EvolutionRisk.LOW)
    gate.submit_for_promotion(assessment)
    gate.approve(assessment, human_approved=True, reason="validated")
    promoted = gate.promote_record("C-1")
    assert promoted.state is EvolutionState.PROMOTED


def test_promotion_requires_pending_state():
    registry = CandidateRegistry()
    c = candidate()
    registry.register(c)
    gate = PromotionGate(candidates=registry)
    assessment = gate.assess(c, build=build_ok(), suite=suite_ok(), risk=EvolutionRisk.LOW)
    gate.approve(assessment, human_approved=True, reason="validated")
    with pytest.raises(ValueError):
        gate.promote_record("C-1")


def test_promotion_has_no_execution_surface():
    gate = PromotionGate()
    assert not hasattr(gate, "execute")
    assert not hasattr(gate, "deploy")
    assert not hasattr(gate, "run_driver")


def test_build_and_benchmark_have_no_execution_surface():
    assert not hasattr(CandidateBuilder(), "execute")
    assert not hasattr(CandidateBenchmark(), "run_process")


def test_ineligible_candidate_cannot_enter_promotion_pending():
    registry = CandidateRegistry(); c = candidate(); registry.register(c)
    gate = PromotionGate(candidates=registry)
    assessment = gate.assess(
        c, build=build_ok(),
        suite=BenchmarkSuite("C-1", (BenchmarkResult("C-1", "accuracy", .8, .7),)),
        risk=EvolutionRisk.LOW,
    )
    with pytest.raises(ValueError):
        gate.submit_for_promotion(assessment)


def test_rejection_moves_candidate_to_rejected_state():
    registry = CandidateRegistry(); c = candidate(); registry.register(c)
    gate = PromotionGate(candidates=registry)
    assessment = gate.assess(c, build=build_ok(), suite=suite_ok(), risk=EvolutionRisk.LOW)
    gate.reject(assessment, reason="not selected")
    assert registry.get("C-1").state is EvolutionState.REJECTED
