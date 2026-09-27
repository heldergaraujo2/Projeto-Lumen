from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from threading import RLock

from .engine import BenchmarkEngine, RegressionDetector, SafetyValidator
from .lab import EvolutionLab, LabWorkspace
from .models import BenchmarkResult, Candidate, EvolutionRisk, EvolutionState
from .registry import CandidateRegistry, ExperimentManager


class AdaptationKind(str, Enum):
    LORA = "lora"
    FINE_TUNING = "fine_tuning"
    DISTILLATION = "distillation"
    PRUNING = "pruning"
    QUANTIZATION = "quantization"
    DATASET_CURATION = "dataset_curation"
    SYNTHETIC_DATA = "synthetic_data"
    CURRICULUM = "curriculum"
    TOOL_USE = "tool_use"
    DOMAIN_ADAPTATION = "domain_adaptation"
    INFERENCE_OPTIMIZATION = "inference_optimization"


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    version: str
    samples: int
    train_samples: int = 0
    validation_samples: int = 0
    test_samples: int = 0
    source: str = ""
    content_hash: str = ""

    def validate(self) -> None:
        if not self.dataset_id.strip() or not self.version.strip():
            raise ValueError("dataset identity is required")
        if self.samples < 1:
            raise ValueError("dataset must contain at least one sample")
        if min(self.train_samples, self.validation_samples, self.test_samples) < 0:
            raise ValueError("dataset split sizes must be non-negative")
        if self.train_samples + self.validation_samples + self.test_samples > self.samples:
            raise ValueError("dataset splits exceed total sample count")


@dataclass(frozen=True)
class AdaptationSpec:
    adaptation_id: str
    evolution_id: str
    base_provider: str
    base_model: str
    target_model: str
    kind: AdaptationKind
    changed_layers: tuple[str, ...]
    objective_metric: str
    rationale: str
    workspace_id: str
    risk: EvolutionRisk = EvolutionRisk.MEDIUM
    seed: int = 0
    configuration: tuple[tuple[str, str], ...] = ()

    def validate(self) -> None:
        if not self.adaptation_id.startswith("ADAPTATION-"):
            raise ValueError("invalid adaptation identifier")
        if not self.evolution_id.startswith("EVOLUTION-"):
            raise ValueError("invalid evolution identifier")
        if not self.base_provider.strip() or not self.base_model.strip() or not self.target_model.strip():
            raise ValueError("base and target model identities are required")
        if not self.changed_layers:
            raise ValueError("adaptation must declare changed layers")
        if not self.objective_metric.strip() or not self.rationale.strip():
            raise ValueError("adaptation objective and rationale are required")
        if not self.workspace_id.strip():
            raise ValueError("isolated workspace is required")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")


@dataclass(frozen=True)
class AdaptationExperiment:
    experiment_id: str
    adaptation: AdaptationSpec
    dataset: DatasetSpec
    control_configuration: tuple[tuple[str, str], ...] = ()
    max_samples: int = 0
    max_steps: int = 0

    def validate(self) -> None:
        if not self.experiment_id.strip():
            raise ValueError("experiment identity is required")
        self.adaptation.validate()
        self.dataset.validate()
        if self.max_samples < 0 or self.max_steps < 0:
            raise ValueError("experiment limits must be non-negative")


@dataclass(frozen=True)
class AdaptationEvidence:
    adaptation_id: str
    experiment_id: str
    provider_id: str
    base_model: str
    candidate_model: str
    metric: str
    baseline: float
    candidate: float
    sample_size: int
    seed: int
    reproducibility_key: str
    artifact_references: tuple[str, ...] = ()
    test_references: tuple[str, ...] = ()

    @property
    def delta(self) -> float:
        return self.candidate - self.baseline

    def validate(self) -> None:
        if not self.adaptation_id.startswith("ADAPTATION-") or not self.experiment_id.strip():
            raise ValueError("adaptation evidence identity is required")
        if not self.provider_id.strip() or not self.base_model.strip() or not self.candidate_model.strip():
            raise ValueError("adaptation evidence model identity is required")
        if not self.metric.strip() or not 0.0 <= self.baseline <= 1.0 or not 0.0 <= self.candidate <= 1.0:
            raise ValueError("adaptation evidence metric must be in [0, 1]")
        if self.sample_size < 1 or self.seed < 0:
            raise ValueError("invalid adaptation evidence sample or seed")
        if not self.reproducibility_key.strip():
            raise ValueError("reproducibility key is required")
        if not self.artifact_references or not self.test_references:
            raise ValueError("adaptation evidence requires artifacts and tests")


@dataclass(frozen=True)
class AdaptationCandidate:
    candidate_id: str
    adaptation_id: str
    evolution_id: str
    provider_id: str
    base_model: str
    candidate_model: str
    version: str
    workspace_id: str
    manifest_digest: str
    artifact_references: tuple[str, ...]
    isolated: bool = True

    def validate(self) -> None:
        if not self.candidate_id.strip() or not self.adaptation_id.startswith("ADAPTATION-"):
            raise ValueError("invalid adaptation candidate identity")
        if not self.evolution_id.startswith("EVOLUTION-"):
            raise ValueError("invalid evolution identifier")
        if not self.provider_id.strip() or not self.base_model.strip() or not self.candidate_model.strip():
            raise ValueError("candidate model identity is required")
        if not self.version.strip() or not self.workspace_id.strip() or not self.manifest_digest.strip():
            raise ValueError("candidate manifest identity is required")
        if not self.artifact_references:
            raise ValueError("candidate must reference artifacts")
        if not self.isolated:
            raise ValueError("adaptation candidate must remain isolated")

    def as_evolution_candidate(self) -> Candidate:
        self.validate()
        return Candidate(
            self.candidate_id, self.evolution_id, self.version,
            self.artifact_references, EvolutionState.EXPERIMENTAL,
        )


@dataclass(frozen=True)
class AdaptationAssessment:
    candidate_id: str
    evidence: tuple[AdaptationEvidence, ...]
    benchmarks: tuple[BenchmarkResult, ...]
    regressed: bool
    safety_passed: bool
    human_approval_required: bool
    eligible: bool
    reasons: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.candidate_id.strip() or not self.evidence or not self.benchmarks:
            raise ValueError("adaptation assessment requires evidence and benchmarks")
        if any(item.candidate_id != self.candidate_id for item in self.benchmarks):
            raise ValueError("benchmark belongs to another candidate")


class AdaptationEvaluator:
    """Validates caller-supplied adaptation evidence; it never invokes a model."""

    def compare(self, left: AdaptationEvidence, right: AdaptationEvidence) -> int:
        left.validate()
        right.validate()
        if (
            left.metric != right.metric
            or left.experiment_id != right.experiment_id
            or left.base_model != right.base_model
        ):
            raise ValueError("evidence must share experiment, metric and base model")
        if left.seed != right.seed:
            raise ValueError("evidence comparison requires the same seed")
        return (left.candidate > right.candidate) - (left.candidate < right.candidate)

    def reproducibility_digest(self, evidence: AdaptationEvidence) -> str:
        evidence.validate()
        payload = {
            "adaptation_id": evidence.adaptation_id,
            "experiment_id": evidence.experiment_id,
            "provider_id": evidence.provider_id,
            "base_model": evidence.base_model,
            "candidate_model": evidence.candidate_model,
            "metric": evidence.metric,
            "baseline": evidence.baseline,
            "candidate": evidence.candidate,
            "sample_size": evidence.sample_size,
            "seed": evidence.seed,
            "reproducibility_key": evidence.reproducibility_key,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


class ModelAdaptationLab:
    """F18 isolated laboratory; records evidence but never executes models."""

    def __init__(
        self,
        *,
        evolution_lab: EvolutionLab | None = None,
        experiments: ExperimentManager | None = None,
        candidates: CandidateRegistry | None = None,
        benchmark: BenchmarkEngine | None = None,
        regression: RegressionDetector | None = None,
        safety: SafetyValidator | None = None,
    ) -> None:
        self.evolution_lab = evolution_lab or EvolutionLab(
            experiments=experiments, candidates=candidates
        )
        self.experiments = self.evolution_lab.experiments
        self.candidates = self.evolution_lab.candidates
        self.benchmark_engine = benchmark or BenchmarkEngine()
        self.regression = regression or RegressionDetector()
        self.safety = safety or SafetyValidator()
        self._counter = 0
        self._lock = RLock()
        self._experiments: dict[str, AdaptationExperiment] = {}
        self._evidence: dict[str, list[AdaptationEvidence]] = {}
        self._workspaces: dict[str, LabWorkspace] = {}

    def next_adaptation_id(self) -> str:
        with self._lock:
            self._counter += 1
            return f"ADAPTATION-{self._counter:06d}"

    def create_workspace(self, *, evolution_id: str, workspace_id: str) -> LabWorkspace:
        workspace = self.evolution_lab.create_workspace(
            evolution_id=evolution_id, workspace_id=workspace_id
        )
        self._workspaces[workspace_id] = workspace
        return workspace

    def design(self, experiment: AdaptationExperiment) -> LabWorkspace:
        experiment.validate()
        workspace = self._workspaces.get(experiment.adaptation.workspace_id)
        if workspace is None:
            raise KeyError("adaptation workspace does not exist")
        if workspace.evolution_id != experiment.adaptation.evolution_id:
            raise ValueError("workspace does not belong to evolution")
        if experiment.experiment_id in self._experiments:
            raise ValueError("adaptation experiment already exists")
        self._experiments[experiment.experiment_id] = experiment
        self._evidence[experiment.experiment_id] = []
        from .models import Experiment
        self.experiments.create(
            Experiment(
                experiment.adaptation.evolution_id,
                experiment.experiment_id,
                workspace.root,
                EvolutionState.PROPOSED,
                tuple(f"{k}={v}" for k, v in experiment.adaptation.configuration),
            )
        )
        return workspace

    def record_evidence(self, evidence: AdaptationEvidence) -> None:
        evidence.validate()
        experiment = self._experiments.get(evidence.experiment_id)
        if experiment is None:
            raise KeyError("unknown adaptation experiment")
        if experiment.adaptation.adaptation_id != evidence.adaptation_id:
            raise ValueError("evidence belongs to another adaptation")
        if evidence.base_model != experiment.adaptation.base_model:
            raise ValueError("evidence base model does not match experiment")
        if evidence.seed != experiment.adaptation.seed:
            raise ValueError("evidence seed does not match experiment")
        self._evidence[evidence.experiment_id].append(evidence)

    def evidence(self, experiment_id: str) -> tuple[AdaptationEvidence, ...]:
        if experiment_id not in self._experiments:
            raise KeyError("unknown adaptation experiment")
        return tuple(self._evidence[experiment_id])

    def register_candidate(self, candidate: AdaptationCandidate) -> Candidate:
        candidate.validate()
        experiment = next(
            (
                item for item in self._experiments.values()
                if item.adaptation.adaptation_id == candidate.adaptation_id
            ),
            None,
        )
        if experiment is None or experiment.adaptation.evolution_id != candidate.evolution_id:
            raise ValueError("candidate does not match a known adaptation")
        if candidate.workspace_id != experiment.adaptation.workspace_id:
            raise ValueError("candidate workspace does not match experiment")
        if not self.evidence(experiment.experiment_id):
            raise ValueError("candidate requires adaptation evidence")
        result = candidate.as_evolution_candidate()
        self.candidates.register(result)
        return result

    def benchmark(
        self,
        candidate: AdaptationCandidate,
        *,
        metric: str,
        baseline: float,
        candidate_score: float,
        sample_size: int,
        evidence: tuple[str, ...],
    ) -> BenchmarkResult:
        candidate.validate()
        return self.benchmark_engine.compare(
            candidate_id=candidate.candidate_id,
            metric=metric,
            baseline=baseline,
            candidate=candidate_score,
            sample_size=sample_size,
            evidence=evidence,
        )

    def assess(
        self,
        candidate: AdaptationCandidate,
        *,
        benchmarks: tuple[BenchmarkResult, ...],
        risk: EvolutionRisk | None = None,
        changed_components: tuple[str, ...] = (),
        human_approved: bool = False,
        tolerance: float = 0.0,
    ) -> AdaptationAssessment:
        candidate.validate()
        matching = [
            item
            for experiment in self._experiments.values()
            if experiment.adaptation.adaptation_id == candidate.adaptation_id
            for item in self._evidence[experiment.experiment_id]
        ]
        if not matching:
            raise ValueError("candidate requires adaptation evidence")
        if not benchmarks:
            raise ValueError("benchmarks are required")
        for item in benchmarks:
            item.validate()
            if item.candidate_id != candidate.candidate_id:
                raise ValueError("benchmark belongs to another candidate")
        report = self.regression.detect(
            candidate_id=candidate.candidate_id,
            benchmarks=benchmarks,
            tolerance=tolerance,
        )
        safety = self.safety.review(
            candidate.as_evolution_candidate(),
            changed_components=changed_components,
            risk=risk or EvolutionRisk.MEDIUM,
            human_approved=human_approved,
        )
        reasons: list[str] = []
        if report.regressed:
            reasons.append("benchmark regression detected")
        if not safety.passed:
            reasons.append("security review failed")
        eligible = not reasons
        return AdaptationAssessment(
            candidate.candidate_id, tuple(matching), tuple(benchmarks),
            report.regressed, safety.passed, safety.human_approval_required,
            eligible, tuple(reasons),
        )
