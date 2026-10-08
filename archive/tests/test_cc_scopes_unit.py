from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.scopes import CCLimits, CCScope


def dt_utc(y: int, m: int, d: int, hh: int = 0, mm: int = 0, ss: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)


def test_limits_validate_requires_positive_values() -> None:
    with pytest.raises(ValueError):
        CCLimits(max_actions_total=0, max_actions_per_minute=1).validate()
    with pytest.raises(ValueError):
        CCLimits(max_actions_total=1, max_actions_per_minute=0).validate()
    with pytest.raises(ValueError):
        CCLimits(max_actions_total=1, max_actions_per_minute=1, max_session_seconds=0).validate()

    # valid
    CCLimits(max_actions_total=1, max_actions_per_minute=1).validate()
    CCLimits(max_actions_total=1, max_actions_per_minute=1, max_session_seconds=10).validate()


def test_scope_validate_requires_tz_aware_and_expires_after_created() -> None:
    limits = CCLimits(max_actions_total=2, max_actions_per_minute=10)

    naive_created = datetime(2020, 1, 1)  # no tzinfo
    aware_expires = dt_utc(2020, 1, 2)

    scope = CCScope(
        scope_id="s1",
        created_at=naive_created,
        expires_at=aware_expires,
        target=CCTarget(app_name="x"),
        allowed_actions=frozenset({CCActionType.SCREENSHOT}),
        limits=limits,
    )
    with pytest.raises(ValueError):
        scope.validate()

    created = dt_utc(2020, 1, 2)
    expires = dt_utc(2020, 1, 2)  # equal -> invalid
    scope2 = CCScope(
        scope_id="s2",
        created_at=created,
        expires_at=expires,
        target=CCTarget(app_name="x"),
        allowed_actions=frozenset({CCActionType.SCREENSHOT}),
        limits=limits,
    )
    with pytest.raises(ValueError):
        scope2.validate()


def test_scope_is_expired_and_consume_action_limit() -> None:
    created = dt_utc(2020, 1, 1)
    expires = dt_utc(2020, 1, 1, 0, 0, 10)
    limits = CCLimits(max_actions_total=2, max_actions_per_minute=10)

    scope = CCScope(
        scope_id="scope-123",
        created_at=created,
        expires_at=expires,
        target=CCTarget(app_name="demo"),
        allowed_actions=frozenset({CCActionType.SCREENSHOT}),
        limits=limits,
    )
    scope.validate()

    now = created + timedelta(seconds=1)
    assert scope.is_expired(now=now) is False
    assert scope.remaining_actions() == 2

    scope.consume_action(now=now)
    assert scope.remaining_actions() == 1

    scope.consume_action(now=now + timedelta(seconds=1))
    assert scope.remaining_actions() == 0

    # next consume should fail-closed
    with pytest.raises(PermissionError):
        scope.consume_action(now=now + timedelta(seconds=2))

    # expired should be fail-closed
    assert scope.is_expired(now=expires) is True
    assert scope.can_consume_action(now=expires) is False
