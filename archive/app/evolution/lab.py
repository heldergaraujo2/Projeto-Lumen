from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from threading import RLock

from .models import Candidate, EvolutionRisk, EvolutionState, Experiment
from .registry import CandidateRegistry, ExperimentManager


@dataclass(frozen=True)
class LabWorkspace:
    workspace_id: str
    evolution_id: str
    root: str
    stable_runtime: bool = False

    def validate(self) -> None:
        if not self.workspace_id.strip() or not self.evolution_id.startswith("EVOLUTION-"):
            raise ValueError("invalid laboratory workspace")
        if self.stable_runtime:
            raise ValueError("experimental workspace cannot be the stable runtime")
        path = PurePosixPath(self.root)
        if not path.parts or path.parts[0] != "evolution-lab":
            raise ValueError("laboratory workspace must be isolated under evolution-lab")


@dataclass(frozen=True)
class LabChange:
    path: str
    operation: str
    description: str = ""

    def validate(self) -> None:
        p = PurePosixPath(self.path)
        if not self.path.strip() or p.is_absolute() or ".." in p.parts:
            raise ValueError("laboratory change path escapes workspace")
        if p.parts and p.parts[0] in {"app", "tests", ".github"}:
            raise ValueError("laboratory change cannot target stable runtime paths")


class EvolutionLab:
    """Isolated F13 laboratory. It records and validates work; it never executes it."""

    def __init__(self, experiments: ExperimentManager | None = None,
                 candidates: CandidateRegistry | None = None) -> None:
        self.experiments = experiments or ExperimentManager()
        self.candidates = candidates or CandidateRegistry()
        self._workspaces: dict[str, LabWorkspace] = {}
        self._changes: dict[str, list[LabChange]] = {}
        self._lock = RLock()

    def create_workspace(self, *, evolution_id: str, workspace_id: str) -> LabWorkspace:
        workspace = LabWorkspace(workspace_id, evolution_id, f"evolution-lab/{workspace_id}")
        workspace.validate()
        with self._lock:
            if workspace_id in self._workspaces:
                raise ValueError("laboratory workspace already exists")
            self._workspaces[workspace_id] = workspace
            self._changes[workspace_id] = []
        return workspace

    def record_experiment(self, experiment: Experiment) -> LabWorkspace:
        experiment.validate()
        workspace = LabWorkspace(
            f"ws-{experiment.evolution_id}", experiment.evolution_id, experiment.workspace
        )
        workspace.validate()
        self.experiments.create(experiment)
        with self._lock:
            self._workspaces[workspace.workspace_id] = workspace
            self._changes.setdefault(workspace.workspace_id, [])
        return workspace

    def record_change(self, workspace_id: str, change: LabChange) -> None:
        change.validate()
        with self._lock:
            if workspace_id not in self._workspaces:
                raise KeyError("unknown laboratory workspace")
            self._changes[workspace_id].append(change)

    def changes(self, workspace_id: str) -> tuple[LabChange, ...]:
        with self._lock:
            if workspace_id not in self._workspaces:
                raise KeyError("unknown laboratory workspace")
            return tuple(self._changes[workspace_id])

    def register_candidate(self, candidate: Candidate, *, workspace_id: str) -> None:
        candidate.validate()
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            if workspace is None:
                raise KeyError("unknown laboratory workspace")
            if workspace.evolution_id != candidate.evolution_id:
                raise ValueError("candidate does not belong to workspace evolution")
        self.candidates.register(candidate)

    def is_isolated(self, workspace_id: str) -> bool:
        workspace = self._workspaces.get(workspace_id)
        return workspace is not None and not workspace.stable_runtime

    def transition(self, evolution_id: str, state: EvolutionState):
        return self.experiments.transition(evolution_id, state)
