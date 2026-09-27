from __future__ import annotations

from app.computer_control.recovery import RecoveryAction, RecoveryDecision, RecoveryEngine


class IntelligenceRecovery:
    """Bounded recovery; it never grants permission or widens scope."""

    def __init__(self, *, max_attempts: int = 2):
        self.engine = RecoveryEngine(max_attempts=max_attempts)

    def decide(self, *, failure_reason: str, attempt: int) -> RecoveryDecision:
        return self.engine.decide(failure_reason=failure_reason, attempt=attempt)
