from .diagnostics import ImprovementOpportunity, ImprovementPlanner, ResearchEngine, ResearchEvidence, ResearchKind, ResearchQuery, ResearchReport, SelfDiagnostics
"""Lumen Evolution System — F12 foundation."""

from .lab import EvolutionLab, LabChange, LabWorkspace
from .engine import BenchmarkEngine, EvolutionEngine, HypothesisManager, ImprovementPlanner, RegressionDetector, SafetyValidator
from .models import *
from .registry import CandidateRegistry, CapabilityRegistry, EvolutionMemory, ExperimentManager, PromotionManager, RollbackManager
from .promotion import BenchmarkSuite, BuildEvidence, CandidateBenchmark, CandidateBuilder, PromotionAssessment, PromotionGate
from .continuous import ContinuousEvolutionMonitor, ContinuousEvolutionPlanner, EvolutionTrigger, MonitoringPolicy, MonitoringStatus, PostPromotionObservation, StabilityAssessment
from .intelligence_stack import AdapterKind, IntelligenceStack, IntelligenceStackEvolution, ModelProfile, ProviderProfile, RoutingDecision, StackAdaptation, StackEvidence, StackEvaluator, StackLayer, StackRequest
from .adaptation import AdaptationAssessment, AdaptationCandidate, AdaptationEvaluator, AdaptationEvidence, AdaptationExperiment, AdaptationKind, AdaptationSpec, DatasetSpec, ModelAdaptationLab
from .intelligence_lab import IntelligenceAssessment, IntelligenceBaseline, IntelligenceCapability, IntelligenceEvidenceLedger, IntelligenceFinding, IntelligenceHypothesis, IntelligenceOpportunity, IntelligenceResearch, IntelligenceTrack, LumenIntelligenceLab
from .self_optimizing import OptimizationAssessment, OptimizationDimension, OptimizationEvidence, OptimizationObjective, OptimizationPolicy, OptimizationRecommendation, SelfOptimizingIntelligence, StrategyVariant
from .provider_independence import IndependenceRequirement, ProviderCapabilityContract, ProviderCompatibility, ProviderFallbackPolicy, ProviderIndependenceAssessment, ProviderIndependenceLab, ProviderMigrationPlan
from .continuous_intelligence import ContinuousIntelligenceEvolution, ContinuousIntelligencePlan, IntelligenceCycle, IntelligenceCycleState, IntelligenceObservation, IntelligenceTrigger
from .orchestrator import EvolutionRuntimeOrchestrator, OrchestrationContext
from .closed_loop import ClosedLoopEvolution, ClosedLoopPlan, ClosedLoopRecord, ClosedLoopState, PersistentClosedLoopEvolution
from .autonomous_progress import ActionEvidence, AutonomousProgressController, EvolutionProgressState, ProgressDecision
from .cognitive_fusion import CapabilityGap, CognitiveFusion, Experience, EvolutionGovernor, EvolutionHypothesis, QuantumInspiredOptimizer, ResearchFinding, TemporalEventLearner, ToolCandidate, WorldFact
from .operational_brain import ActionOutcome, BrainDecision, BrainState, OperationalBrain
from .cognitive_runtime import CognitiveRuntime, CognitiveProvider, CognitiveToolExecutor, RuntimeCycle
from .autonomous_runtime import AutonomousMissionRuntime, MissionEnvironment

# Autonomous mission imports the tool/runtime stack, which in turn may import
# the evolution package. Keep this boundary lazy so importing an unrelated
# evolution primitive (for example StackLayer) cannot create a package-level
# circular import.
_AUTONOMOUS_MISSION_EXPORTS = {
    "AutonomousMissionEngine",
    "AutonomousMissionSupervisor",
    "AutonomousUnrealBroker",
    "MissionRecord",
    "MissionStore",
    "create_mission",
}

def __getattr__(name):
    if name in _AUTONOMOUS_MISSION_EXPORTS:
        from . import autonomous_mission
        value = getattr(autonomous_mission, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "EvolutionLab", "LabChange", "LabWorkspace",
    "BenchmarkEngine", "EvolutionEngine", "HypothesisManager",
    "ImprovementPlanner", "RegressionDetector", "SafetyValidator",
    "CapabilityRegistry", "CandidateRegistry", "EvolutionMemory",
    "ExperimentManager", "PromotionManager", "RollbackManager",
    "BenchmarkSuite", "BuildEvidence", "CandidateBenchmark", "CandidateBuilder",
    "PromotionAssessment", "PromotionGate",
    "ContinuousEvolutionMonitor", "ContinuousEvolutionPlanner", "EvolutionTrigger",
    "MonitoringPolicy", "MonitoringStatus", "PostPromotionObservation", "StabilityAssessment",
    "AdapterKind", "IntelligenceStack", "IntelligenceStackEvolution", "ModelProfile",
    "ProviderProfile", "RoutingDecision", "StackAdaptation", "StackEvidence",
    "StackEvaluator", "StackLayer", "StackRequest",
    "AdaptationAssessment", "AdaptationCandidate", "AdaptationEvaluator", "AdaptationEvidence",
    "AdaptationExperiment", "AdaptationKind", "AdaptationSpec", "DatasetSpec", "ModelAdaptationLab",
    "IntelligenceAssessment", "IntelligenceBaseline", "IntelligenceCapability",
    "IntelligenceEvidenceLedger", "IntelligenceFinding", "IntelligenceHypothesis",
    "IntelligenceOpportunity", "IntelligenceResearch", "IntelligenceTrack", "LumenIntelligenceLab",
    "OptimizationAssessment", "OptimizationDimension", "OptimizationEvidence",
    "OptimizationObjective", "OptimizationPolicy", "OptimizationRecommendation",
    "SelfOptimizingIntelligence", "StrategyVariant",
    "IndependenceRequirement", "ProviderCapabilityContract", "ProviderCompatibility",
    "ProviderFallbackPolicy", "ProviderIndependenceAssessment", "ProviderIndependenceLab",
    "ProviderMigrationPlan",
    "ContinuousIntelligenceEvolution", "ContinuousIntelligencePlan", "IntelligenceCycle",
    "IntelligenceCycleState", "IntelligenceObservation", "IntelligenceTrigger",
    "EvolutionRuntimeOrchestrator", "OrchestrationContext",
    "ClosedLoopEvolution", "ClosedLoopPlan", "ClosedLoopRecord", "ClosedLoopState",
    "PersistentClosedLoopEvolution",
    "AutonomousProgressController", "EvolutionProgressState", "ProgressDecision", "ActionEvidence",
    "CognitiveFusion", "CapabilityGap", "Experience", "EvolutionGovernor",
    "EvolutionHypothesis", "QuantumInspiredOptimizer", "ResearchFinding",
    "TemporalEventLearner", "ToolCandidate", "WorldFact",
    "OperationalBrain", "BrainState", "BrainDecision", "ActionOutcome",
    "CognitiveRuntime", "CognitiveProvider", "CognitiveToolExecutor", "RuntimeCycle",
    "AutonomousMissionRuntime", "MissionEnvironment",
    "AutonomousMissionEngine", "AutonomousMissionSupervisor", "AutonomousUnrealBroker",
    "MissionRecord", "MissionStore", "create_mission",
]
