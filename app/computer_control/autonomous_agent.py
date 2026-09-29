"""F29 — bounded autonomous computer-agent control loop.

Goal -> Plan -> Observe -> Target -> Action -> Verify -> Recover -> Replan.

The agent is an orchestrator only. It never calls a driver directly and never
grants permission, widens scope, approves checkpoints, or bypasses policy.
Physical execution remains owned by ComputerControlService.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .actions import CCActionRequest
from .api import CCTarget, ScreenRegion
from .service import CCExecutionResult, ComputerControlService
from .verification import VerificationExpectation, VerificationResult, VerificationStatus
from .vision_grounding import VisionGroundingPipeline, VisionGroundingResult
from .scopes import CCScope


class ComputerAgentState(str, Enum):
    OBSERVE = "observe"
    PLAN = "plan"
    TARGET = "target"
    ACTION = "action"
    VERIFY = "verify"
    RECOVER = "recover"
    REPLAN = "replan"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"


@dataclass(frozen=True)
class ComputerAgentLimits:
    max_cycles: int = 8
    max_replans: int = 3
    max_recoveries: int = 3

    def validate(self) -> None:
        if self.max_cycles < 1:
            raise ValueError("max_cycles must be >= 1")
        if self.max_replans < 0 or self.max_recoveries < 0:
            raise ValueError("agent budgets must be >= 0")


@dataclass(frozen=True)
class ComputerAgentStep:
    cycle: int
    state: ComputerAgentState
    action: CCActionRequest | None = None
    reason: str = ""
    verification: VerificationResult | None = None


@dataclass(frozen=True)
class ComputerAgentRun:
    goal: str
    state: ComputerAgentState
    steps: tuple[ComputerAgentStep, ...]
    cycles: int
    replans: int
    recoveries: int
    pending_checkpoint_id: str | None = None


@dataclass(frozen=True)
class ComputerPlan:
    action: CCActionRequest
    expectation: VerificationExpectation
    target_label: str | None = None


@dataclass(frozen=True)
class _PendingApproval:
    goal: str
    target_label: str
    scope_id: str
    plan: ComputerPlan


class ComputerAgentPlanner(Protocol):
    def plan(
        self,
        *,
        goal: str,
        observation: VisionGroundingResult,
        previous_reason: str = "",
    ) -> ComputerPlan: ...


class ComputerAgentVerifier(Protocol):
    def verify(
        self,
        *,
        expectation: VerificationExpectation,
        observation: VisionGroundingResult,
    ) -> VerificationResult: ...


class VisionComputerAgent:
    """Closed-loop autonomous orchestration over the existing security core."""

    def __init__(
        self,
        *,
        computer_control: ComputerControlService,
        vision: VisionGroundingPipeline,
        planner: ComputerAgentPlanner,
        verifier: ComputerAgentVerifier,
        limits: ComputerAgentLimits | None = None,
    ) -> None:
        self.computer_control = computer_control
        self.vision = vision
        self.planner = planner
        self.verifier = verifier
        self.limits = limits or ComputerAgentLimits()
        self.limits.validate()
        self._pending_approvals: dict[str, _PendingApproval] = {}

    def run(
        self,
        *,
        goal: str,
        scope: CCScope,
        screenshot_request,
        target_label: str,
        expected_window: CCTarget | None = None,
        scope_region: ScreenRegion | None = None,
        approved_checkpoint_id: str | None = None,
    ) -> ComputerAgentRun:
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal is required")
        if not target_label.strip():
            raise ValueError("target_label is required")
        steps: list[ComputerAgentStep] = []
        replans = 0
        recoveries = 0
        previous_reason = ""
        pending_plan: ComputerPlan | None = None
        resume_checkpoint_id = approved_checkpoint_id

        if approved_checkpoint_id is not None:
            pending = self._pending_approvals.pop(approved_checkpoint_id, None)
            if pending is None:
                return ComputerAgentRun(
                    goal, ComputerAgentState.FAILED, tuple(steps), 0, replans, recoveries
                )
            if pending.goal != goal or pending.target_label != target_label or pending.scope_id != scope.scope_id:
                return ComputerAgentRun(
                    goal, ComputerAgentState.FAILED, tuple(steps), 0, replans, recoveries
                )
            pending_plan = pending.plan

        for cycle in range(1, self.limits.max_cycles + 1):
            if pending_plan is not None:
                plan = pending_plan
                pending_plan = None
                steps.append(
                    ComputerAgentStep(
                        cycle,
                        ComputerAgentState.PLAN,
                        plan.action,
                        "checkpoint_resume",
                    )
                )
                plan.action.validate()
                plan.expectation.validate()
                steps.append(
                    ComputerAgentStep(
                        cycle,
                        ComputerAgentState.TARGET,
                        plan.action,
                        "checkpoint_target_reused",
                    )
                )
            else:
                observation = self.vision.observe_and_resolve(
                    screenshot_request,
                    label=target_label,
                    scope_region=scope_region,
                    expected_window=expected_window,
                )
                steps.append(ComputerAgentStep(cycle, ComputerAgentState.OBSERVE, reason=observation.reason))
                if observation.target is None:
                    if replans >= self.limits.max_replans:
                        return ComputerAgentRun(goal, ComputerAgentState.FAILED, tuple(steps), cycle, replans, recoveries)
                    replans += 1
                    previous_reason = observation.reason
                    steps.append(ComputerAgentStep(cycle, ComputerAgentState.REPLAN, reason=previous_reason))
                    continue

                plan = self.planner.plan(goal=goal, observation=observation, previous_reason=previous_reason)
                plan.action.validate()
                plan.expectation.validate()
                steps.append(ComputerAgentStep(cycle, ComputerAgentState.PLAN, plan.action, "plan_ready"))
                if plan.action.target is None and plan.target_label:
                    target = observation.target
                    plan = ComputerPlan(
                        CCActionRequest(
                            action=plan.action.action, x=plan.action.x, y=plan.action.y,
                            target=target, text=plan.action.text, keys=plan.action.keys,
                            delta=plan.action.delta, region=plan.action.region, metadata=plan.action.metadata
                        ),
                        plan.expectation, plan.target_label,
                    )
                steps.append(ComputerAgentStep(cycle, ComputerAgentState.TARGET, plan.action, "target_grounded"))

            result: CCExecutionResult = self.computer_control.execute(
                scope=scope,
                request=plan.action,
                approved_checkpoint_id=resume_checkpoint_id,
            )
            resume_checkpoint_id = None
            if not result.success and result.checkpoint is not None and result.error == "checkpoint_required":
                self._pending_approvals[result.checkpoint.id] = _PendingApproval(
                    goal=goal,
                    target_label=target_label,
                    scope_id=scope.scope_id,
                    plan=plan,
                )
                steps.append(ComputerAgentStep(cycle, ComputerAgentState.WAITING_APPROVAL, plan.action, "checkpoint_required"))
                return ComputerAgentRun(
                    goal, ComputerAgentState.WAITING_APPROVAL, tuple(steps), cycle,
                    replans, recoveries, result.checkpoint.id
                )
            steps.append(ComputerAgentStep(cycle, ComputerAgentState.ACTION, plan.action, result.error or "action_executed"))
            if not result.success:
                if recoveries >= self.limits.max_recoveries:
                    return ComputerAgentRun(goal, ComputerAgentState.FAILED, tuple(steps), cycle, replans, recoveries)
                recoveries += 1
                previous_reason = result.error or "action_failed"
                steps.append(ComputerAgentStep(cycle, ComputerAgentState.RECOVER, plan.action, previous_reason))
                continue

            post = self.vision.observe_and_resolve(
                screenshot_request,
                label=target_label,
                scope_region=scope_region,
                expected_window=expected_window,
            )
            verification = self.verifier.verify(expectation=plan.expectation, observation=post)
            steps.append(ComputerAgentStep(cycle, ComputerAgentState.VERIFY, plan.action, verification.reason, verification))
            if verification.status is VerificationStatus.VERIFIED:
                return ComputerAgentRun(goal, ComputerAgentState.COMPLETED, tuple(steps), cycle, replans, recoveries)
            if verification.status is VerificationStatus.INCONCLUSIVE:
                if recoveries >= self.limits.max_recoveries:
                    return ComputerAgentRun(goal, ComputerAgentState.FAILED, tuple(steps), cycle, replans, recoveries)
                recoveries += 1
                previous_reason = verification.reason
                steps.append(ComputerAgentStep(cycle, ComputerAgentState.RECOVER, plan.action, previous_reason))
            else:
                if replans >= self.limits.max_replans:
                    return ComputerAgentRun(goal, ComputerAgentState.FAILED, tuple(steps), cycle, replans, recoveries)
                replans += 1
                previous_reason = verification.reason
                steps.append(ComputerAgentStep(cycle, ComputerAgentState.REPLAN, plan.action, previous_reason))

        return ComputerAgentRun(goal, ComputerAgentState.FAILED, tuple(steps), self.limits.max_cycles, replans, recoveries)
        return ComputerAgentRun(goal, ComputerAgentState.FAILED, tuple(steps), self.limits.max_cycles, replans, recoveries)
