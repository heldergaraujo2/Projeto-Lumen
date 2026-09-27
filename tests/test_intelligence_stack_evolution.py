import pytest

from app.evolution.intelligence_stack import (
    AdapterKind, IntelligenceStack, IntelligenceStackEvolution, ModelProfile,
    ProviderProfile, StackAdaptation, StackEvaluator, StackEvidence, StackLayer,
    StackRequest,
)


def profile(provider, model, layers, reliability=.9, cost=.1, context=8192):
    return ModelProfile(model, provider, frozenset(layers), context, cost, reliability)


def test_provider_model_contract():
    p = ProviderProfile("local", AdapterKind.LOCAL, (profile("local", "model-a", [StackLayer.REASONING]),))
    p.validate()


def test_provider_rejects_foreign_model():
    with pytest.raises(ValueError):
        ProviderProfile("local", AdapterKind.LOCAL, (profile("remote", "model-a", [StackLayer.REASONING]),))


def test_route_is_deterministic_and_provider_neutral():
    stack = IntelligenceStack()
    stack.register(ProviderProfile("remote", AdapterKind.REMOTE, (profile("remote", "z", [StackLayer.REASONING], .95, .5),)))
    stack.register(ProviderProfile("local", AdapterKind.LOCAL, (profile("local", "a", [StackLayer.REASONING], .95, .1),)))
    request = StackRequest("R1", StackLayer.REASONING, frozenset({StackLayer.REASONING}), .9, .5, 4096)
    assert stack.route(request).model_id == "a"


def test_route_filters_capability_reliability_cost_context():
    stack = IntelligenceStack()
    stack.register(ProviderProfile("p", AdapterKind.MOCK, (
        profile("p", "weak", [StackLayer.REASONING], .7, .1, 1024),
        profile("p", "good", [StackLayer.REASONING, StackLayer.CODING], .95, .2, 8192),
    )))
    result = stack.route(StackRequest("R", StackLayer.CODING, frozenset({StackLayer.CODING}), .9, .3, 4096))
    assert result.model_id == "good"


def test_route_requires_declared_model():
    stack = IntelligenceStack()
    with pytest.raises(LookupError):
        stack.route(StackRequest("R", StackLayer.VISION))


def test_evidence_comparison_requires_same_request_and_metric():
    evaluator = StackEvaluator()
    left = StackEvidence("R", "p", "m1", "accuracy", .8)
    right = StackEvidence("R", "p", "m2", "accuracy", .9)
    assert evaluator.compare(left, right) == -1
    with pytest.raises(ValueError):
        evaluator.compare(left, StackEvidence("X", "p", "m2", "accuracy", .9))


def test_adaptation_requires_isolation_and_evidence():
    evo = IntelligenceStackEvolution()
    adaptation = StackAdaptation("A1", "p", "m2", frozenset({StackLayer.REASONING}), "measured improvement")
    with pytest.raises(ValueError):
        evo.propose(adaptation, ())
    with pytest.raises(ValueError):
        evo.propose(StackAdaptation("A2", "p", "m2", frozenset({StackLayer.REASONING}), "x", False), (
            StackEvidence("R", "p", "m2", "accuracy", .9),
        ))
    evo.propose(adaptation, (StackEvidence("R", "p", "m2", "accuracy", .9),))


def test_no_execution_or_security_surface():
    stack = IntelligenceStack()
    evo = IntelligenceStackEvolution()
    for obj in (stack, evo):
        assert not hasattr(obj, "execute")
        assert not hasattr(obj, "deploy")
        assert not hasattr(obj, "grant_permission")
        assert not hasattr(obj, "change_policy")
