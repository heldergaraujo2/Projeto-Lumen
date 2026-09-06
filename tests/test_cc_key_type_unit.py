from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.fake_driver import FakeComputerControlDriver
from app.computer_control.scopes import CCLimits, CCScope
from app.tools.computer_control import CcKeyTypeTool


class _Audit:
    def __init__(self):
        self.records: list[dict] = []

    def record(self, **detail):
        self.records.append(detail)


def _make_scope(*, scope_id: str = "s1", max_actions_total: int = 2) -> CCScope:
    now = datetime.now(timezone.utc)
    return CCScope(
        scope_id=scope_id,
        created_at=now,
        expires_at=now + timedelta(seconds=60),
        target=CCTarget(app_name="Desktop", window_title_pattern="Notepad"),
        allowed_actions=frozenset({CCActionType.KEY_TYPE}),
        limits=CCLimits(max_actions_total=max_actions_total, max_actions_per_minute=999),
    )


def test_cc_key_type_success_and_audit_has_no_text():
    audit = _Audit()
    scopes: dict[str, CCScope] = {"s1": _make_scope(scope_id="s1", max_actions_total=2)}
    tool = CcKeyTypeTool(scopes=scopes, driver=FakeComputerControlDriver(), audit=audit)

    r = tool.run(scope_id="s1", text="abc")
    assert r.ok is True
    assert r.data["chars_typed"] == 3

    assert audit.records
    rec = audit.records[-1]
    # Nunca deve aparecer o texto digitado na auditoria:
    assert "text" not in rec
    # e nem dentro de detail (quando audit real serializa extras):
    if isinstance(rec.get("detail"), dict):
        assert "text" not in rec["detail"]


def test_cc_key_type_rejects_control_chars_and_too_long():
    tool = CcKeyTypeTool(scopes={"s1": _make_scope(scope_id="s1")}, driver=FakeComputerControlDriver(), audit=_Audit())

    r1 = tool.run(scope_id="s1", text="a\n")
    assert r1.ok is False and r1.error == "invalid_input"

    r2 = tool.run(scope_id="s1", text=("x" * 81))
    assert r2.ok is False and r2.error == "invalid_input"
