from datetime import datetime, timedelta, timezone

from app.computer.models import ExecutionMechanism
from app.computer_control.api import CCTarget, CCActionType
from app.computer_control.scopes import CCLimits, CCScope
from app.computer_control.service import ComputerControlService
from app.security.permissions import PermissionLevel, PermissionManager
from app.unreal.agent import UnrealAgent
from app.unreal.execution import UnrealExecutionSession
from app.unreal.models import UnrealProject


class FakeDriver:
    def __init__(self): self.calls = []
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
        scope_id="unreal-session-test",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        target=CCTarget(app_name="UnrealEditor"),
        allowed_actions=frozenset({
            CCActionType.WINDOW_FOCUS, CCActionType.KEY_COMBO,
            CCActionType.KEY_TYPE, CCActionType.KEY_PRESS,
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


def make_session(driver):
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.COMPUTER_CONTROL)
    service = ComputerControlService(permissions=permissions, driver=driver)
    return UnrealExecutionSession(
        service=service,
        scope=make_scope(),
        plan=make_plan(),
        observation_fingerprint="obs-asset-open",
    )


def test_unreal_session_has_one_checkpoint_per_physical_request():
    driver = FakeDriver()
    session = make_session(driver)

    assert session.state.total_steps == 4
    first = session.prepare_next()
    assert first.awaiting_checkpoint
    assert driver.calls == []

    approved = session.approve_current(note="test")
    assert approved.ok
    assert driver.calls == [("focus_window", CCTarget(app_name="UnrealEditor"))]
    assert session.state.step_index == 1
    assert session.state.checkpoint_id is None


def test_unreal_session_does_not_skip_pending_checkpoint():
    driver = FakeDriver()
    session = make_session(driver)
    first = session.prepare_next()

    blocked = session.prepare_next()
    assert blocked.awaiting_checkpoint
    assert blocked.checkpoint_id == first.checkpoint_id
    assert driver.calls == []


def test_unreal_session_refusal_stops_without_driver_action():
    driver = FakeDriver()
    session = make_session(driver)
    prepared = session.prepare_next()

    refused = session.refuse_current(note="not authorized")
    assert not refused.ok
    assert prepared.checkpoint_id
    assert driver.calls == []
    assert session.state.step_index == 0


def test_unreal_session_requires_explicit_computer_control_permission():
    driver = FakeDriver()
    permissions = PermissionManager()
    service = ComputerControlService(permissions=permissions, driver=driver)
    session = UnrealExecutionSession(
        service=service,
        scope=make_scope(),
        plan=make_plan(),
        observation_fingerprint="obs-asset-open",
    )
    result = session.prepare_next()
    assert not result.awaiting_checkpoint
    assert not result.ok
    assert driver.calls == []
