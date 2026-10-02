import pytest

from app.evolution.autonomous_progress import AutonomousProgressController


def test_exhausted_progress_budget_does_not_fallback_to_unbounded_research(tmp_path):
    controller = AutonomousProgressController(
        tmp_path / "progress.json",
        "mission",
        repeat_limit=1,
    )
    for action in ("list_toolsets", "describe_toolset", "observe_unreal", "unreal_call", "research", "evolve_code"):
        controller.record(action=action, fingerprint=f"{action}-done", success=False)

    with pytest.raises(RuntimeError, match="progress exhausted"):
        controller.recommend(
            ("list_toolsets", "describe_toolset", "observe_unreal", "unreal_call", "research", "evolve_code"),
            context={"can_observe": True, "can_research": True, "can_evolve_code": True, "can_unreal_call": True},
        )
