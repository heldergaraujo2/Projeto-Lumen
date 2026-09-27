import pytest

from app.computer.models import ExecutionMechanism
from app.computer_control.api import CCTarget
from app.computer_control.verification import VerificationStatus
from app.unreal.agent import UnrealAgent
from app.unreal.models import UnrealOperation, UnrealPlan, UnrealProject
from app.unreal.shortcuts import OPEN_ASSET, OPEN_LEVEL, PLAY_IN_EDITOR, SAVE, SAVE_ALL


def project():
    return UnrealProject(
        name="AgeOfAether",
        root="C:/Games/AgeOfAether",
        engine_version="5.8",
        editor_window=CCTarget(app_name="UnrealEditor"),
    )


def test_project_requires_identity():
    with pytest.raises(ValueError):
        UnrealProject("", "C:/Games/A").validate()


def test_open_asset_is_explicit_and_verifiable():
    action = UnrealAgent().open_asset("/Game/Blueprints/BP_Player")
    assert action.operation is UnrealOperation.OPEN_ASSET
    assert action.keys == OPEN_ASSET
    assert action.expected is not None
    assert action.expected.value == "/Game/Blueprints/BP_Player"


def test_open_level_is_explicit_and_verifiable():
    action = UnrealAgent().open_level("/Game/Maps/Main")
    assert action.operation is UnrealOperation.OPEN_LEVEL
    assert action.keys == OPEN_LEVEL


def test_save_and_play_plan():
    plan = UnrealAgent().save_and_play(project=project())
    assert len(plan.actions) == 2
    assert plan.actions[0].operation is UnrealOperation.SAVE
    assert plan.actions[1].operation is UnrealOperation.PLAY


def test_goal_planner_is_fail_closed_for_ambiguous_free_text():
    with pytest.raises(ValueError, match="unsupported Unreal goal"):
        UnrealAgent().plan(project=project(), goal="melhore meu jogo")


def test_goal_planner_accepts_known_safe_goal():
    plan = UnrealAgent().plan(project=project(), goal="salvar projeto")
    assert plan.actions[0].operation is UnrealOperation.SAVE


def test_to_action_plan_does_not_execute():
    plan = UnrealAgent().save_and_play(project=project())
    action_plan = UnrealAgent().to_action_plan(plan=plan, observation_fingerprint="abc")
    assert len(action_plan.intents) == 2
    assert action_plan.observation_fingerprint == "abc"


def test_open_asset_expands_to_search_type_confirm():
    plan = UnrealPlan(
        project=project(),
        goal="open asset",
        actions=(UnrealAgent().open_asset("/Game/BP_Player"),),
    )
    action_plan = UnrealAgent().to_action_plan(plan=plan, observation_fingerprint="abc")
    assert [i.action for i in action_plan.intents] == ["key_combo", "key_type", "key_press"]
    assert action_plan.intents[1].parameters["text"] == "/Game/BP_Player"


def test_resolve_requests_remains_non_executing():
    plan = UnrealAgent().save_and_play(project=project())
    action_plan = UnrealAgent().to_action_plan(plan=plan, observation_fingerprint="abc")
    requests = UnrealAgent().resolve_requests(action_plan, mechanism=ExecutionMechanism.COMPUTER_CONTROL)
    assert len(requests) == 2
    assert all(r.keys for r in requests)


def test_required_target_is_project_editor_window():
    target = UnrealAgent.required_target(project())
    assert target.app_name == "UnrealEditor"


def test_verification_contract_accepts_expected_asset():
    action = UnrealAgent().open_asset("/Game/BP_Player")
    assert action.expected is not None
    action.expected.validate()


def test_unreal_plan_validation_rejects_empty_actions():
    with pytest.raises(ValueError):
        UnrealPlan(project(), "x", ()).validate()


def test_documented_shortcuts_are_present():
    assert OPEN_ASSET == ("CTRL", "P")
    assert OPEN_LEVEL == ("CTRL", "O")
    assert SAVE == ("CTRL", "S")
    assert SAVE_ALL == ("CTRL", "SHIFT", "S")
    assert PLAY_IN_EDITOR == ("ALT", "P")


def test_verification_status_is_fail_closed():
    assert VerificationStatus.INCONCLUSIVE.value == "inconclusive"
