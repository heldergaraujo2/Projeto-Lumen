from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.fake_driver import FakeComputerControlDriver
from app.computer_control.scopes import CCLimits, CCScope
from app.tools.computer_control import CcMouseClickTool


class _Audit:
    def __init__(self):
        self.records: list[dict] = []

    def record(self, **detail):
        self.records.append(detail)


def _make_scope(*, scope_id: str = "s1", max_actions_total: int = 1) -> CCScope:
    now = datetime.now(timezone.utc)
    return CCScope(
        scope_id=scope_id,
        created_at=now,
        expires_at=now + timedelta(seconds=60),
        target=CCTarget(app_name="Desktop"),
        allowed_actions=frozenset({CCActionType.MOUSE_CLICK}),
        limits=CCLimits(max_actions_total=max_actions_total, max_actions_per_minute=999),
    )


def test_cc_mouse_click_success_then_denied_by_budget():
    audit = _Audit()
    scopes: dict[str, CCScope] = {"s1": _make_scope(scope_id="s1", max_actions_total=1)}
    tool = CcMouseClickTool(scopes=scopes, driver=FakeComputerControlDriver(), audit=audit)

    r1 = tool.run(scope_id="s1")
    assert r1.ok is True
    assert r1.data["click"]["button"] == "left"

    r2 = tool.run(scope_id="s1")
    assert r2.ok is False
    assert r2.error == "denied_scope_limit_exceeded"


def test_cc_mouse_click_invalid_input_missing_scope_id():
    tool = CcMouseClickTool(scopes={}, driver=FakeComputerControlDriver(), audit=_Audit())
    r = tool.run(scope_id="")
    assert r.ok is False
    assert r.error == "invalid_input"
