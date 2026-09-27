import pytest

from app.workflows import (
    WorkflowDefinition, WorkflowLearner, WorkflowMatcher, WorkflowOutcome,
    WorkflowRegistry, WorkflowRisk, WorkflowStep,
)
from app.workflows.models import WorkflowEvidence


def workflow():
    return WorkflowDefinition(
        workflow_id="unreal.save.play",
        name="Save and Play",
        goal="salvar e iniciar play no Unreal",
        steps=(
            WorkflowStep("window_focus", expectation_kind="window_focused", expectation_value="UnrealEditor"),
            WorkflowStep("key_press", parameters=(("keys", ("CTRL", "S")),), expectation_kind="state_changed"),
            WorkflowStep("key_press", parameters=(("keys", ("ALT", "P")),), expectation_kind="state_changed"),
        ),
    )


def test_definition_has_deterministic_fingerprint():
    assert workflow().fingerprint == workflow().fingerprint


def test_registry_records_evidence_without_execution():
    registry = WorkflowRegistry()
    registry.register(workflow())
    registry.record(WorkflowEvidence("unreal.save.play", WorkflowOutcome.SUCCESS, "verified", "abc"))
    assert registry.reusable("unreal.save.play")
    assert registry.stats("unreal.save.play").success_rate == 1.0


def test_failed_latest_outcome_blocks_reuse():
    registry = WorkflowRegistry()
    registry.register(workflow())
    registry.record(WorkflowEvidence("unreal.save.play", WorkflowOutcome.SUCCESS, "verified", "a"))
    registry.record(WorkflowEvidence("unreal.save.play", WorkflowOutcome.FAILURE, "failed", "b"))
    assert not registry.reusable("unreal.save.play")


def test_matcher_is_deterministic_and_only_returns_reusable():
    registry = WorkflowRegistry()
    registry.register(workflow())
    registry.record(WorkflowEvidence("unreal.save.play", WorkflowOutcome.SUCCESS, "verified", "a"))
    matches = WorkflowMatcher().match("salvar play Unreal", registry=registry)
    assert matches[0].workflow_id == "unreal.save.play"


def test_matcher_rejects_empty_goal():
    with pytest.raises(ValueError):
        WorkflowMatcher().match("", registry=WorkflowRegistry())


def test_learning_requires_observed_steps():
    with pytest.raises(ValueError):
        WorkflowLearner().learn(workflow_id="x", name="x", goal="x", steps=())


def test_learning_creates_non_executing_workflow():
    proposal = WorkflowLearner().learn(
        workflow_id="x", name="Salvar", goal="salvar projeto",
        steps=({"action": "key_press", "parameters": {"keys": ("CTRL", "S")}, "expectation_kind": "state_changed"},),
    )
    assert proposal.workflow.steps[0].action == "key_press"
    assert proposal.workflow.requires_human_approval is False


def test_high_risk_workflow_requires_human_approval():
    proposal = WorkflowLearner().learn(
        workflow_id="danger", name="Sensitive", goal="sensitive",
        steps=({"action": "window_close", "risk": "high"},),
    )
    assert proposal.requires_human_approval


def test_adaptation_only_uses_declared_variables():
    learner = WorkflowLearner()
    learner.registry.register(
        WorkflowDefinition(
            "x", "Open asset", "abrir asset",
            (WorkflowStep("key_type", parameters=(("text", "$asset"),)),),
            variables=("asset",),
        )
    )
    adapted = learner.adapt("x", bindings={"asset": "/Game/BP"})
    assert dict(adapted.steps[0].parameters)["text"] == "/Game/BP"
    with pytest.raises(ValueError):
        learner.adapt("x", bindings={"other": "x"})


def test_adaptation_never_adds_or_removes_steps():
    learner = WorkflowLearner()
    original = workflow()
    learner.registry.register(original)
    adapted = learner.adapt(original.workflow_id, bindings={})
    assert len(adapted.steps) == len(original.steps)
    assert adapted.version == original.version + 1


def test_invalid_expectation_is_rejected():
    with pytest.raises(ValueError):
        WorkflowStep("key_press", expectation_kind="execute_anything").validate()


def test_evidence_rejects_missing_observation_fingerprint():
    with pytest.raises(ValueError):
        WorkflowEvidence("x", WorkflowOutcome.SUCCESS, "verified", "").validate()


def test_version_cannot_move_backwards():
    registry = WorkflowRegistry()
    registry.register(workflow())
    older = WorkflowDefinition("unreal.save.play", "old", "salvar", (WorkflowStep("key_press"),), version=0)
    with pytest.raises(ValueError):
        registry.register(older)


def test_disabled_workflow_is_never_reusable():
    registry = WorkflowRegistry()
    disabled = WorkflowDefinition(
        "disabled", "Disabled", "salvar",
        (WorkflowStep("key_press"),), enabled=False,
    )
    registry.register(disabled)
    registry.record(WorkflowEvidence("disabled", WorkflowOutcome.SUCCESS, "verified", "x"))
    assert not registry.reusable("disabled")


def test_workflow_fingerprint_changes_when_version_changes():
    first = workflow()
    second = WorkflowDefinition(first.workflow_id, first.name, first.goal, first.steps, version=2)
    assert first.fingerprint != second.fingerprint


def test_learning_can_capture_unreal_plan_without_execution():
    from app.computer_control.api import CCTarget
    from app.unreal.agent import UnrealAgent
    from app.unreal.models import UnrealProject

    project = UnrealProject(name="AgeOfAether", root="C:/Games/AgeOfAether", editor_window=CCTarget(app_name="UnrealEditor"))
    plan = UnrealAgent().save_and_play(project=project)
    proposal = WorkflowLearner().learn_unreal_plan(
        plan=plan,
        workflow_id="unreal.save.play",
        name="Unreal Save and Play",
    )
    assert proposal.workflow.source == "unreal_agent"
    assert len(proposal.workflow.steps) == len(plan.actions)
    assert proposal.workflow.steps[0].action == "save"


def test_success_evidence_requires_verified_status():
    with pytest.raises(ValueError):
        WorkflowEvidence("x", WorkflowOutcome.SUCCESS, "failed", "abc").validate()


def test_failed_evidence_cannot_be_verified():
    with pytest.raises(ValueError):
        WorkflowEvidence("x", WorkflowOutcome.FAILURE, "verified", "abc").validate()
