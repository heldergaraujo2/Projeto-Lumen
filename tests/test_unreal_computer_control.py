import pytest
from datetime import datetime, timedelta, timezone

from app.computer.models import ExecutionMechanism
from app.computer_control.api import CCTarget, CCActionType
from app.computer_control.scopes import CCLimits, CCScope
from app.computer_control.service import ComputerControlService
from app.security.permissions import PermissionLevel, PermissionManager
from app.unreal.agent import UnrealAgent
from app.unreal.computer_control import UnrealComputerControlBridge
from app.unreal.models import UnrealPlan, UnrealProject


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
        scope_id="unreal-test",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        target=CCTarget(app_name="UnrealEditor"),
        allowed_actions=frozenset({CCActionType.WINDOW_FOCUS, CCActionType.KEY_COMBO, CCActionType.KEY_TYPE, CCActionType.KEY_PRESS}),
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


def test_bridge_fails_closed_without_computer_control_permission():
    permissions = PermissionManager()
    driver = FakeDriver()
    service = ComputerControlService(permissions=permissions, driver=driver)
    bridge = UnrealComputerControlBridge(service=service)
    result = bridge.prepare(
        plan=make_plan(),
        observation_fingerprint="obs-1",
        scope=make_scope(),
    )
    assert not result.ok
    assert not result.awaiting_checkpoint
    assert "permission" in (result.error or "").lower()
    assert driver.calls == []


def test_bridge_prepares_checkpoint_without_touching_driver():
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.COMPUTER_CONTROL)
    driver = FakeDriver()
    service = ComputerControlService(permissions=permissions, driver=driver)
    bridge = UnrealComputerControlBridge(service=service)

    result = bridge.prepare(
        plan=make_plan(),
        observation_fingerprint="obs-1",
        scope=make_scope(),
    )

    assert not result.ok
    assert result.awaiting_checkpoint
    assert result.checkpoint_id
    assert driver.calls == []


def test_bridge_approval_is_the_only_path_to_driver_and_consumes_checkpoint():
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.COMPUTER_CONTROL)
    driver = FakeDriver()
    service = ComputerControlService(permissions=permissions, driver=driver)
    bridge = UnrealComputerControlBridge(service=service)

    prepared = bridge.prepare(
        plan=make_plan(),
        observation_fingerprint="obs-1",
        scope=make_scope(),
    )
    approved = bridge.approve(prepared.checkpoint_id, note="test approval")

    assert approved.ok
    assert driver.calls == [
        ("focus_window", CCTarget(app_name="UnrealEditor")),
    ]
    assert approved.execution is not None
    assert approved.execution.checkpoint is not None
    assert approved.execution.checkpoint.status == "CONSUMED"


def test_bridge_rejects_non_computer_control_mechanism():
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.COMPUTER_CONTROL)
    service = ComputerControlService(permissions=permissions, driver=FakeDriver())
    bridge = UnrealComputerControlBridge(service=service)

    result = bridge.prepare(
        plan=make_plan(),
        observation_fingerprint="obs-1",
        scope=make_scope(),
        mechanism=ExecutionMechanism.NATIVE,
    )
    assert not result.ok
    assert not result.awaiting_checkpoint


def test_bridge_verification_never_grants_authority():
    permissions = PermissionManager()
    service = ComputerControlService(permissions=permissions, driver=FakeDriver())
    bridge = UnrealComputerControlBridge(service=service)
    expectation = make_plan().actions[1].expected

    result = bridge.verify(expectation=expectation, found=True)
    assert result.verified
    assert not permissions.is_granted(PermissionLevel.COMPUTER_CONTROL)
