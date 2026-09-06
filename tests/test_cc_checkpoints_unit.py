from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.fake_driver import FakeComputerControlDriver
from app.computer_control.scopes import CCLimits, CCScope
from app.planner.models import PlannedTask
from app.security.permissions import PermissionManager
from app.tools.base import ToolRegistry
from app.tools.computer_control import (
    CcMouseClickAtTool,
    CcMouseClickTool,
    CcKeyTypeTool,
    PrevalidatedComputerControlCheckpoints,
)


def _scope(*, scope_id: str, action: CCActionType = CCActionType.MOUSE_CLICK, max_actions_total: int = 2) -> CCScope:
    now = datetime.now(timezone.utc)
    return CCScope(
        scope_id=scope_id,
        created_at=now,
        expires_at=now + timedelta(seconds=60),
        target=CCTarget(app_name="Desktop", window_title_pattern="Notepad"),
        allowed_actions=frozenset({action}),
        limits=CCLimits(max_actions_total=max_actions_total, max_actions_per_minute=999),
    )


def test_cc_click_checkpoint_required_only_when_viable():
    permissions = PermissionManager()
    permissions.grant("COMPUTER_CONTROL")

    scopes: dict[str, CCScope] = {"s1": _scope(scope_id="s1"), "s2": _scope(scope_id="s2", action=CCActionType.KEY_TYPE)}
    reg = ToolRegistry()  # s? precisamos do get()

    reg.register(CcMouseClickTool(scopes=scopes, driver=FakeComputerControlDriver()))
    reg.register(CcKeyTypeTool(scopes=scopes, driver=FakeComputerControlDriver()))
    reg.register(CcMouseClickAtTool(scopes=scopes, driver=FakeComputerControlDriver()))

    policy = PrevalidatedComputerControlCheckpoints(permissions, reg, scopes)

    t_ok = PlannedTask(
        id="T1",
        description="click",
        order=1,
        dependencies=(),
        tool="cc_mouse_click",
        parameters={"scope_id": "s1"},
    )
    assert policy.requires_checkpoint(t_ok) is True

    t_key = PlannedTask(
        id="T3",
        description="type",
        order=1,
        dependencies=(),
        tool="cc_key_type",
        parameters={"scope_id": "s2", "text": "abc"},
    )
    assert policy.requires_checkpoint(t_key) is True

    t_key_bad = PlannedTask(
        id="T4",
        description="type bad",
        order=1,
        dependencies=(),
        tool="cc_key_type",
        parameters={"scope_id": "s2", "text": "a\n"},
    )
    assert policy.requires_checkpoint(t_key_bad) is False

    t_missing = PlannedTask(
        id="T2",
        description="click missing",
        order=1,
        dependencies=(),
        tool="cc_mouse_click",
        parameters={"scope_id": "missing"},
    )
    assert policy.requires_checkpoint(t_missing) is False


def test_cc_click_checkpoint_not_required_without_permission():
    permissions = PermissionManager()  # n?o concede COMPUTER_CONTROL

    scopes: dict[str, CCScope] = {"s1": _scope(scope_id="s1")}
    reg = ToolRegistry()
    reg.register(CcMouseClickTool(scopes=scopes, driver=FakeComputerControlDriver()))
    policy = PrevalidatedComputerControlCheckpoints(permissions, reg, scopes)

    t_ok = PlannedTask(
        id="T1",
        description="click",
        order=1,
        dependencies=(),
        tool="cc_mouse_click",
        parameters={"scope_id": "s1"},
    )
    assert policy.requires_checkpoint(t_ok) is False
