from .diagnostics import ImprovementOpportunity, ImprovementPlanner, ResearchEngine, ResearchEvidence, ResearchKind, ResearchQuery, ResearchReport, SelfDiagnostics
"""Lumen Evolution System — F12 foundation.

Contracts and registries only. F12 does not execute experiments, mutate runtime
security, or promote code automatically.
"""

from .lab import EvolutionLab, LabChange, LabWorkspace
from .engine import (
    BenchmarkEngine, EvolutionEngine, HypothesisManager, ImprovementPlanner,
    RegressionDetector, SafetyValidator,
)
from .models import *
from .registry import CandidateRegistry, CapabilityRegistry, EvolutionMemory, ExperimentManager, PromotionManager, RollbackManager

__all__ = [
    "EvolutionLab", "LabChange", "LabWorkspace", "BenchmarkEngine", "EvolutionEngine", "HypothesisManager", "ImprovementPlanner",
    "RegressionDetector", "SafetyValidator", "CapabilityRegistry", "CandidateRegistry",
    "EvolutionMemory", "ExperimentManager", "PromotionManager", "RollbackManager",
]

from .promotion import BenchmarkSuite, BuildEvidence, CandidateBenchmark, CandidateBuilder, PromotionAssessment, PromotionGate

from .continuous import (
    ContinuousEvolutionMonitor, ContinuousEvolutionPlanner, EvolutionTrigger,
    MonitoringPolicy, MonitoringStatus, PostPromotionObservation, StabilityAssessment,
)

from .intelligence_stack import (AdapterKind, IntelligenceStack, IntelligenceStackEvolution, ModelProfile, ProviderProfile, RoutingDecision, StackAdaptation, StackEvidence, StackEvaluator, StackLayer, StackRequest)


from .adaptation import (
    AdaptationAssessment, AdaptationCandidate, AdaptationEvaluator, AdaptationEvidence,
    AdaptationExperiment, AdaptationKind, AdaptationSpec, DatasetSpec, ModelAdaptationLab,
)

from .intelligence_lab import (
    IntelligenceAssessment, IntelligenceBaseline, IntelligenceCapability,
    IntelligenceEvidenceLedger, IntelligenceFinding, IntelligenceHypothesis,
    IntelligenceOpportunity, IntelligenceResearch, IntelligenceTrack,
    LumenIntelligenceLab,
)

from .self_optimizing import (
    OptimizationAssessment, OptimizationDimension, OptimizationEvidence,
    OptimizationObjective, OptimizationPolicy, OptimizationRecommendation,
    SelfOptimizingIntelligence, StrategyVariant,
)

from .provider_independence import (
    IndependenceRequirement, ProviderCapabilityContract, ProviderCompatibility,
    ProviderFallbackPolicy, ProviderIndependenceAssessment, ProviderIndependenceLab,
    ProviderMigrationPlan,
)

from .continuous_intelligence import (
    ContinuousIntelligenceEvolution, ContinuousIntelligencePlan,
    IntelligenceCycle, IntelligenceCycleState, IntelligenceObservation,
    IntelligenceTrigger,
)

from .orchestrator import EvolutionRuntimeOrchestrator, OrchestrationContext

from .closed_loop import ClosedLoopEvolution, ClosedLoopPlan, ClosedLoopRecord, ClosedLoopState, PersistentClosedLoopEvolution

from .autonomous_progress import ActionEvidence, AutonomousProgressController, EvolutionProgressState, ProgressDecision

from .cognitive_fusion import (
    CapabilityGap, CognitiveFusion, Experience, EvolutionGovernor,
    EvolutionHypothesis, QuantumInspiredOptimizer, ResearchFinding,
    TemporalEventLearner, ToolCandidate, WorldFact,
)
from .operational_brain import ActionOutcome, BrainDecision, BrainState, OperationalBrain
