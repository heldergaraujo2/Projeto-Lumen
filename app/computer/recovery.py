from __future__ import annotations

from app.computer_control.recovery import FailureKind, RecoveryAction, RecoveryDecision, RecoveryEngine


class IntelligenceRecovery:
    """Bounded recovery decisions; never grants permission or widens scope."""

    def __init__(self, *, max_attempts: int = 2):
        self.engine = RecoveryEngine(max_attempts=max_attempts)

    def classify(self, failure_reason: str) -> FailureKind:
        return self.engine.classify_failure(failure_reason)

    def decide(self, *, failure_reason: str, attempt: int) -> RecoveryDecision:
        return self.engine.decide(failure_reason=failure_reason, attempt=attempt)

    @staticmethod
    def safe_for_execution(decision: RecoveryDecision) -> bool:
        return decision.action is not RecoveryAction.ABORT and decision.failure_kind not in {
            FailureKind.PERMISSION,
            FailureKind.SCOPE,
        }
