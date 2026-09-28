import pytest

from app.evolution.models import (
    BenchmarkResult, Capability, CapabilityMeasurement, Candidate, EvolutionRisk,
    EvolutionState, Hypothesis,
)
from app.evolution.diagnostics import Diagnostic, ResearchEvidence, ResearchKind, ResearchQuery, ResearchReport
from app.evolution.orchestrator import EvolutionRuntimeOrchestrator
from app.evolution.promotion import BenchmarkSuite, BuildEvidence


def setup_orchestrator():
    o = EvolutionRuntimeOrchestrator()
    o.evolution.register_capability(Capability("cap-1", "Reasoning"))
    o.evolution.baseline(CapabilityMeasurement("cap-1", .80, "quality", 10))
    return o


def test_f24_full_bounded_lifecycle_without_execution():
    o = setup_orchestrator()
    c = o.detect(capability_id="cap-1", problem="quality below target", risk=EvolutionRisk.LOW)
    assert c.state is EvolutionState.PROPOSED
    d = Diagnostic("cap-1", "DEGRADED", ("below target",), (CapabilityMeasurement("cap-1", .70, "quality", 10),), EvolutionRisk.LOW)
    c = o.investigate(c.evolution_id, d)
    report = ResearchReport(
        ResearchQuery("RQ-1", "cap-1", "how to improve quality"),
        (ResearchEvidence("E-1", ResearchKind.DOCUMENTATION, "fixture", "evidence"),),
    )
    c = o.research(c.evolution_id, report)
    c = o.hypothesize(c.evolution_id, Hypothesis(c.evolution_id, "X improves quality", "evidence", "quality", .10))
    c = o.request_experiment(c.evolution_id, experiment_id="EXP-1", workspace="/tmp/lumen-evolution")
    c = o.submit_build_request(c.evolution_id)
    candidate = Candidate("C-F24-1", c.evolution_id, "1.0")
    c = o.record_candidate(c.evolution_id, candidate)
    c = o.record_build(c.evolution_id, BuildEvidence("C-F24-1", "BUILD-1", True, "1.0", ("artifact",), ("tests",)))
    c = o.benchmark(c.evolution_id, BenchmarkSuite("C-F24-1", (BenchmarkResult("C-F24-1", "quality", .70, .85, 10),)))
    c = o.security_review(c.evolution_id)
    assert c.state is EvolutionState.PROMOTION_PENDING
    c = o.request_approval(c.evolution_id)
    c = o.approve(c.evolution_id, reason="explicit test approval")
    assert c.state is EvolutionState.APPROVED
    c = o.promote(c.evolution_id)
    assert c.state is EvolutionState.PROMOTED
    c = o.monitor(c.evolution_id)
    assert c.state is EvolutionState.MONITORED
    assert len(o.digest(c.evolution_id)) == 64


def test_f24_rejects_invalid_transition():
    o = setup_orchestrator()
    c = o.detect(capability_id="cap-1", problem="problem")
    with pytest.raises(ValueError):
        o.promote(c.evolution_id)


def test_f24_rejects_cross_evolution_candidate():
    o = setup_orchestrator()
    c = o.detect(capability_id="cap-1", problem="problem")
    other = Candidate("C-F24-X", "EVOLUTION-999999", "1.0")
    with pytest.raises(ValueError):
        o.record_candidate(c.evolution_id, other)


def test_f24_failed_build_is_terminal_rejection():
    o = setup_orchestrator()
    c = o.detect(capability_id="cap-1", problem="problem")
    d = Diagnostic("cap-1", "DEGRADED", ("x",), (), EvolutionRisk.LOW)
    c = o.investigate(c.evolution_id, d)
    r = ResearchReport(ResearchQuery("RQ-2", "cap-1", "q"), (ResearchEvidence("E-2", ResearchKind.OBSERVATION, "fixture", "x"),))
    c = o.research(c.evolution_id, r)
    c = o.hypothesize(c.evolution_id, Hypothesis(c.evolution_id, "h", "r", "quality", .1))
    c = o.request_experiment(c.evolution_id, experiment_id="EXP-2", workspace="/tmp/x")
    c = o.submit_build_request(c.evolution_id)
    c = o.record_candidate(c.evolution_id, Candidate("C-F24-X2", c.evolution_id, "1.0"))
    c = o.record_build(c.evolution_id, BuildEvidence("C-F24-X2", "B2", False, "1.0"))
    assert c.state is EvolutionState.REJECTED


def test_f24_requires_human_approval():
    o = setup_orchestrator()
    assert not hasattr(o, "execute")
    assert not hasattr(o, "deploy")
    assert not hasattr(o, "run_driver")
    assert not hasattr(o, "run_provider")
