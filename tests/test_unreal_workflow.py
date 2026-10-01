from datetime import datetime, timedelta, timezone

import pytest

from app.computer.models import ExecutionMechanism
from app.computer_control.api import CCTarget, CCActionType
from app.computer_control.scopes import CCLimits, CCScope
from app.computer_control.service import ComputerControlService
from app.security.permissions import PermissionLevel, PermissionManager
from app.unreal.agent import UnrealAgent
from app.unreal.models import UnrealProject
from app.unreal.workflow import UnrealWorkflowCoordinator


class FakeDriver:
    def __init__(self):
        self.calls = []

    def screenshot(self, **kwargs): self.calls.append(("screenshot", kwargs))
    def mouse_move(self, x, y): self.calls.append(("mouse_move", x, y))
    def mouse_click(self, x, y, *, button="left"): self.calls.append(("mouse_click", x, y, button))
    def mouse_double_click(self, x, y, *, button="left"): self.calls.append(("mouse_double_click", x, y, button))
    def mouse_drag(self, x1, y1, x2, y2, *, button="left"): self.calls.append(("mouse_drag", x1, y1, x2, y2, button))
    def scroll(self, delta): self.calls.append(("scroll", delta))
    def key_press(self, key): self.calls.append(("key_press", key))
    def key_combo(self, keys): self.calls.append(("key_combo", keys))
    def type_text(self, text): self.calls.append(("type_text", text))
    def focus_window(self, target): self.calls.append(("focus_window", target))


def make_scope():
    now = datetime.now(timezone.utc)
    return CCScope(
        scope_id="unreal-ui-workflow-test",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        target=CCTarget(app_name="UnrealEditor"),
        allowed_actions=frozenset({
            CCActionType.WINDOW_FOCUS,
            CCActionType.KEY_COMBO,
            CCActionType.KEY_TYPE,
            CCActionType.KEY_PRESS,
        }),
        limits=CCLimits(max_actions_total=10, max_actions_per_minute=10),
    )


def make_plan():
    project = UnrealProject(
        name="AgeOfAether",
        root="C:/Games/AgeOfAether",
        engine_version="5.8",
        editor_window=CCTarget(app_name="UnrealEditor"),
    )
    return UnrealAgent().plan(project=project, goal="abrir asset /Game/BP_Player")


def make_coordinator(driver):
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.COMPUTER_CONTROL)
    service = ComputerControlService(permissions=permissions, driver=driver)
    return UnrealWorkflowCoordinator(service=service)


def test_coordinator_requires_explicit_session_inputs():
    driver = FakeDriver()
    coordinator = make_coordinator(driver)

    with pytest.raises(RuntimeError, match="no Unreal workflow"):
        coordinator.prepare_next()
    assert coordinator.status().active is False
    assert driver.calls == []


def test_coordinator_preserves_checkpoint_boundary():
    driver = FakeDriver()
    coordinator = make_coordinator(driver)

    status = coordinator.start(
        plan=make_plan(),
        scope=make_scope(),
        observation_fingerprint="obs-ui-workflow",
    )
    assert status.active
    assert status.state is not None
    assert status.state.total_steps == 4

    prepared = coordinator.prepare_next()
    assert prepared.awaiting_checkpoint
    assert prepared.checkpoint_id
    assert driver.calls == []

    pending = coordinator.status()
    assert pending.checkpoint_id == prepared.checkpoint_id

    blocked = coordinator.prepare_next()
    assert blocked.awaiting_checkpoint
    assert blocked.checkpoint_id == prepared.checkpoint_id
    assert driver.calls == []


def test_coordinator_approval_advances_only_after_service_execution():
    driver = FakeDriver()
    coordinator = make_coordinator(driver)
    coordinator.start(
        plan=make_plan(),
        scope=make_scope(),
        observation_fingerprint="obs-ui-workflow",
    )

    coordinator.prepare_next()
    result = coordinator.approve_current(note="explicit UI approval")

    assert result.ok
    assert driver.calls == [("focus_window", CCTarget(app_name="UnrealEditor"))]
    assert coordinator.status().state.step_index == 1


def test_coordinator_refusal_never_reaches_driver():
    driver = FakeDriver()
    coordinator = make_coordinator(driver)
    coordinator.start(
        plan=make_plan(),
        scope=make_scope(),
        observation_fingerprint="obs-ui-workflow",
    )

    prepared = coordinator.prepare_next()
    result = coordinator.refuse_current(note="user refused")

    assert prepared.checkpoint_id
    assert not result.ok
    assert driver.calls == []
    assert coordinator.status().state.step_index == 0


def test_coordinator_does_not_grant_computer_control():
    driver = FakeDriver()
    permissions = PermissionManager()
    service = ComputerControlService(permissions=permissions, driver=driver)
    coordinator = UnrealWorkflowCoordinator(service=service)

    coordinator.start(
        plan=make_plan(),
        scope=make_scope(),
        observation_fingerprint="obs-ui-workflow",
    )
    result = coordinator.prepare_next()

    assert not result.ok
    assert not result.awaiting_checkpoint
    assert not permissions.is_granted(PermissionLevel.COMPUTER_CONTROL)
    assert driver.calls == []
