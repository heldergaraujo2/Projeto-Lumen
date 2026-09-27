from __future__ import annotations

from dataclasses import dataclass

from app.computer.actions import ActionPlanner
from app.computer.models import ActionPlan, ComputerObservation, ExecutionMechanism
from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.actions import CCActionRequest
from app.computer_control.verification import VerificationExpectation

from .models import UnrealAction, UnrealOperation, UnrealPlan, UnrealProject, UnrealRisk
from .shortcuts import (
    OPEN_ASSET,
    OPEN_LEVEL,
    PLAY_IN_EDITOR,
    SAVE,
    SAVE_ALL,
    STOP_PLAY,
)


@dataclass(frozen=True)
class UnrealAgent:
    """Plans Unreal Editor workflows; physical execution remains in F7 ComputerControlService."""

    planner: ActionPlanner = ActionPlanner()

    def plan(self, *, project: UnrealProject, goal: str, observation: ComputerObservation | None = None) -> UnrealPlan:
        project.validate()
        goal = goal.strip()
        if not goal:
            raise ValueError("goal is required")

        normalized = " ".join(goal.casefold().split())
        actions: list[UnrealAction] = [self.focus_editor()]

        if normalized in {"salvar", "salvar projeto", "save", "save project"}:
            actions.append(self.save())
        elif normalized in {"salvar tudo", "save all"}:
            actions.append(self.save_all())
        elif normalized in {"iniciar pie", "play", "play in editor", "executar projeto"}:
            actions.append(self.play())
        elif normalized in {"parar pie", "stop", "stop play"}:
            actions.append(self.stop_play())
        else:
            raise ValueError("unsupported Unreal goal; use a structured UnrealAgent operation")

        plan = UnrealPlan(project=project, goal=goal, actions=tuple(actions))
        plan.validate()
        if observation is not None:
            observation.validate()
        return plan

    def focus_editor(self) -> UnrealAction:
        return UnrealAction(
            UnrealOperation.FOCUS_EDITOR,
            expected=VerificationExpectation("window_focused", "UnrealEditor"),
            rationale="Focus the explicitly authorized Unreal Editor window before UI interaction.",
        )

    def open_asset(self, asset: str) -> UnrealAction:
        asset = asset.strip()
        if not asset:
            raise ValueError("asset is required")
        return UnrealAction(
            UnrealOperation.OPEN_ASSET,
            value=asset,
            keys=OPEN_ASSET,
            expected=VerificationExpectation("target_visible", asset),
            rationale="Open an explicitly named Unreal asset through the editor asset picker.",
        )

    def open_level(self, level: str) -> UnrealAction:
        level = level.strip()
        if not level:
            raise ValueError("level is required")
        return UnrealAction(
            UnrealOperation.OPEN_LEVEL,
            value=level,
            keys=OPEN_LEVEL,
            expected=VerificationExpectation("target_visible", level),
            rationale="Open an explicitly named Unreal level.",
        )

    def save(self) -> UnrealAction:
        return UnrealAction(
            UnrealOperation.SAVE,
            keys=SAVE,
            expected=VerificationExpectation("state_changed"),
            rationale="Save the current Unreal asset/level.",
        )

    def save_all(self) -> UnrealAction:
        return UnrealAction(
            UnrealOperation.SAVE_ALL,
            keys=SAVE_ALL,
            expected=VerificationExpectation("state_changed"),
            rationale="Save all modified Unreal assets/levels.",
        )

    def play(self) -> UnrealAction:
        return UnrealAction(
            UnrealOperation.PLAY,
            keys=PLAY_IN_EDITOR,
            expected=VerificationExpectation("state_changed"),
            rationale="Start Play In Editor using the documented editor shortcut.",
        )

    def stop_play(self) -> UnrealAction:
        return UnrealAction(
            UnrealOperation.STOP_PLAY,
            keys=STOP_PLAY,
            expected=VerificationExpectation("state_changed"),
            rationale="Request stopping the current play session.",
        )

    def to_action_plan(self, *, plan: UnrealPlan, observation_fingerprint: str) -> ActionPlan:
        plan.validate()
        if not observation_fingerprint.strip():
            raise ValueError("observation_fingerprint is required")

        intents = []
        for action in plan.actions:
            if action.operation is UnrealOperation.FOCUS_EDITOR:
                intents.append(self.planner.window_focus(rationale=action.rationale))
            elif action.operation is UnrealOperation.OPEN_ASSET:
                intents.extend([
                    self.planner.key_combo(*action.keys, rationale=action.rationale),
                    self.planner.type_text(action.value or "", rationale="Enter the exact asset search term."),
                    self.planner.key_press("ENTER", rationale="Confirm the selected asset."),
                ])
            elif action.operation is UnrealOperation.OPEN_LEVEL:
                intents.extend([
                    self.planner.key_combo(*action.keys, rationale=action.rationale),
                    self.planner.type_text(action.value or "", rationale="Enter the exact level search term."),
                    self.planner.key_press("ENTER", rationale="Confirm the selected level."),
                ])
            else:
                if len(action.keys) > 1:
                    intents.append(self.planner.key_combo(*action.keys, rationale=action.rationale))
                else:
                    intents.append(self.planner.key_press(action.keys[0], rationale=action.rationale))

        result = self.planner.build(observation_fingerprint, *intents, rationale=plan.goal)
        return result

    def resolve_requests(self, action_plan: ActionPlan, *, mechanism: ExecutionMechanism) -> tuple[CCActionRequest, ...]:
        action_plan.validate()
        requests = []
        for intent in action_plan.intents:
            action = CCActionType(intent.action)
            requests.append(
                CCActionRequest(
                    action=action,
                    text=intent.parameters.get("text"),
                    keys=tuple(intent.parameters.get("keys", ())),
                )
            )
        return tuple(requests)

    @staticmethod
    def required_target(project: UnrealProject) -> CCTarget:
        return project.editor_window

    def save_and_play(self, *, project: UnrealProject) -> UnrealPlan:
        plan = UnrealPlan(
            project=project,
            goal="save and play",
            actions=(self.save(), self.play()),
        )
        plan.validate()
        return plan
