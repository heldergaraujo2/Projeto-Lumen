import json

import pytest

from app.experience import (
    ExperienceEvent, ExperienceOutcome, ExperienceStore, ExperienceTrace,
    WorkflowIntelligence,
)
from app.workflows import WorkflowOutcome


def trace(experience_id, path, value, fingerprint):
    return ExperienceTrace(
        experience_id=experience_id,
        goal="abrir asset no Unreal",
        events=(
            ExperienceEvent(0, "open_asset", (("path", path),), fingerprint, True, ExperienceOutcome.SUCCESS),
            ExperienceEvent(1, "select_value", (("value", value),), fingerprint + "2", True, ExperienceOutcome.SUCCESS),
        ),
        outcome=ExperienceOutcome.SUCCESS,
        context=(("application", "UnrealEditor"),),
    )


def test_observe_and_understand_are_metadata_only(tmp_path):
    store = ExperienceStore(tmp_path / "experience.json")
    intelligence = WorkflowIntelligence(experience_store=store)
    t = trace("e1", "/Game/A", "A", "fp1")
    assert intelligence.observe(t) == t
    understood = intelligence.understand(t)
    assert understood["action_sequence"] == ("open_asset", "select_value")
    assert not hasattr(intelligence, "driver")


def test_record_persists_and_reloads(tmp_path):
    path = tmp_path / "experience.json"
    store = ExperienceStore(path)
    store.record(trace("e1", "/Game/A", "A", "fp1"))
    reloaded = ExperienceStore(path)
    assert reloaded.get("e1").goal == "abrir asset no Unreal"
    assert reloaded.get("e1").events[0].action == "open_asset"


def test_secrets_are_redacted_before_persistence(tmp_path):
    path = tmp_path / "experience.json"
    store = ExperienceStore(path)
    t = trace("e1", "/Game/A", "A", "fp1")
    t = ExperienceTrace(
        t.experience_id, t.goal, (
            ExperienceEvent(0, "open_asset", (("token", "Authorization: Bearer SECRET"),), "fp", True, ExperienceOutcome.SUCCESS),
        ), ExperienceOutcome.SUCCESS,
    )
    store.record(t)
    raw = path.read_text()
    assert "SECRET" not in raw
    assert "***" in raw


def test_generalize_only_verified_successes(tmp_path):
    intelligence = WorkflowIntelligence(experience_store=ExperienceStore(tmp_path / "x.json"))
    first = trace("e1", "/Game/A", "A", "fp1")
    second = trace("e2", "/Game/B", "B", "fp2")
    result = intelligence.generalize(workflow_id="asset.open", name="Open asset", traces=(first, second))
    assert result.generalized_variables == ("step0_path", "step1_value")
    assert dict(result.workflow.steps[0].parameters)["path"] == "$step0_path"


def test_generalization_rejects_failed_or_unverified(tmp_path):
    intelligence = WorkflowIntelligence(experience_store=ExperienceStore(tmp_path / "x.json"))
    bad = ExperienceTrace(
        "bad", "goal",
        (ExperienceEvent(0, "open", (), "fp", False, ExperienceOutcome.FAILURE),),
        ExperienceOutcome.FAILURE,
    )
    with pytest.raises(ValueError):
        intelligence.generalize(workflow_id="x", name="x", traces=(bad,))


def test_generalization_rejects_different_sequences(tmp_path):
    intelligence = WorkflowIntelligence(experience_store=ExperienceStore(tmp_path / "x.json"))
    a = trace("a", "/A", "A", "1")
    b = ExperienceTrace(
        "b", a.goal,
        (
            ExperienceEvent(0, "open_asset", (("path", "/B"),), "2", True, ExperienceOutcome.SUCCESS),
            ExperienceEvent(1, "different", (("value", "B"),), "3", True, ExperienceOutcome.SUCCESS),
        ),
        ExperienceOutcome.SUCCESS,
    )
    with pytest.raises(ValueError):
        intelligence.generalize(workflow_id="x", name="x", traces=(a, b))


def test_reuse_requires_verified_outcome(tmp_path):
    intelligence = WorkflowIntelligence(experience_store=ExperienceStore(tmp_path / "x.json"))
    workflow = intelligence.generalize(workflow_id="asset.open", name="Open", traces=(trace("e1", "/A", "A", "fp"),)).workflow
    assert intelligence.reuse("abrir asset Unreal") == ()
    intelligence.record_verification(workflow_id=workflow.workflow_id, success=True, observation_fingerprint="ok")
    assert intelligence.reuse("abrir asset Unreal")[0].workflow_id == "asset.open"


def test_adapt_requires_exact_bindings(tmp_path):
    intelligence = WorkflowIntelligence(experience_store=ExperienceStore(tmp_path / "x.json"))
    workflow = intelligence.generalize(
        workflow_id="asset.open", name="Open", traces=(trace("e1", "/A", "A", "fp"), trace("e2", "/B", "B", "fp2"))
    ).workflow
    with pytest.raises(ValueError):
        intelligence.adapt(workflow.workflow_id, {"step0_path": "/C"})
    adapted = intelligence.adapt(workflow.workflow_id, {"step0_path": "/C", "step1_value": "C"})
    assert dict(adapted.steps[0].parameters)["path"] == "/C"


def test_evidence_rejects_unverified_success(tmp_path):
    intelligence = WorkflowIntelligence(experience_store=ExperienceStore(tmp_path / "x.json"))
    with pytest.raises(ValueError):
        intelligence.verify(__import__("app.workflows", fromlist=["WorkflowEvidence"]).WorkflowEvidence(
            "missing", WorkflowOutcome.SUCCESS, "failed", "fp"
        ))


def test_store_is_bounded(tmp_path):
    store = ExperienceStore(tmp_path / "x.json", max_items=2)
    for i in range(3):
        store.record(trace(f"e{i}", f"/A{i}", str(i), f"fp{i}"))
    assert store.get("e0") is None
    assert store.get("e1") is not None
    assert store.get("e2") is not None
