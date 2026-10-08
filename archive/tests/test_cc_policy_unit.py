from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.policy import evaluate_cc_action
from app.computer_control.scopes import CCLimits, CCScope

UTC = timezone.utc


def valid_scope(*, max_total: int = 2) -> CCScope:
    created = datetime(2020, 1, 1, tzinfo=UTC)
    expires = datetime(2020, 1, 2, tzinfo=UTC)
    s = CCScope(
        scope_id="scope-ok",
        created_at=created,
        expires_at=expires,
        target=CCTarget(app_name="demo"),
        allowed_actions=frozenset({CCActionType.SCREENSHOT}),
        limits=CCLimits(max_actions_total=max_total, max_actions_per_minute=10),
    )
    s.validate()
    return s


def test_denied_no_permission():
    s = valid_scope()
    d = evaluate_cc_action(has_computer_control_permission=False, scope=s, action=CCActionType.SCREENSHOT)
    assert (d.allowed, d.reason) == (False, "denied_no_permission")


def test_denied_no_scope():
    d = evaluate_cc_action(has_computer_control_permission=True, scope=None, action=CCActionType.SCREENSHOT)
    assert (d.allowed, d.reason) == (False, "denied_no_scope")


def test_denied_invalid_scope():
    bad = CCScope(
        scope_id="scope-bad",
        created_at=datetime(2020, 1, 1),  # naive
        expires_at=datetime(2020, 1, 2, tzinfo=UTC),
        target=CCTarget(app_name="demo"),
        allowed_actions=frozenset({CCActionType.SCREENSHOT}),
        limits=CCLimits(max_actions_total=1, max_actions_per_minute=1),
    )
    d = evaluate_cc_action(has_computer_control_permission=True, scope=bad, action=CCActionType.SCREENSHOT)
    assert (d.allowed, d.reason, d.scope_id) == (False, "denied_invalid_scope", "scope-bad")


def test_denied_scope_expired():
    s = valid_scope()
    d = evaluate_cc_action(has_computer_control_permission=True, scope=s, action=CCActionType.SCREENSHOT, now=s.expires_at)
    assert (d.allowed, d.reason, d.scope_id) == (False, "denied_scope_expired", s.scope_id)


def test_denied_action_not_allowed():
    s = valid_scope()
    d = evaluate_cc_action(
        has_computer_control_permission=True,
        scope=s,
        action=CCActionType.MOUSE_CLICK,
        now=s.created_at + timedelta(seconds=1),
    )
    assert (d.allowed, d.reason, d.scope_id) == (False, "denied_action_not_allowed", s.scope_id)


def test_denied_scope_limit_exceeded():
    s = valid_scope(max_total=1)
    s.consume_action(now=s.created_at + timedelta(seconds=1))
    d = evaluate_cc_action(
        has_computer_control_permission=True,
        scope=s,
        action=CCActionType.SCREENSHOT,
        now=s.created_at + timedelta(seconds=2),
    )
    assert (d.allowed, d.reason, d.scope_id) == (False, "denied_scope_limit_exceeded", s.scope_id)


def test_allowed():
    s = valid_scope(max_total=2)
    d = evaluate_cc_action(
        has_computer_control_permission=True,
        scope=s,
        action=CCActionType.SCREENSHOT,
        now=s.created_at + timedelta(seconds=1),
    )
    assert (d.allowed, d.reason, d.scope_id) == (True, "allowed", s.scope_id)
