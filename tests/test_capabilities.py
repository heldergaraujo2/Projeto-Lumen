from app.core.capabilities import (
    Capability, CapabilityRegistry, CapabilityRisk, CapabilityStatus,
    build_baseline_registry,
)


def test_implemented_capability_requires_evidence():
    try:
        Capability("x", "X", "test", CapabilityStatus.IMPLEMENTED, CapabilityRisk.LOW)
    except ValueError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("IMPLEMENTED capability without evidence was accepted")


def test_registry_rejects_duplicate_ids():
    c = Capability("x", "X", "test", CapabilityStatus.PLANNED, CapabilityRisk.LOW)
    registry = CapabilityRegistry([c])
    try:
        registry.register(c)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate capability id was accepted")


def test_baseline_registry_distinguishes_statuses():
    registry = build_baseline_registry()
    assert len(registry) >= 9
    assert registry.get("conversation").status is CapabilityStatus.IMPLEMENTED
    assert registry.get("computer_control").status is CapabilityStatus.PARTIAL
    assert registry.get("research").status is CapabilityStatus.PLANNED


def test_registry_is_descriptive_only():
    registry = build_baseline_registry()
    assert not hasattr(registry, "execute")
    assert not hasattr(registry, "grant")
    assert not hasattr(registry, "authorize")


def test_high_risk_capabilities_are_explicit():
    ids = {c.id for c in build_baseline_registry().by_risk(CapabilityRisk.HIGH)}
    assert {"secure_filesystem", "secure_terminal", "computer_control", "vision", "evolution"} <= ids
