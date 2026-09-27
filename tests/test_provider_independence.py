import pytest

from app.evolution.intelligence_stack import AdapterKind, ModelProfile, ProviderProfile, StackLayer
from app.evolution.provider_independence import (
    IndependenceRequirement, ProviderCapabilityContract, ProviderCompatibility,
    ProviderFallbackPolicy, ProviderIndependenceAssessment, ProviderIndependenceLab,
    ProviderMigrationPlan, ensure_f21_no_execution_surface,
)


def provider(pid, mid, *, reliability=.9, context=8192, cost=.1, enabled=True):
    return ProviderProfile(pid, AdapterKind.LOCAL, (ModelProfile(mid, pid, frozenset({StackLayer.REASONING, StackLayer.CODING}), context, cost, reliability, enabled),), enabled)


def contract():
    return ProviderCapabilityContract(
        "contract-reasoning", frozenset({StackLayer.REASONING}),
        min_reliability=.8, min_context_window=4096, max_cost_per_unit=.5,
        requirements=frozenset({IndependenceRequirement.CAPABILITY, IndependenceRequirement.FAILOVER}),
    )


def test_contract_validation():
    contract().validate()


def test_contract_rejects_invalid_limits():
    with pytest.raises(ValueError):
        ProviderCapabilityContract("x", frozenset({StackLayer.REASONING}), min_reliability=1.2).validate()


def test_provider_profiles_are_registered():
    lab = ProviderIndependenceLab(providers=(provider("a", "m-a"), provider("b", "m-b")))
    assert len(lab.providers()) == 2


def test_duplicate_provider_rejected():
    lab = ProviderIndependenceLab()
    lab.register(provider("a", "m-a"))
    with pytest.raises(ValueError):
        lab.register(provider("a", "m-b"))


def test_assessment_finds_multiple_compatible_providers():
    lab = ProviderIndependenceLab(providers=(provider("a", "m-a"), provider("b", "m-b"), provider("c", "m-c", reliability=.4)))
    result = lab.assess(contract())
    assert result.independent
    assert result.alternative_count == 2
    assert {(x.provider_id, x.model_id) for x in result.compatible} == {("a", "m-a"), ("b", "m-b")}


def test_assessment_records_incompatibility_reasons():
    lab = ProviderIndependenceLab(providers=(provider("a", "m-a", context=1024),))
    result = lab.assess(contract())
    assert not result.independent
    assert result.incompatible[0].reasons == ("context below minimum",)


def test_disabled_provider_is_incompatible():
    lab = ProviderIndependenceLab(providers=(provider("a", "m-a", enabled=False), provider("b", "m-b")))
    result = lab.assess(contract())
    assert result.compatible[0].provider_id == "b"
    assert result.incompatible[0].provider_id == "a"


def test_fallback_requires_compatible_alternatives():
    lab = ProviderIndependenceLab(providers=(provider("a", "m-a"), provider("b", "m-b")))
    policy = ProviderFallbackPolicy("PROV-POL-000001", ("a", "b"), minimum_alternatives=2)
    result = lab.validate_fallback(policy, contract())
    assert result.alternative_count == 2


def test_fallback_rejects_missing_alternative():
    lab = ProviderIndependenceLab(providers=(provider("a", "m-a"),))
    policy = ProviderFallbackPolicy("PROV-POL-000001", ("a", "missing"), minimum_alternatives=2)
    with pytest.raises(ValueError):
        lab.validate_fallback(policy, contract())


def test_fallback_order_is_not_modified():
    lab = ProviderIndependenceLab(providers=(provider("a", "m-a"), provider("b", "m-b")))
    policy = ProviderFallbackPolicy("PROV-POL-000001", ("b", "a"), minimum_alternatives=2)
    lab.validate_fallback(policy, contract())
    assert policy.ordered_provider_ids == ("b", "a")


def test_migration_target_must_be_compatible():
    lab = ProviderIndependenceLab(providers=(provider("a", "m-a"), provider("b", "m-b", context=1024)))
    plan = ProviderMigrationPlan("PROV-MIG-000001", "contract-reasoning", "a", "b", "m-a", "m-b", ("validate", "benchmark", "approve"))
    with pytest.raises(ValueError):
        lab.plan_migration(plan, contract())


def test_migration_is_reversible():
    lab = ProviderIndependenceLab(providers=(provider("a", "m-a"), provider("b", "m-b")))
    plan = ProviderMigrationPlan("PROV-MIG-000001", "contract-reasoning", "a", "b", "m-a", "m-b", ("validate", "benchmark", "approve"))
    assert lab.plan_migration(plan, contract()).reversible


def test_migration_rejects_same_target():
    with pytest.raises(ValueError):
        ProviderMigrationPlan("PROV-MIG-000001", "contract-reasoning", "a", "a", "m", "m", ("x",)).validate()


def test_digest_is_deterministic():
    lab = ProviderIndependenceLab(providers=(provider("b", "m-b"), provider("a", "m-a")))
    assert lab.digest(contract()) == lab.digest(contract())


def test_to_stack_request_is_provider_neutral():
    lab = ProviderIndependenceLab()
    request = lab.to_stack_request(contract(), "request-1")
    assert request.request_id == "request-1"
    assert request.layer == StackLayer.REASONING
    assert request.required_capabilities == frozenset({StackLayer.REASONING})


def test_compatibility_validation():
    item = ProviderCompatibility("a", "m", "contract", True, ())
    item.validate()


def test_assessment_validation():
    item = ProviderCompatibility("a", "m", "contract", True, ())
    ProviderIndependenceAssessment("contract", (item,), (), True, 1, ("ok",)).validate()


def test_no_execution_or_security_bypass_surface():
    assert not set(dir(ProviderIndependenceLab)).intersection(ensure_f21_no_execution_surface())


def test_provider_and_model_identity_are_preserved():
    lab = ProviderIndependenceLab(providers=(provider("provider-a", "model-a"), provider("provider-b", "model-b")))
    result = lab.assess(contract())
    assert {(x.provider_id, x.model_id) for x in result.compatible} == {("provider-a", "model-a"), ("provider-b", "model-b")}


def test_contract_requirements_are_declarative():
    assert IndependenceRequirement.FAILOVER in contract().requirements
