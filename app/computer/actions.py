from __future__ import annotations

from app.computer_control.actions import CCActionRequest
from app.computer_control.api import CCActionType
from app.computer_control.grounding import GroundedTarget

from .models import ActionIntent, ActionPlan, ExecutionMechanism


class ActionPlanner:
    """Builds intents/plans only; no driver or OS execution."""

    def click(self, target: GroundedTarget, *, rationale: str = "") -> ActionIntent:
        target.validate()
        return ActionIntent(CCActionType.MOUSE_CLICK.value, target=target, rationale=rationale)

    def type_text(self, text: str, *, rationale: str = "") -> ActionIntent:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        return ActionIntent(CCActionType.KEY_TYPE.value, parameters={"text": text}, rationale=rationale)

    def key_press(self, key: str, *, rationale: str = "") -> ActionIntent:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")
        return ActionIntent(CCActionType.KEY_PRESS.value, parameters={"keys": (key,)}, rationale=rationale)

    def window_focus(self, *, rationale: str = "") -> ActionIntent:
        return ActionIntent(CCActionType.WINDOW_FOCUS.value, rationale=rationale)

    def key_combo(self, *keys: str, rationale: str = "") -> ActionIntent:
        if not keys or any(not isinstance(key, str) or not key for key in keys):
            raise ValueError("at least one non-empty key is required")
        return ActionIntent(CCActionType.KEY_COMBO.value, parameters={"keys": tuple(keys)}, rationale=rationale)

    def build(self, observation_fingerprint: str, *intents: ActionIntent, rationale: str = "") -> ActionPlan:
        plan = ActionPlan(tuple(intents), observation_fingerprint, rationale)
        plan.validate()
        return plan


class ExecutionResolver:
    """Converts an intent into the existing request contract, but never executes."""

    def resolve(self, intent: ActionIntent, *, mechanism: ExecutionMechanism) -> CCActionRequest:
        intent.validate()
        if mechanism is ExecutionMechanism.NONE:
            raise PermissionError("no execution mechanism resolved")
        action = CCActionType(intent.action)
        if action is CCActionType.MOUSE_CLICK and intent.target is None:
            raise ValueError("mouse click intent requires a grounded target")
        return CCActionRequest(
            action=action,
            target=intent.target,
            text=intent.parameters.get("text"),
            keys=tuple(intent.parameters.get("keys", ())),
        )
