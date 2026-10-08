from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .api import CCActionType


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_summary(value: Optional[str], *, max_len: int = 200) -> Optional[str]:
    """Sanitize user/system-provided target summaries for metadata-only audit.

    This does NOT attempt to remove sensitive content beyond basic normalization.
    The key guarantee is: no binary payloads and no newline/control characters.
    """
    if value is None:
        return None
    v = " ".join(str(value).split())
    if len(v) > max_len:
        v = v[: max_len - 1] + "…"
    return v


@dataclass(frozen=True)
class CCAuditEvent:
    """Computer Control audit event (metadata-only).

    Non-negotiable: this object must never contain screenshot bytes or typed text.
    Any artifact must be referenced by artifact_ref only.
    """

    operation: str
    timestamp: datetime

    scope_id: Optional[str] = None
    action_type: Optional[CCActionType] = None
    target_summary: Optional[str] = None

    decision: Optional[str] = None  # "allowed" | "denied"
    denied_reason: Optional[str] = None

    duration_ms: Optional[int] = None
    artifact_ref: Optional[str] = None

    def validate(self) -> None:
        if not self.operation or not self.operation.strip():
            raise ValueError("operation must be non-empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.decision is not None and self.decision not in ("allowed", "denied"):
            raise ValueError("decision must be 'allowed' or 'denied' when provided")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0 when provided")
        # Normalize target_summary contract: metadata-only, sanitized, short.
        _ = sanitize_summary(self.target_summary)

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (still metadata-only)."""
        self.validate()
        return {
            "operation": self.operation,
            "timestamp": self.timestamp.isoformat(),
            "scope_id": self.scope_id,
            "action_type": (self.action_type.value if self.action_type else None),
            "target_summary": sanitize_summary(self.target_summary),
            "decision": self.decision,
            "denied_reason": self.denied_reason,
            "duration_ms": self.duration_ms,
            "artifact_ref": self.artifact_ref,
        }


def make_cc_audit_event(
    *,
    operation: str,
    scope_id: Optional[str] = None,
    action_type: Optional[CCActionType] = None,
    target_summary: Optional[str] = None,
    decision: Optional[str] = None,
    denied_reason: Optional[str] = None,
    duration_ms: Optional[int] = None,
    artifact_ref: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> CCAuditEvent:
    ev = CCAuditEvent(
        operation=operation,
        timestamp=timestamp or now_utc(),
        scope_id=scope_id,
        action_type=action_type,
        target_summary=sanitize_summary(target_summary),
        decision=decision,
        denied_reason=denied_reason,
        duration_ms=duration_ms,
        artifact_ref=artifact_ref,
    )
    ev.validate()
    return ev
