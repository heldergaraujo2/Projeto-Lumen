from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .api import CCActionType
from .scopes import CCScope


@dataclass(frozen=True)
class CCDecision:
    allowed: bool
    reason: str
    scope_id: Optional[str] = None


def evaluate_cc_action(
    *,
    has_computer_control_permission: bool,
    scope: Optional[CCScope],
    action: CCActionType,
    now: Optional[datetime] = None,
) -> CCDecision:
    """Pure policy evaluation for CC actions (fail-closed).

    This function does NOT touch OS, tools, or PermissionManager.
    It is designed for unit testing with FakeDriver and for wiring in CC-3 tools.
    """
    if not has_computer_control_permission:
        return CCDecision(allowed=False, reason="denied_no_permission")

    if scope is None:
        return CCDecision(allowed=False, reason="denied_no_scope")

    try:
        scope.validate()
    except Exception:
        return CCDecision(allowed=False, reason="denied_invalid_scope", scope_id=scope.scope_id)

    if scope.is_expired(now=now):
        return CCDecision(allowed=False, reason="denied_scope_expired", scope_id=scope.scope_id)

    if action not in scope.allowed_actions:
        return CCDecision(allowed=False, reason="denied_action_not_allowed", scope_id=scope.scope_id)

    if not scope.can_consume_action(now=now):
        return CCDecision(allowed=False, reason="denied_scope_limit_exceeded", scope_id=scope.scope_id)

    return CCDecision(allowed=True, reason="allowed", scope_id=scope.scope_id)
