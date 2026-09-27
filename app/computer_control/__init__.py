"""Computer Intelligence and Computer Control core."""
from .api import CCActionType,CCTarget,ScreenRegion,ScreenshotInfo,WindowInfo
from .actions import CCActionRequest
from .grounding import GroundedTarget,GroundingEngine,GroundingSource,TargetResolver
from .recovery import RecoveryEngine
from .scopes import CCLimits,CCScope
from .service import CCExecutionResult,ComputerControlService
from .verification import ComputerVerifier,VerificationResult,VerificationStatus
from .vision import OllamaVisionProvider,VisionElement,VisionObservation,VisionProvider,VisionRequest
__all__=["CCActionType","CCTarget","ScreenRegion","ScreenshotInfo","WindowInfo","CCActionRequest","GroundedTarget","GroundingEngine","GroundingSource","TargetResolver","RecoveryEngine","CCLimits","CCScope","CCExecutionResult","ComputerControlService","ComputerVerifier","VerificationResult","VerificationStatus","OllamaVisionProvider","VisionElement","VisionObservation","VisionProvider","VisionRequest"]
