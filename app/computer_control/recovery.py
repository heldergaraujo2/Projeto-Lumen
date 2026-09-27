from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecoveryAction(str, Enum):
    REOBSERVE = "reobserve"
    REFIND_TARGET = "refind_target"
    REFOCUS_WINDOW = "refocus_window"
    RETRY = "retry"
    ABORT = "abort"


class FailureKind(str, Enum):
    TARGET = "target"
    WINDOW = "window"
    TRANSIENT = "transient"
    TIMEOUT = "timeout"
    SCOPE = "scope"
    PERMISSION = "permission"
    DRIVER = "driver"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    attempt: int
    failure_kind: FailureKind = FailureKind.UNKNOWN

    @property
    def terminal(self) -> bool:
        return self.action is RecoveryAction.ABORT


class RecoveryEngine:
    """Produces bounded recovery decisions only; it never executes or grants authority."""

    def __init__(self, *, max_attempts=2):
        if max_attempts < 0:
            raise ValueError("max_attempts must be >= 0")
        self.max_attempts = max_attempts

    @staticmethod
    def classify_failure(failure_reason: str) -> FailureKind:
        reason = (failure_reason or "").casefold()
        if any(x in reason for x in ("permission", "scope", "checkpoint", "denied")):
            return FailureKind.PERMISSION if "permission" in reason or "denied" in reason else FailureKind.SCOPE
        if any(x in reason for x in ("target", "ground")):
            return FailureKind.TARGET
        if "window" in reason or "focus" in reason:
            return FailureKind.WINDOW
        if "timeout" in reason:
            return FailureKind.TIMEOUT
        if any(x in reason for x in ("transient", "temporary", "busy")):
            return FailureKind.TRANSIENT
        if any(x in reason for x in ("driver", "execution_failed")):
            return FailureKind.DRIVER
        return FailureKind.UNKNOWN

    def decide(self, *, failure_reason, attempt):
        if attempt < 0:
            raise ValueError("attempt must be >= 0")
        kind = self.classify_failure(failure_reason)
        if kind in {FailureKind.PERMISSION, FailureKind.SCOPE}:
            return RecoveryDecision(RecoveryAction.ABORT, "security_failure_not_recoverable", attempt, kind)
        if attempt >= self.max_attempts:
            return RecoveryDecision(RecoveryAction.ABORT, "recovery_budget_exhausted", attempt, kind)
        if kind is FailureKind.WINDOW:
            return RecoveryDecision(RecoveryAction.REFOCUS_WINDOW, failure_reason, attempt, kind)
        if kind is FailureKind.TARGET:
            return RecoveryDecision(RecoveryAction.REFIND_TARGET, failure_reason, attempt, kind)
        if kind in {FailureKind.TRANSIENT, FailureKind.TIMEOUT}:
            return RecoveryDecision(RecoveryAction.RETRY, failure_reason, attempt, kind)
        return RecoveryDecision(RecoveryAction.REOBSERVE, failure_reason, attempt, kind)
