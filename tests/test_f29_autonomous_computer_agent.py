from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.computer_control.actions import CCActionRequest
from app.computer_control.api import CCActionType, ScreenshotInfo
from app.computer_control.autonomous_agent import (
    ComputerAgentLimits, ComputerAgentState, ComputerPlan, VisionComputerAgent,
)
from app.computer_control.service import CCExecutionResult
from app.computer_control.verification import VerificationExpectation, VerificationResult, VerificationStatus
from app.computer_control.vision import VisionElement, VisionObservation, VisionRequest
from app.computer_control.vision_grounding import VisionGroundingPipeline
from app.computer_control.scopes import CCScope


@dataclass
class FakeVisionProvider:
    observations: list[VisionObservation]
    def observe(self, request):
        return self.observations.pop(0)


class FakeCC:
    def __init__(self, result):
        self.result = result
        self.calls = 0
    def execute(self, **kwargs):
        self.calls += 1
        return self.result


class Planner:
    def plan(self, *, goal, observation, previous_reason=""):
        return ComputerPlan(
            CCActionRequest(CCActionType.MOUSE_CLICK, target=observation.target),
            VerificationExpectation("target_absent", "Compile"),
            "Compile",
        )


class Verifier:
    def verify(self, *, expectation, observation):
        return VerificationResult(VerificationStatus.VERIFIED, "target_absent")


def obs(label="Compile", request_id="REQ"):
    return VisionObservation(
        width=800, height=600,
        elements=(VisionElement(label, 0.95, 100, 100, 80, 30, text=label),),
        provider="fake", model="fake", request_id=request_id,
    )


def make_scope():
    return CCScope(scope_id="scope", target=None, allowed_region=None, action_budget=5)


def test_closed_loop_completes_after_action_and_verification():
    provider = FakeVisionProvider([obs(request_id="REQ-1"), obs(request_id="REQ-2")])
    pipeline = VisionGroundingPipeline(provider)
    result = CCExecutionResult(True, object(), object())
    agent = VisionComputerAgent(
        computer_control=FakeCC(result), vision=pipeline, planner=Planner(),
        verifier=Verifier(), limits=ComputerAgentLimits(max_cycles=2),
    )
    run = agent.run(goal="click Compile", scope=make_scope(),
                    screenshot_request=VisionRequest("fake", 800, 600),
                    target_label="Compile")
    assert run.state is ComputerAgentState.COMPLETED
    assert run.steps
    assert run.steps[-1].verification is not None


def test_checkpoint_pauses_before_physical_action():
    provider = FakeVisionProvider([obs()])
    pipeline = VisionGroundingPipeline(provider)
    checkpoint = type("CP", (), {"id": "CP-1"})()
    result = CCExecutionResult(False, object(), object(), "checkpoint_required", checkpoint)
    cc = FakeCC(result)
    agent = VisionComputerAgent(
        computer_control=cc, vision=pipeline, planner=Planner(),
        verifier=Verifier(),
    )
    run = agent.run(goal="click Compile", scope=make_scope(),
                    screenshot_request=VisionRequest("fake", 800, 600),
                    target_label="Compile")
    assert run.state is ComputerAgentState.WAITING_APPROVAL
    assert run.pending_checkpoint_id == "CP-1"
    assert cc.calls == 1


def test_limits_are_fail_closed():
    with pytest.raises(ValueError):
        ComputerAgentLimits(max_cycles=0).validate()


def test_replan_budget_is_bounded():
    provider = FakeVisionProvider([obs()])
    pipeline = VisionGroundingPipeline(provider)
    class NoopCC:
        def execute(self, **kwargs):
            return CCExecutionResult(False, object(), object(), "driver_error")
    agent = VisionComputerAgent(
        computer_control=NoopCC(), vision=pipeline, planner=Planner(),
        verifier=Verifier(), limits=ComputerAgentLimits(max_cycles=1, max_replans=0, max_recoveries=0),
    )
    run = agent.run(goal="x", scope=make_scope(),
                    screenshot_request=VisionRequest("fake", 800, 600),
                    target_label="Compile")
    assert run.state is ComputerAgentState.FAILED
    assert run.replans == 0
