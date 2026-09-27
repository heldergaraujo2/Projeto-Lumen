from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.fake_driver import FakeComputerControlDriver
from app.computer_control.scopes import CCLimits, CCScope
from app.tools.computer_control import CcMouseMoveToTool


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
        target=CCTarget(app_name="Desktop"),
        allowed_actions=frozenset({CCActionType.MOUSE_MOVE}),
        limits=CCLimits(max_actions_total=5, max_actions_per_minute=999),
    )


def test_cc_mouse_move_to_consumes_one_action():
    audit = _Audit()
    scope = _scope("s1")
    tool = CcMouseMoveToTool(scopes={"s1": scope}, driver=FakeComputerControlDriver(), audit=audit)
    r = tool.run(scope_id="s1", x=123, y=456)
    assert r.ok is True
    assert scope.actions_used == 1
    assert audit.records
