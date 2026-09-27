from dataclasses import dataclass
from enum import Enum
class RecoveryAction(str,Enum): REOBSERVE="reobserve"; REFIND_TARGET="refind_target"; REFOCUS_WINDOW="refocus_window"; RETRY="retry"; ABORT="abort"
@dataclass(frozen=True)
class RecoveryDecision:
    action:RecoveryAction; reason:str; attempt:int
class RecoveryEngine:
    def __init__(self,*,max_attempts=2):
        if max_attempts<0:raise ValueError("max_attempts must be >= 0")
        self.max_attempts=max_attempts
    def decide(self,*,failure_reason,attempt):
        if attempt>=self.max_attempts:return RecoveryDecision(RecoveryAction.ABORT,"recovery_budget_exhausted",attempt)
        if "window" in failure_reason:return RecoveryDecision(RecoveryAction.REFOCUS_WINDOW,failure_reason,attempt)
        if "target" in failure_reason or "ground" in failure_reason:return RecoveryDecision(RecoveryAction.REFIND_TARGET,failure_reason,attempt)
        return RecoveryDecision(RecoveryAction.REOBSERVE,failure_reason,attempt)
