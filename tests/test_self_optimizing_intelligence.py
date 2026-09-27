import pytest

from app.evolution.self_optimizing import (
    OptimizationAssessment,
    OptimizationDimension,
    OptimizationEvidence,
    OptimizationObjective,
    OptimizationPolicy,
    OptimizationRecommendation,
    SelfOptimizingIntelligence,
    StrategyVariant,
)


def make_lab():
    lab = SelfOptimizingIntelligence(policy=OptimizationPolicy(min_samples=2, min_improvement=.01))
    lab.register_objective(
        OptimizationObjective("OPT-OBJ-000001", "reasoning", OptimizationDimension.QUALITY, .80)
    )
    lab.register_variant(StrategyVariant("OPT-VAR-000001", "reasoning", (("temperature", "0.2"),)))
    lab.register_variant(StrategyVariant("OPT-VAR-000002", "reasoning", (("temperature", "0.0"),)))
    return lab


def evidence(eid, vid, score, samples=2):
    return OptimizationEvidence(eid, vid, "OPT-OBJ-000001", score, samples, "benchmark://fixture")


def test_objective_validation():
    with pytest.raises(ValueError):
        OptimizationObjective("bad", "reasoning", OptimizationDimension.QUALITY, .8).validate()


def test_variant_must_be_isolated():
    with pytest.raises(ValueError):
        StrategyVariant("OPT-VAR-000001", "reasoning", (("x", "1"),), isolated=False).validate()


def test_evidence_requires_existing_objective_and_variant():
    lab = SelfOptimizingIntelligence()
    with pytest.raises(KeyError):
        lab.record_evidence(evidence("OPT-EV-000001", "OPT-VAR-000001", .8))


def test_evidence_identity_must_be_unique():
    lab = make_lab()
    lab.record_evidence(evidence("OPT-EV-000001", "OPT-VAR-000001", .8))
    with pytest.raises(ValueError):
        lab.record_evidence(evidence("OPT-EV-000001", "OPT-VAR-000001", .9))


def test_evidence_sample_policy_is_enforced():
    lab = make_lab()
    with pytest.raises(ValueError):
        lab.record_evidence(evidence("OPT-EV-000001", "OPT-VAR-000001", .8, 1))


def test_assessment_is_weighted_by_sample_size():
    lab = make_lab()
    lab.record_evidence(evidence("OPT-EV-000001", "OPT-VAR-000001", .8, 2))
    lab.record_evidence(evidence("OPT-EV-000002", "OPT-VAR-000001", .9, 4))
    result = lab.assess("OPT-VAR-000001", "OPT-OBJ-000001")
    assert isinstance(result, OptimizationAssessment)
    assert result.score == pytest.approx(.8666666667)
    assert result.meets_target


def test_recommendation_selects_deterministic_best_variant():
    lab = make_lab()
    lab.record_evidence(evidence("OPT-EV-000001", "OPT-VAR-000001", .82))
    lab.record_evidence(evidence("OPT-EV-000002", "OPT-VAR-000002", .91))
    recommendation = lab.recommend("reasoning", "OPT-OBJ-000001")
    assert isinstance(recommendation, OptimizationRecommendation)
    assert recommendation.selected_variant_id == "OPT-VAR-000002"
    assert recommendation.requires_human_approval
    assert recommendation.isolated


def test_improvement_threshold_blocks_insufficient_gain():
    lab = make_lab()
    lab.record_evidence(evidence("OPT-EV-000001", "OPT-VAR-000001", .805))
    with pytest.raises(ValueError):
        lab.recommend("reasoning", "OPT-OBJ-000001")


def test_objective_and_variant_must_share_capability():
    lab = SelfOptimizingIntelligence()
    lab.register_objective(OptimizationObjective("OPT-OBJ-000001", "reasoning", OptimizationDimension.QUALITY, .8))
    lab.register_variant(StrategyVariant("OPT-VAR-000001", "coding", (("x", "1"),)))
    with pytest.raises(ValueError):
        lab.record_evidence(OptimizationEvidence("OPT-EV-000001", "OPT-VAR-000001", "OPT-OBJ-000001", .8, 2, "fixture"))


def test_variant_limit_is_bounded():
    lab = SelfOptimizingIntelligence(policy=OptimizationPolicy(max_variants=1))
    lab.register_variant(StrategyVariant("OPT-VAR-000001", "reasoning", (("x", "1"),)))
    with pytest.raises(ValueError):
        lab.register_variant(StrategyVariant("OPT-VAR-000002", "reasoning", (("x", "2"),)))


def test_digest_is_deterministic():
    lab = make_lab()
    lab.record_evidence(evidence("OPT-EV-000001", "OPT-VAR-000001", .82))
    first = lab.digest()
    second = lab.digest()
    assert first == second
    assert len(first) == 64


def test_no_execution_or_authority_surface():
    forbidden = {
        "execute", "run_model", "train", "infer", "deploy",
        "grant_permission", "change_policy", "disable_audit",
        "widen_scope", "execute_driver", "run_browser", "run_tool",
    }
    assert not forbidden.intersection(set(dir(SelfOptimizingIntelligence)))


def test_recommendation_rejects_nonpositive_target_gain():
    lab = SelfOptimizingIntelligence(policy=OptimizationPolicy(min_improvement=0.0))
    lab.register_objective(OptimizationObjective("OPT-OBJ-000001", "reasoning", OptimizationDimension.QUALITY, .8))
    lab.register_variant(StrategyVariant("OPT-VAR-000001", "reasoning", (("x", "1"),)))
    lab.record_evidence(evidence("OPT-EV-000001", "OPT-VAR-000001", .8))
    recommendation = lab.recommend("reasoning", "OPT-OBJ-000001")
    assert recommendation.selected_variant_id == "OPT-VAR-000001"


def test_counts():
    lab = make_lab()
    lab.record_evidence(evidence("OPT-EV-000001", "OPT-VAR-000001", .82))
    assert lab.counts() == {"objectives": 1, "variants": 2, "evidence": 1}
