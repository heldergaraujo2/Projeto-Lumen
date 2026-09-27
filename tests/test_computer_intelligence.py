from app.computer import (
    ActionPlanner, ComputerIntelligence, ComputerObservation, ComputerState,
    ExecutionMechanism, IntelligenceRecovery, IntelligenceVerifier,
    PerceptionPipeline, TargetingEngine, VisionObservationPerception,
)
from app.computer.actions import ExecutionResolver
from app.computer_control.api import CCTarget, ScreenRegion
from app.computer_control.grounding import GroundedTarget, GroundingSource
from app.computer_control.vision import VisionElement, VisionObservation


def target(label, source=GroundingSource.VISION, confidence=0.95, x=100, y=100):
    return GroundedTarget(label, source, confidence, x, y, 80, 30)


def observation(*elements, region=None):
    return ComputerObservation(
        width=800, height=600, elements=tuple(elements),
        active_window=CCTarget(window_title_pattern="Unreal"),
        allowed_region=region,
    )


def lumen(obs):
    return ComputerIntelligence(
        perception=PerceptionPipeline(lambda: obs),
        targeting=TargetingEngine(min_confidence=0.80),
        actions=ActionPlanner(), execution=ExecutionResolver(),
        verification=IntelligenceVerifier(),
        recovery_engine=IntelligenceRecovery(max_attempts=2),
    )


def test_observation_is_structured_and_fingerprinted():
    obs = observation(target("Compile"))
    assert obs.state is ComputerState.OBSERVED
    assert len(obs.fingerprint) == 64


def test_state_fingerprint_changes_when_structured_ui_changes():
    assert observation(target("Compile")).fingerprint != observation(target("Play")).fingerprint


def test_vision_adapter_converts_elements():
    raw = VisionObservation(800, 600, (VisionElement("Compile", 0.95, 100, 100, 80, 30, "Compile"),))
    obs = VisionObservationPerception(raw).observe()
    assert obs.elements[0].label == "Compile"
    assert obs.elements[0].source is GroundingSource.VISION


def test_targeting_prefers_structured_source_over_vision():
    obs = observation(target("Compile", GroundingSource.VISION))
    native = target("Compile", GroundingSource.NATIVE, 0.81, 300, 300)
    result = TargetingEngine().resolve(obs, "Compile", candidates=(native,))
    assert result.target is native
    assert result.mechanism is ExecutionMechanism.NATIVE


def test_targeting_rejects_outside_region():
    obs = observation(target("Compile", x=250, y=250), region=ScreenRegion(0, 0, 200, 200))
    result = TargetingEngine().resolve(obs, "Compile")
    assert result.target is None
    assert result.reason == "target_outside_scope"


def test_unknown_target_is_not_planned():
    obs = observation(target("Compile"))
    result = lumen(obs).plan_click(obs, "Play")
    assert not result.ok
    assert result.plan is None


def test_click_plan_is_driver_free_and_resolvable():
    obs = observation(target("Compile"))
    result = lumen(obs).plan_click(obs, "Compile", rationale="build")
    requests = lumen(obs).resolve_plan_requests(result.plan, mechanism=ExecutionMechanism.COMPUTER_CONTROL)
    assert result.ok and requests[0].target.label == "Compile"


def test_low_confidence_is_not_grounded():
    obs = observation(target("Compile", confidence=0.50))
    result = lumen(obs).plan_click(obs, "Compile")
    assert not result.ok


def test_verification_detects_target():
    obs = observation(target("Compile"))
    assert lumen(obs).verify_target(obs, "Compile").status.value == "verified"


def test_verification_detects_state_change():
    before, after = observation(target("Compile")), observation(target("Play"))
    assert lumen(before).verify_state_change(before, after).status.value == "verified"


def test_recovery_is_bounded():
    agent = lumen(observation(target("Compile")))
    assert agent.recovery(failure_reason="target_not_found", attempt=0).attempt == 0
    assert agent.recovery(failure_reason="target_not_found", attempt=2).action.value == "abort"


def test_action_planner_rejects_invalid_key_combo():
    try:
        ActionPlanner().key_combo()
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_native_resolution_does_not_execute():
    obs = observation(target("Compile", GroundingSource.NATIVE, 0.99))
    result = lumen(obs).plan_click(obs, "Compile")
    request = lumen(obs).resolve_plan_requests(result.plan, mechanism=ExecutionMechanism.NATIVE)[0]
    assert request.action.value == "mouse_click"
