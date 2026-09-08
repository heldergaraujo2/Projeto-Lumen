from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.fake_driver import FakeComputerControlDriver
from app.computer_control.scopes import CCLimits, CCScope
from app.tools.computer_control import CcDoubleClickAndTypeTool


class _Audit:
    def __init__(self):
        self.records: list[dict] = []

    def record(self, **detail):
        self.records.append(detail)


def _scope(*, scope_id: str = "s1", max_actions_total: int = 5, with_title: bool = True) -> CCScope:
    now = datetime.now(timezone.utc)
    target = (
        CCTarget(app_name="Desktop", window_title_pattern="Notepad")
        if with_title
        else CCTarget(app_name="Desktop")
    )
    return CCScope(
        scope_id=scope_id,
        created_at=now,
        expires_at=now + timedelta(seconds=60),
        target=target,
        allowed_actions=frozenset({CCActionType.MOUSE_CLICK, CCActionType.KEY_TYPE}),
        limits=CCLimits(max_actions_total=max_actions_total, max_actions_per_minute=999),
    )


def test_cc_double_click_and_type_success_consumes_two_actions_and_audit_has_no_text():
    audit = _Audit()
    scope = _scope(scope_id="s1", max_actions_total=5, with_title=True)
    scopes: dict[str, CCScope] = {"s1": scope}

    tool = CcDoubleClickAndTypeTool(scopes=scopes, driver=FakeComputerControlDriver(), audit=audit)
    r = tool.run(scope_id="s1", text="HELLO", open_delay_ms=200)
    assert r.ok is True
    assert r.data["chars_typed"] == 5
    assert scope.actions_used == 2

    assert audit.records
    rec = audit.records[-1]
    assert "text" not in rec
    if isinstance(rec.get("detail"), dict):
        assert "text" not in rec["detail"]


def test_cc_double_click_and_type_requires_two_actions_budget():
    scope = _scope(scope_id="s1", max_actions_total=1, with_title=True)
    tool = CcDoubleClickAndTypeTool(scopes={"s1": scope}, driver=FakeComputerControlDriver(), audit=_Audit())
    r = tool.run(scope_id="s1", text="HELLO", open_delay_ms=200)
    assert r.ok is False
    assert r.error == "denied_scope_limit_exceeded"


def test_cc_double_click_and_type_requires_window_title_pattern():
    scope = _scope(scope_id="s1", max_actions_total=5, with_title=False)
    tool = CcDoubleClickAndTypeTool(scopes={"s1": scope}, driver=FakeComputerControlDriver(), audit=_Audit())
    r = tool.run(scope_id="s1", text="HELLO", open_delay_ms=200)
    assert r.ok is False
    assert r.error == "invalid_input"
