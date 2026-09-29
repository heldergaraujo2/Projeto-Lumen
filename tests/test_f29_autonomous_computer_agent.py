from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from app.computer_control.actions import CCActionRequest
from app.computer_control.api import CCActionType, CCTarget, ScreenshotInfo
from app.computer_control.autonomous_agent import (
    ComputerAgentLimits, ComputerAgentState, ComputerPlan, VisionComputerAgent,
)
from app.computer_control.service import CCExecutionResult
from app.computer_control.verification import VerificationExpectation, VerificationResult, VerificationStatus
from app.computer_control.vision import VisionElement, VisionObservation, VisionRequest
from app.computer_control.vision_grounding import VisionGroundingPipeline
from app.computer_control.scopes import CCLimits, CCScope


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
        provider="fake", model="fake",
    )


def make_scope():
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return CCScope(scope_id="scope", created_at=created, expires_at=created + timedelta(minutes=10), target=CCTarget(app_name="test"), allowed_actions=frozenset({CCActionType.MOUSE_CLICK}), limits=CCLimits(max_actions_total=5, max_actions_per_minute=5))


def test_closed_loop_completes_after_action_and_verification():
    provider = FakeVisionProvider([obs(request_id="REQ-1"), obs(request_id="REQ-2")])
    pipeline = VisionGroundingPipeline(provider)
    result = CCExecutionResult(True, object(), object())
    agent = VisionComputerAgent(
        computer_control=FakeCC(result), vision=pipeline, planner=Planner(),
        verifier=Verifier(), limits=ComputerAgentLimits(max_cycles=2),
    )
    run = agent.run(goal="click Compile", scope=make_scope(),
                    screenshot_request=VisionRequest(Path("fake"), "click Compile"),
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
                    screenshot_request=VisionRequest(Path("fake"), "click Compile"),
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


def test_approved_checkpoint_resume_is_forwarded_to_service():
    provider = FakeVisionProvider([obs(), obs(), obs()])
    pipeline = VisionGroundingPipeline(provider)
    checkpoint = type("CP", (), {"id": "CP-2"})()
    results = [
        CCExecutionResult(False, object(), object(), "checkpoint_required", checkpoint),
        CCExecutionResult(True, object(), object()),
    ]

    class RecordingCC:
        def __init__(self):
            self.calls = []
        def execute(self, **kwargs):
            self.calls.append(kwargs)
            return results.pop(0)

    class MovePlanner:
        def plan(self, *, goal, observation, previous_reason=""):
            return ComputerPlan(
                CCActionRequest(CCActionType.MOUSE_MOVE, target=observation.target),
                VerificationExpectation("target_visible", "Compile"),
                "Compile",
            )

    class VisibleVerifier:
        def verify(self, *, expectation, observation):
            return VerificationResult(VerificationStatus.VERIFIED, "target_visible")

    cc = RecordingCC()
    agent = VisionComputerAgent(
        computer_control=cc,
        vision=pipeline,
        planner=MovePlanner(),
        verifier=VisibleVerifier(),
    )
    first = agent.run(
        goal="move to Compile",
        scope=make_scope(),
        screenshot_request=VisionRequest(Path("fake"), "move Compile"),
        target_label="Compile",
    )
    assert first.state is ComputerAgentState.WAITING_APPROVAL
    assert first.pending_checkpoint_id == "CP-2"

    second = agent.run(
        goal="move to Compile",
        scope=make_scope(),
        screenshot_request=VisionRequest(Path("fake"), "move Compile"),
        target_label="Compile",
        approved_checkpoint_id=first.pending_checkpoint_id,
    )
    assert second.state is ComputerAgentState.COMPLETED
    assert cc.calls[1]["approved_checkpoint_id"] == "CP-2"
