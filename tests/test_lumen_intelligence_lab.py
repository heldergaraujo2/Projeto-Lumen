import dataclasses
import pytest

from app.evolution.diagnostics import ResearchEvidence, ResearchKind, ResearchQuery, ResearchReport
from app.evolution.intelligence_stack import StackEvidence
from app.evolution.intelligence_lab import (
    IntelligenceAssessment, IntelligenceBaseline, IntelligenceCapability,
    IntelligenceFinding, IntelligenceHypothesis, IntelligenceOpportunity,
    IntelligenceResearch, IntelligenceTrack, LumenIntelligenceLab,
)
from app.evolution.models import CapabilityMeasurement, EvolutionRisk


def make_lab():
    lab = LumenIntelligenceLab()
    lab.register_capability(IntelligenceCapability("reasoning", "Reasoning", IntelligenceTrack.REASONING))
    lab.record_baseline(IntelligenceBaseline("reasoning", CapabilityMeasurement("reasoning", .70, "accuracy", 20, ("baseline://1",)), "fixture", "2026-09-27T00:00:00Z"))
    return lab


def make_research(lab):
    query = ResearchQuery("q-1", "reasoning", "How can reasoning improve?", ("reasoning",))
    evidence = ResearchEvidence("paper-1", ResearchKind.PAPER, "paper://1", "method improves reasoning", .9)
    research = IntelligenceResearch("research-1", "reasoning", query, ResearchReport(query, (evidence,)))
    lab.record_research(research)
    return research


def test_capability_and_baseline_are_registered():
    lab = make_lab()
    assert lab.summary()["capabilities"] == 1
    assert lab.baseline("reasoning").measurement.score == .70


def test_baseline_requires_registered_capability():
    lab = LumenIntelligenceLab()
    with pytest.raises(KeyError):
        lab.record_baseline(IntelligenceBaseline("missing", CapabilityMeasurement("missing", .5, "accuracy"), "fixture", "now"))


def test_research_requires_matching_query_and_capability():
    lab = make_lab()
    query = ResearchQuery("q-1", "reasoning", "question")
    report = ResearchReport(ResearchQuery("q-other", "reasoning", "question"), (ResearchEvidence("e", ResearchKind.PAPER, "paper://e", "claim"),))
    with pytest.raises(ValueError):
        lab.record_research(IntelligenceResearch("r", "reasoning", query, report))


def test_research_evidence_enters_ledger():
    lab = make_lab()
    make_research(lab)
    assert lab.evidence.size() == 2
    assert lab.evidence.get("RESEARCH:research-1:paper-1").claim == "method improves reasoning"


def test_hypothesis_requires_capability():
    lab = make_lab()
    hypothesis = IntelligenceHypothesis("INT-HYP-000001", "EVOLUTION-000001", "missing", "improve", "accuracy", .1)
    with pytest.raises(KeyError):
        lab.propose_hypothesis(hypothesis)


def test_stack_evidence_is_validated_and_recorded():
    lab = make_lab()
    lab.record_stack_evidence(StackEvidence("req-1", "local", "model", "accuracy", .8, 10, "fixture"))
    assert lab.evidence.size() == 2


def test_assessment_requires_existing_evidence_and_records_finding():
    lab = make_lab()
    assessment = lab.assess("reasoning", candidate_score=.82, finding_id="INT-FIND-000001", evidence_ids=("BASELINE:reasoning:2026-09-27T00:00:00Z",), conclusion="improvement observed", confidence=.9)
    assert isinstance(assessment, IntelligenceAssessment)
    assert assessment.findings[0].delta == pytest.approx(.12)
    assert not assessment.regression_detected


def test_assessment_rejects_unknown_evidence():
    lab = make_lab()
    with pytest.raises(KeyError):
        lab.assess("reasoning", candidate_score=.82, finding_id="INT-FIND-000002", evidence_ids=("missing",), conclusion="x", confidence=.5)


def test_opportunity_requires_research():
    lab = make_lab()
    opportunity = IntelligenceOpportunity("INT-OPP-000001", "reasoning", "reasoning gap", ("missing-research",), .8, EvolutionRisk.MEDIUM, "research needed")
    with pytest.raises(KeyError):
        lab.create_opportunity(opportunity)
    make_research(lab)
    lab.create_opportunity(dataclasses.replace(opportunity, research_ids=("research-1",)))
    assert lab.summary()["opportunities"] == 1


def test_digest_is_deterministic():
    lab = make_lab()
    make_research(lab)
    assert lab.digest("reasoning") == lab.digest("reasoning")
    assert len(lab.digest("reasoning")) == 64


def test_workspace_is_isolated():
    lab = make_lab()
    ws = lab.workspace(evolution_id="EVOLUTION-000001", workspace_id="ws-int")
    assert ws.root == "evolution-lab/ws-int"
    assert not ws.stable_runtime


def test_finding_validation_blocks_bad_confidence():
    with pytest.raises(ValueError):
        IntelligenceFinding("INT-FIND-1", "reasoning", ("e",), .5, .6, 1.5, "x").validate()


def test_hypothesis_validation():
    IntelligenceHypothesis("INT-HYP-000001", "EVOLUTION-000001", "reasoning", "change approach", "accuracy", .05).validate()


def test_ledger_rejects_duplicate_and_unvalidated_evidence():
    lab = make_lab()
    item = ResearchEvidence("e", ResearchKind.PAPER, "paper://e", "claim")
    lab.evidence.record("evidence-1", item)
    with pytest.raises(ValueError):
        lab.evidence.record("evidence-1", item)
    with pytest.raises(ValueError):
        lab.evidence.record("bad", object())


def test_ledger_is_bounded():
    from app.evolution.intelligence_lab import IntelligenceEvidenceLedger
    ledger = IntelligenceEvidenceLedger(history_limit=2)
    for i in range(3):
        ledger.record(str(i), ResearchEvidence(str(i), ResearchKind.PAPER, "source", "claim"))
    assert ledger.ids() == ("1", "2")
    with pytest.raises(KeyError):
        ledger.get("0")


def test_duplicate_capability_and_research_are_rejected():
    lab = make_lab()
    with pytest.raises(ValueError):
        lab.register_capability(IntelligenceCapability("reasoning", "Other", IntelligenceTrack.REASONING))
    make_research(lab)
    query = ResearchQuery("q-1", "reasoning", "How can reasoning improve?")
    report = ResearchReport(query, (ResearchEvidence("other", ResearchKind.PAPER, "source", "claim"),))
    with pytest.raises(ValueError):
        lab.record_research(IntelligenceResearch("research-1", "reasoning", query, report))


def test_regression_is_explicitly_reported():
    lab = make_lab()
    assessment = lab.assess("reasoning", candidate_score=.50, finding_id="INT-FIND-000003", evidence_ids=("BASELINE:reasoning:2026-09-27T00:00:00Z",), conclusion="degradation observed", confidence=.9)
    assert assessment.regression_detected


def test_summary_counts_research_state():
    lab = make_lab()
    make_research(lab)
    lab.propose_hypothesis(IntelligenceHypothesis("INT-HYP-000001", "EVOLUTION-000001", "reasoning", "improve", "accuracy", .1))
    assert lab.summary() == {"capabilities": 1, "baselines": 1, "research": 1, "hypotheses": 1, "findings": 0, "opportunities": 0, "evidence": 2}


def test_no_execution_or_security_bypass_surface():
    names = set(dir(LumenIntelligenceLab))
    forbidden = {"execute", "run_model", "train", "infer", "download_model", "deploy", "grant_permission", "change_policy", "disable_audit", "widen_scope", "run_browser", "run_tool", "execute_driver"}
    assert not names.intersection(forbidden)