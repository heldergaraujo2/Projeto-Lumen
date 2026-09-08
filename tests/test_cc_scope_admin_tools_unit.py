from __future__ import annotations

from app.computer_control.fake_driver import FakeComputerControlDriver
from app.tools.computer_control import (
    CcListScopesTool,
    CcRevokeScopeTool,
    CcRequestScopeTool,
)


class _Audit:
    def __init__(self):
        self.records: list[dict] = []

    def record(self, **detail):
        self.records.append(detail)


def test_cc_list_scopes_empty_then_one_then_revoked():
    audit = _Audit()
    scopes: dict = {}

    list_tool = CcListScopesTool(scopes=scopes, audit=audit)
    r0 = list_tool.run()
    assert r0.ok is True
    assert r0.data["count"] == 0

    req = CcRequestScopeTool(scopes=scopes, audit=audit)
    r1 = req.run(
        allowed_actions=["mouse_move"],
        expires_in_s=60,
        max_actions_total=2,
        max_actions_per_minute=1,
        app_name="Desktop",
    )
    assert r1.ok is True
    scope_id = r1.data["scope_id"]

    r2 = list_tool.run()
    assert r2.ok is True
    assert r2.data["count"] == 1
    assert r2.data["scopes"][0]["scope_id"] == scope_id

    revoke = CcRevokeScopeTool(scopes=scopes, audit=audit)
    r3 = revoke.run(scope_id=scope_id)
    assert r3.ok is True
    assert scope_id not in scopes

    r4 = list_tool.run()
    assert r4.ok is True
    assert r4.data["count"] == 0


def test_cc_revoke_scope_missing_is_error():
    audit = _Audit()
    scopes: dict = {}
    revoke = CcRevokeScopeTool(scopes=scopes, audit=audit)
    r = revoke.run(scope_id="missing")
    assert r.ok is False
    assert r.error == "scope_not_found"
