import pytest

from app.evolution.lab import EvolutionLab, LabChange, LabWorkspace
from app.evolution.models import Candidate, EvolutionState, Experiment


def test_workspace_isolated_under_evolution_lab():
    ws = LabWorkspace("ws-1", "EVOLUTION-000001", "evolution-lab/ws-1")
    ws.validate()
    assert not ws.stable_runtime


@pytest.mark.parametrize("root", ["/tmp/x", "../x", "app/evolution-lab", ".github/workflows"])
def test_workspace_rejects_escape_or_stable_locations(root):
    with pytest.raises(ValueError):
        LabWorkspace("ws-1", "EVOLUTION-000001", root).validate()


def test_change_cannot_target_stable_runtime():
    for path in ("app/foo.py", "tests/foo.py", ".github/workflows/x.yml", "../secret"):
        with pytest.raises(ValueError):
            LabChange(path, "modify").validate()


def test_change_accepts_isolated_relative_path():
    change = LabChange("src/module.py", "add", "experimental implementation")
    change.validate()


def test_lab_records_experiment_without_executing_it():
    lab = EvolutionLab()
    ws = lab.record_experiment(
        Experiment("EVOLUTION-000001", "grounding-test", "evolution-lab/ws-1")
    )
    assert lab.is_isolated(ws.workspace_id)
    assert lab.experiments.get("EVOLUTION-000001").state is EvolutionState.PROPOSED


def test_lab_records_changes():
    lab = EvolutionLab()
    ws = lab.create_workspace(evolution_id="EVOLUTION-000001", workspace_id="ws-1")
    lab.record_change(ws.workspace_id, LabChange("src/new.py", "add"))
    assert len(lab.changes("ws-1")) == 1


def test_candidate_must_match_workspace_evolution():
    lab = EvolutionLab()
    ws = lab.create_workspace(evolution_id="EVOLUTION-000001", workspace_id="ws-1")
    with pytest.raises(ValueError):
        lab.register_candidate(
            Candidate("C-2", "EVOLUTION-000002", "1"), workspace_id=ws.workspace_id
        )


def test_candidate_can_be_registered_in_own_workspace():
    lab = EvolutionLab()
    ws = lab.create_workspace(evolution_id="EVOLUTION-000001", workspace_id="ws-1")
    lab.register_candidate(Candidate("C-1", "EVOLUTION-000001", "1"), workspace_id=ws.workspace_id)
    assert lab.candidates.get("C-1").evolution_id == ws.evolution_id


def test_duplicate_workspace_and_candidate_are_rejected():
    lab = EvolutionLab()
    lab.create_workspace(evolution_id="EVOLUTION-000001", workspace_id="ws-1")
    with pytest.raises(ValueError):
        lab.create_workspace(evolution_id="EVOLUTION-000001", workspace_id="ws-1")
    lab.register_candidate(Candidate("C-1", "EVOLUTION-000001", "1"), workspace_id="ws-1")
    with pytest.raises(ValueError):
        lab.register_candidate(Candidate("C-1", "EVOLUTION-000001", "1"), workspace_id="ws-1")


def test_transition_uses_bounded_f12_lifecycle():
    lab = EvolutionLab()
    lab.record_experiment(Experiment("EVOLUTION-000001", "test", "evolution-lab/ws"))
    lab.transition("EVOLUTION-000001", EvolutionState.RESEARCHING)
    assert lab.experiments.get("EVOLUTION-000001").state is EvolutionState.RESEARCHING


def test_lab_has_no_execution_surface():
    lab = EvolutionLab()
    assert not hasattr(lab, "execute")
    assert not hasattr(lab, "run_driver")
    assert not hasattr(lab, "grant_permission")
