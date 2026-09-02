from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import FrozenSet, Optional

from .api import CCActionType, CCTarget


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CCLimits:
    """Quantitative limits for a CC scope (fail-closed).

    All non-optional limits must be > 0.
    """

    max_actions_total: int
    max_actions_per_minute: int
    max_session_seconds: Optional[int] = None

    def validate(self) -> None:
        if self.max_actions_total <= 0:
            raise ValueError("max_actions_total must be > 0")
        if self.max_actions_per_minute <= 0:
            raise ValueError("max_actions_per_minute must be > 0")
        if self.max_session_seconds is not None and self.max_session_seconds <= 0:
            raise ValueError("max_session_seconds must be > 0 when provided")


@dataclass
class CCScope:
    """Consent object granting a narrow CC capability set over a target.

    This is a pure model. Granting/revoking is handled elsewhere.
    """

    scope_id: str
    created_at: datetime
    expires_at: datetime
    target: CCTarget
    allowed_actions: FrozenSet[CCActionType]
    limits: CCLimits

    # Minimal accounting for MVP; more sophisticated rate-limit windows can come later.
    actions_used: int = 0
    first_action_at: Optional[datetime] = None
    last_action_at: Optional[datetime] = None

    def validate(self) -> None:
        if not self.scope_id.strip():
            raise ValueError("scope_id must be non-empty")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("created_at and expires_at must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if not self.allowed_actions:
            raise ValueError("allowed_actions must be non-empty")
        self.limits.validate()

    def is_expired(self, *, now: Optional[datetime] = None) -> bool:
        n = now or _now_utc()
        return n >= self.expires_at

    def remaining_actions(self) -> int:
        return max(0, self.limits.max_actions_total - self.actions_used)

    def can_consume_action(self, *, now: Optional[datetime] = None) -> bool:
        # Fail-closed: if expired or at/over limit, return False.
        n = now or _now_utc()
        if self.is_expired(now=n):
            return False
        if self.actions_used >= self.limits.max_actions_total:
            return False
        # MVP: we do not implement rolling per-minute window yet; keep field for later.
        return True

    def consume_action(self, *, now: Optional[datetime] = None) -> None:
        n = now or _now_utc()
        if not self.can_consume_action(now=n):
            raise PermissionError("scope cannot consume action (expired or limit exceeded)")
        self.actions_used += 1
        if self.first_action_at is None:
            self.first_action_at = n
        self.last_action_at = n
