from dataclasses import dataclass
from enum import Enum
class VerificationStatus(str,Enum): VERIFIED="verified"; FAILED="failed"; INCONCLUSIVE="inconclusive"
@dataclass(frozen=True)
class VerificationResult:
    status:VerificationStatus; reason:str; evidence:tuple[str,...]=()
class ComputerVerifier:
    def verify_target_visible(self,*,found,expected_label):
        return VerificationResult(VerificationStatus.VERIFIED if found else VerificationStatus.FAILED,"target_visible" if found else "target_not_visible",(expected_label,))
    def verify_window(self,*,focused,expected):
        return VerificationResult(VerificationStatus.VERIFIED if focused else VerificationStatus.FAILED,"window_focused" if focused else "window_not_focused",(expected,))
    def require_verified(self,result):
        if result.status is not VerificationStatus.VERIFIED:raise RuntimeError("computer action not verified: "+result.reason)
