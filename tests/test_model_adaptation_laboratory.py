import dataclasses

import pytest

from app.evolution.adaptation import (
    AdaptationCandidate,
    AdaptationEvaluator,
    AdaptationEvidence,
    AdaptationExperiment,
    AdaptationKind,
    AdaptationSpec,
    DatasetSpec,
    ModelAdaptationLab,
)
from app.evolution.models import EvolutionRisk


def make_lab():
    lab = ModelAdaptationLab()
    lab.create_workspace(evolution_id="EVOLUTION-000001", workspace_id="ws-1")
    return lab


def make_experiment():
    lab = make_lab()
    spec = AdaptationSpec(
        "ADAPTATION-000001", "EVOLUTION-000001", "local", "base-model",
        "candidate-model", AdaptationKind.LORA, ("attention",), "accuracy",
        "domain adaptation", "ws-1", EvolutionRisk.MEDIUM, 42, (("rank", "16"),),
    )
    experiment = AdaptationExperiment(
        "exp-1", spec, DatasetSpec("data", "1", 100, 80, 10, 10, "fixture", "sha256:abc"),
        (("temperature", "0"),), 100, 1000,
    )
    lab.design(experiment)
    return lab, spec


def make_evidence(spec):
    return AdaptationEvidence(
        spec.adaptation_id, "exp-1", "local", spec.base_model, spec.target_model,
        "accuracy", .70, .82, 100, spec.seed, "repro-1",
        ("artifact://candidate",), ("test://suite",),
    )


def make_candidate(spec):
    return AdaptationCandidate(
        "candidate-1", spec.adaptation_id, spec.evolution_id, "local",
        spec.base_model, spec.target_model, "1.0-adapted", spec.workspace_id,
        "sha256:manifest", ("artifact://candidate",),
    )


def test_dataset_and_adaptation_contracts_validate():
    DatasetSpec("d", "1", 10, 8, 1, 1).validate()
    make_lab()


def test_dataset_split_cannot_exceed_total():
    with pytest.raises(ValueError):
        DatasetSpec("d", "1", 10, 9, 2, 0).validate()


def test_design_requires_existing_isolated_workspace():
    lab = ModelAdaptationLab()
    spec = AdaptationSpec(
        "ADAPTATION-000001", "EVOLUTION-000001", "p", "b", "c",
        AdaptationKind.QUANTIZATION, ("weights",), "accuracy", "x", "missing",
    )
    with pytest.raises(KeyError):
        lab.design(AdaptationExperiment("e", spec, DatasetSpec("d", "1", 1)))


def test_evidence_requires_artifacts_and_tests():
    lab, spec = make_experiment()
    bad = dataclasses.replace(make_evidence(spec), artifact_references=())
    with pytest.raises(ValueError):
        lab.record_evidence(bad)


def test_candidate_requires_evidence_and_isolation():
    lab, spec = make_experiment()
    candidate = make_candidate(spec)
    with pytest.raises(ValueError):
        lab.register_candidate(candidate)
    lab.record_evidence(make_evidence(spec))
    lab.register_candidate(candidate)
    with pytest.raises(ValueError):
        lab.register_candidate(dataclasses.replace(candidate, isolated=False))


def test_benchmark_and_regression_block_poor_candidate():
    lab, spec = make_experiment()
    lab.record_evidence(make_evidence(spec))
    candidate = make_candidate(spec)
    lab.register_candidate(candidate)
    result = lab.benchmark(candidate, metric="accuracy", baseline=.82, candidate_score=.80,
                           sample_size=20, evidence=("benchmark://1",))
    assessment = lab.assess(candidate, benchmarks=(result,))
    assert assessment.regressed
    assert not assessment.eligible


def test_successful_assessment_requires_no_regression():
    lab, spec = make_experiment()
    lab.record_evidence(make_evidence(spec))
    candidate = make_candidate(spec)
    lab.register_candidate(candidate)
    result = lab.benchmark(candidate, metric="accuracy", baseline=.70, candidate_score=.82,
                           sample_size=20, evidence=("benchmark://1",))
    assessment = lab.assess(candidate, benchmarks=(result,))
    assert assessment.eligible
    assert not assessment.regressed


def test_high_risk_requires_human_approval():
    lab, spec = make_experiment()
    lab.record_evidence(make_evidence(spec))
    candidate = make_candidate(spec)
    lab.register_candidate(candidate)
    result = lab.benchmark(candidate, metric="accuracy", baseline=.70, candidate_score=.82,
                           sample_size=20, evidence=("benchmark://1",))
    denied = lab.assess(candidate, benchmarks=(result,), risk=EvolutionRisk.HIGH)
    assert not denied.eligible
    approved = lab.assess(candidate, benchmarks=(result,), risk=EvolutionRisk.HIGH,
                          human_approved=True)
    assert approved.eligible


def test_evaluator_requires_matching_experiment_metric_model_and_seed():
    evaluator = AdaptationEvaluator()
    _, spec = make_experiment()
    a = make_evidence(spec)
    b = dataclasses.replace(a, candidate_model="other")
    assert evaluator.compare(a, b) == 0
    with pytest.raises(ValueError):
        evaluator.compare(a, dataclasses.replace(a, metric="latency"))
    with pytest.raises(ValueError):
        evaluator.compare(a, dataclasses.replace(a, seed=7))


def test_reproducibility_digest_is_deterministic():
    evaluator = AdaptationEvaluator()
    _, spec = make_experiment()
    a = make_evidence(spec)
    assert evaluator.reproducibility_digest(a) == evaluator.reproducibility_digest(a)


def test_no_execution_or_security_bypass_surface():
    names = set(dir(ModelAdaptationLab))
    forbidden = {
        "execute", "run_model", "train", "infer", "download_model", "deploy",
        "grant_permission", "change_policy", "disable_audit", "widen_scope",
    }
    assert not names.intersection(forbidden)


def test_candidate_maps_to_existing_evolution_contract():
    lab, spec = make_experiment()
    lab.record_evidence(make_evidence(spec))
    candidate = make_candidate(spec)
    registered = lab.register_candidate(candidate)
    assert registered.evolution_id == "EVOLUTION-000001"
    assert registered.artifacts == candidate.artifact_references
