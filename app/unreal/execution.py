"""Session orchestration for approved Unreal UI workflows.

This layer coordinates multiple ComputerControl requests without creating
authority. Permission and scope are supplied by the caller; every physical
request still passes through ComputerControlService and its checkpoint.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.computer.models import ExecutionMechanism
from app.computer_control.scopes import CCScope
from app.computer_control.service import ComputerControlService

from .agent import UnrealAgent
from .computer_control import UnrealBridgeResult, UnrealComputerControlBridge
from .models import UnrealPlan


@dataclass(frozen=True)
class UnrealExecutionState:
    step_index: int
    total_steps: int
    checkpoint_id: str | None
    completed: bool


class UnrealExecutionSession:
    """Sequentially execute an already-approved Unreal plan.

    The session never grants COMPUTER_CONTROL and never widens the scope.
    One checkpoint protects each physical request.
    """

    def __init__(
        self,
        *,
        service: ComputerControlService,
        scope: CCScope,
        plan: UnrealPlan,
        observation_fingerprint: str,
        agent: UnrealAgent | None = None,
    ) -> None:
        plan.validate()
        scope.validate()
        if not observation_fingerprint.strip():
            raise ValueError("observation_fingerprint is required")

        self._scope = scope
        self._bridge = UnrealComputerControlBridge(service=service, agent=agent)
        planner_agent = agent or UnrealAgent()
        action_plan = planner_agent.to_action_plan(
            plan=plan, observation_fingerprint=observation_fingerprint
        )
        self._requests = planner_agent.resolve_requests(
            action_plan, mechanism=ExecutionMechanism.COMPUTER_CONTROL
        )
        if not self._requests:
            raise ValueError("Unreal plan produced no computer-control requests")

        self._index = 0
        self._checkpoint_id: str | None = None

    @property
    def state(self) -> UnrealExecutionState:
        return UnrealExecutionState(
            self._index,
            len(self._requests),
            self._checkpoint_id,
            self._index >= len(self._requests),
        )

    def prepare_next(self) -> UnrealBridgeResult:
        if self.state.completed:
            return UnrealBridgeResult(False, error="Unreal execution session is complete")
        if self._checkpoint_id is not None:
            return UnrealBridgeResult(
                False,
                awaiting_checkpoint=True,
                checkpoint_id=self._checkpoint_id,
                error="current Unreal checkpoint is still pending",
            )

        result = self._bridge.prepare_request(
            scope=self._scope,
            request=self._requests[self._index],
        )
        if result.checkpoint_id is not None:
            self._checkpoint_id = result.checkpoint_id
        return result

    def approve_current(self, *, note: str = "") -> UnrealBridgeResult:
        if self._checkpoint_id is None:
            return UnrealBridgeResult(False, error="no pending Unreal checkpoint")
        result = self._bridge.approve(self._checkpoint_id, note=note)
        self._checkpoint_id = None
        if result.ok:
            self._index += 1
        return result

    def refuse_current(self, *, note: str = "") -> UnrealBridgeResult:
        if self._checkpoint_id is None:
            return UnrealBridgeResult(False, error="no pending Unreal checkpoint")
        result = self._bridge.refuse(self._checkpoint_id, note=note)
        self._checkpoint_id = None
        return result
