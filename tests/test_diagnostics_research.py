import pytest
from app.evolution.diagnostics import (
    ImprovementPlanner, ResearchEngine, ResearchEvidence, ResearchKind,
    ResearchQuery, SelfDiagnostics,
)
from app.evolution.models import Capability, CapabilityMeasurement, EvolutionRisk, Diagnostic


def cap(): return Capability("cap-1", "Grounding")


def meas(score): return CapabilityMeasurement("cap-1", score, "accuracy", 10, ("test",))


def test_healthy_diagnostic():
    d = SelfDiagnostics().diagnose(cap(), [meas(.9)])
    assert d.status == "HEALTHY"
    assert d.severity is EvolutionRisk.LOW


def test_degraded_diagnostic_and_severity():
    d = SelfDiagnostics().diagnose(cap(), [meas(.2)])
    assert d.status == "DEGRADED"
    assert d.severity is EvolutionRisk.HIGH


def test_no_data_is_explicit():
    d = SelfDiagnostics().diagnose(cap(), [])
    assert d.status == "NO_DATA"


def test_mismatched_measurement_rejected():
    with pytest.raises(ValueError):
        SelfDiagnostics().diagnose(cap(), [CapabilityMeasurement("other", .9, "x")])


def test_threshold_validation():
    with pytest.raises(ValueError):
        SelfDiagnostics().diagnose(cap(), [meas(.9)], threshold=2)


def test_research_evidence_validation():
    e = ResearchEvidence("E1", ResearchKind.PAPER, "paper://1", "supports approach")
    e.validate()
    with pytest.raises(ValueError):
        ResearchEvidence("E2", ResearchKind.PAPER, "", "x").validate()


def test_research_collection_uses_supplied_provider():
    q = ResearchQuery("Q1", "cap-1", "How can accuracy improve?", ("grounding",))
    engine = ResearchEngine()
    report = engine.collect(q, lambda _: [ResearchEvidence("E1", ResearchKind.DOCUMENTATION, "docs://x", "method")])
    assert len(report.evidence) == 1


def test_research_provider_cannot_change_query_contract():
    with pytest.raises(ValueError):
        ResearchEngine().collect(ResearchQuery("Q1", "cap-1", "x"), lambda _: [ResearchEvidence("", ResearchKind.PAPER, "s", "c")])


def test_opportunity_links_diagnostic_to_evidence():
    d = SelfDiagnostics().diagnose(cap(), [meas(.4)])
    q = ResearchQuery("Q1", "cap-1", "improve")
    report = ResearchEngine().collect(q, lambda _: [ResearchEvidence("E1", ResearchKind.PAPER, "paper://1", "method", .9)])
    ops = ResearchEngine().identify_opportunities(d, report)
    assert ops[0].evidence_ids == ("E1",)
    assert ops[0].confidence == .9


def test_healthy_capability_has_no_improvement_opportunity():
    d = SelfDiagnostics().diagnose(cap(), [meas(.9)])
    q = ResearchQuery("Q1", "cap-1", "improve")
    report = ResearchReport(q, (ResearchEvidence("E1", ResearchKind.PAPER, "p", "x"),))
    assert ResearchEngine().identify_opportunities(d, report) == ()


def test_planner_requires_degraded_diagnostic():
    d = SelfDiagnostics().diagnose(cap(), [meas(.9)])
    with pytest.raises(ValueError):
        ImprovementPlanner().create_plan(evolution_id="EVOLUTION-000001", diagnostic=d, baseline=meas(.9), objective="x")


def test_planner_preserves_research_sources():
    d = SelfDiagnostics().diagnose(cap(), [meas(.4)])
    q = ResearchQuery("Q1", "cap-1", "improve")
    report = ResearchReport(q, (ResearchEvidence("E1", ResearchKind.PAPER, "paper://1", "x"),))
    p = ImprovementPlanner().create_plan(evolution_id="EVOLUTION-000001", diagnostic=d, baseline=meas(.4), objective="reach target", research=report)
    assert p.sources == ("paper://1",)
    assert p.risk is EvolutionRisk.HIGH


def test_research_and_diagnostics_have_no_execution_surface():
    assert not hasattr(ResearchEngine(), "execute")
    assert not hasattr(SelfDiagnostics(), "run_driver")


def test_research_report_rejects_wrong_capability():
    d = SelfDiagnostics().diagnose(cap(), [meas(.4)])
    q = ResearchQuery("Q1", "other", "improve")
    report = ResearchReport(q, ())
    with pytest.raises(ValueError):
        ResearchEngine().identify_opportunities(d, report)
