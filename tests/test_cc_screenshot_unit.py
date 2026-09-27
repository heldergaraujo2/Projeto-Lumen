"""CC-5: CcScreenshotTool — unidade (FakeDriver, sem controller/OS).

Cobre o fail-closed (sem scope), o consumo de orçamento do scope, o
retorno metadata-only (artifact_ref, sem bytes) e o shape da auditoria.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.fake_driver import FakeComputerControlDriver
from app.computer_control.scopes import CCLimits, CCScope
from app.tools.computer_control import CcScreenshotTool


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **detail) -> None:
        self.records.append(detail)


def _make_scope(*, scope_id: str = "s1", max_actions_total: int = 1) -> CCScope:
    now = datetime.now(timezone.utc)
    return CCScope(
        scope_id=scope_id,
        created_at=now,
        expires_at=now + timedelta(seconds=60),
        target=CCTarget(app_name="Notepad"),
        allowed_actions=frozenset({CCActionType.SCREENSHOT}),
        limits=CCLimits(
            max_actions_total=max_actions_total, max_actions_per_minute=1
        ),
    )


def test_cc_screenshot_denied_no_scope():
    audit = _Audit()
    tool = CcScreenshotTool(
        scopes={}, driver=FakeComputerControlDriver(), audit=audit
    )
    r = tool.run(scope_id="missing")
    assert r.ok is False
    assert r.error == "denied_no_scope"


def test_cc_screenshot_success_consumes_budget_and_returns_artifact_ref():
    audit = _Audit()
    scopes: dict[str, CCScope] = {}
    scope = _make_scope(scope_id="s1", max_actions_total=1)
    scopes["s1"] = scope

    tool = CcScreenshotTool(
        scopes=scopes, driver=FakeComputerControlDriver(), audit=audit
    )

    r1 = tool.run(scope_id="s1")
    assert r1.ok is True
    assert scope.actions_used == 1
    assert r1.data["screenshot"]["artifact_ref"].startswith("fake:screenshot:")

    r2 = tool.run(scope_id="s1")
    assert r2.ok is False
    assert r2.error in {
        "denied_scope_limit_exceeded",
        "denied_action_not_allowed",
        "denied_scope_expired",
    }


def test_cc_screenshot_audit_metadata_only_shape():
    audit = _Audit()
    scopes: dict[str, CCScope] = {}
    scopes["s1"] = _make_scope(scope_id="s1", max_actions_total=1)

    tool = CcScreenshotTool(
        scopes=scopes, driver=FakeComputerControlDriver(), audit=audit
    )
    r = tool.run(scope_id="s1")
    assert r.ok is True
    assert audit.records, "expected at least one audit record"

    rec = audit.records[-1]
    assert rec.get("tool") == "cc_screenshot"
    assert rec.get("operation") == "cc_screenshot"
    assert rec.get("requested_path") is None
    assert rec.get("resolved_path") is None
    assert rec.get("artifact_ref") == r.data["screenshot"]["artifact_ref"]
