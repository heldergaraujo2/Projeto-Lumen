from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.fake_driver import FakeComputerControlDriver
from app.computer_control.scopes import CCLimits, CCScope
from app.tools.computer_control import CcFocusWindowTool, CcWaitForWindowTool


class _Audit:
    def __init__(self):
        self.records: list[dict] = []

    def record(self, **detail):
        self.records.append(detail)


def _scope(scope_id: str = "s1") -> CCScope:
    now = datetime.now(timezone.utc)
    return CCScope(
        scope_id=scope_id,
        created_at=now,
        expires_at=now + timedelta(seconds=60),
        target=CCTarget(app_name="Desktop", window_title_pattern="Notepad"),
        allowed_actions=frozenset({CCActionType.WINDOW_FOCUS, CCActionType.WINDOW_WAIT}),
        limits=CCLimits(max_actions_total=5, max_actions_per_minute=999),
    )


def test_cc_focus_window_success_fake_driver():
    audit = _Audit()
    scope = _scope("s1")
    tool = CcFocusWindowTool(scopes={"s1": scope}, driver=FakeComputerControlDriver(), audit=audit)
    r = tool.run(scope_id="s1")
    assert r.ok is True
    assert r.data["focused"] is True


def test_cc_wait_for_window_success_fake_driver():
    audit = _Audit()
    scope = _scope("s1")
    tool = CcWaitForWindowTool(scopes={"s1": scope}, driver=FakeComputerControlDriver(), audit=audit)
    r = tool.run(scope_id="s1", timeout_s=2)
    assert r.ok is True
    assert r.data["found"] is True


def test_cc_wait_for_window_requires_title_pattern():
    scope = _scope("s1")
    scope.target = CCTarget(app_name="Desktop", window_title_pattern=None)  # type: ignore[misc]
    tool = CcWaitForWindowTool(scopes={"s1": scope}, driver=FakeComputerControlDriver(), audit=_Audit())
    r = tool.run(scope_id="s1", timeout_s=2)
    assert r.ok is False
    assert r.error == "invalid_input"
