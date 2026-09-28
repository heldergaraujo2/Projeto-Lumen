"""Computer Intelligence and Computer Control core."""
from .api import CCActionType,CCTarget,ScreenRegion,ScreenshotInfo,WindowInfo
from .actions import CCActionRequest
from .grounding import GroundedTarget,GroundingEngine,GroundingSource,TargetResolver
from .recovery import RecoveryEngine
from .scopes import CCLimits,CCScope
from .service import CCExecutionResult,ComputerControlService
from .windows_driver import WindowsComputerControlDriver,WindowsComputerControlError
from .verification import ComputerVerifier,VerificationResult,VerificationStatus
from .vision_grounding import VisionGroundingPipeline,VisionGroundingResult
from .vision import JsonVisionProvider,OllamaVisionProvider,VisionElement,VisionObservation,VisionProvider,VisionProviderManager,VisionRequest
from .autonomous_agent import ComputerAgentLimits,ComputerAgentState,ComputerAgentStep,ComputerAgentRun,ComputerPlan,VisionComputerAgent
__all__=["CCActionType","CCTarget","ScreenRegion","ScreenshotInfo","WindowInfo","CCActionRequest","GroundedTarget","GroundingEngine","GroundingSource","TargetResolver","RecoveryEngine","CCLimits","CCScope","CCExecutionResult","ComputerControlService","WindowsComputerControlDriver","WindowsComputerControlError","ComputerVerifier","VerificationResult","VerificationStatus","JsonVisionProvider","OllamaVisionProvider","VisionElement","VisionObservation","VisionProvider","VisionProviderManager","VisionRequest","VisionGroundingPipeline","VisionGroundingResult","ComputerAgentLimits","ComputerAgentState","ComputerAgentStep","ComputerAgentRun","ComputerPlan","VisionComputerAgent"]
