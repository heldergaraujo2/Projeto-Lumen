import json
import pytest
from app.evolution.autonomous_progress import AutonomousProgressController, EvolutionProgressState

def test_starts_empty_and_persists(tmp_path):
    p = tmp_path / "progress.json"
    c = AutonomousProgressController(p, "M")
    c.record(action="list_toolsets", result="2", new_information=True)
    r = AutonomousProgressController(p, "M")
    assert r.state.progress_epoch == 1
    assert r.state.last_action == "list_toolsets"

def test_fingerprint_is_deterministic():
    a = AutonomousProgressController.fingerprint("research", {"q": "x", "n": 1})
    b = AutonomousProgressController.fingerprint("research", {"n": 1, "q": "x"})
    assert a == b and len(a) == 64

def test_repeat_limit(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M", repeat_limit=2)
    fp = c.fingerprint("list_toolsets", {"scope": "unreal"})
    assert c.admit("list_toolsets", fp)
    c.record(action="list_toolsets", fingerprint=fp)
    assert c.admit("list_toolsets", fp)
    c.record(action="list_toolsets", fingerprint=fp)
    assert not c.admit("list_toolsets", fp)

def test_different_fingerprint_is_new_work(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M", repeat_limit=1)
    a = c.fingerprint("research", {"q": "a"})
    b = c.fingerprint("research", {"q": "b"})
    c.record(action="research", fingerprint=a)
    assert not c.admit("research", a)
    assert c.admit("research", b)

def test_research_moves_to_observation(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M")
    c.record(action="research", new_information=True, research_finding="f1")
    d = c.recommend(("research", "observe_unreal"), context={"can_observe": True})
    assert d.action == "observe_unreal"

def test_toolset_discovery_moves_to_description(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M")
    c.record(action="list_toolsets", new_information=True)
    d = c.recommend(("list_toolsets", "describe_toolset"), context={"toolsets": ("Slate", "Assets")})
    assert d.action == "describe_toolset"

def test_description_moves_to_observation(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M")
    c.record(action="describe_toolset", new_information=True)
    d = c.recommend(("describe_toolset", "observe_unreal"), context={"can_observe": True})
    assert d.action == "observe_unreal"

def test_observation_moves_to_unreal_call(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M")
    c.record(action="observe_unreal", new_information=True, observation="snapshot-1")
    d = c.recommend(("observe_unreal", "unreal_call"), context={"can_unreal_call": True})
    assert d.action == "unreal_call"

def test_failure_routes_to_research(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M")
    c.record(action="unreal_call", success=False, error="timeout")
    c.begin_recovery("unreal_call")
    d = c.recommend(("unreal_call", "research"))
    assert d.action == "research" and d.recovery

def test_recovery_budget_is_bounded(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M", max_recovery_attempts=2)
    assert c.begin_recovery("x") == 1
    assert c.begin_recovery("x") == 2
    assert not c.recovery_available("x")
    with pytest.raises(RuntimeError):
        c.begin_recovery("x")

def test_stagnation_guard_breaks_repeat_loop(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M", stagnation_limit=2)
    c.record(action="research", new_information=False)
    c.record(action="list_toolsets", new_information=False)
    d = c.recommend(("research", "observe_unreal"), context={"can_observe": True})
    assert d.action == "observe_unreal"

def test_done_is_not_accepted_while_stagnant(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M", stagnation_limit=2)
    c.record(action="research")
    c.record(action="list_toolsets")
    d = c.recommend(("done", "research"))
    assert d.action == "research"

def test_validated_capability_resets_stagnation(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M")
    c.record(action="research")
    c.mark_validated("unreal.observation", evidence="verified")
    assert c.state.stagnation_steps == 0
    assert c.state.has_validated("unreal.observation")

def test_planner_context_contains_memory(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M")
    c.set_hypothesis("snapshot before mutation")
    c.record(action="research", new_information=True, research_finding="f1", gap="tooling")
    ctx = c.planner_context()
    assert ctx["current_hypothesis"] == "snapshot before mutation"
    assert ctx["current_gap"] == "tooling"
    assert "f1" in ctx["research_findings"]

def test_evidence_is_bounded(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M", evidence_limit=3)
    for i in range(5):
        c.record(action="research", fingerprint=f"fp-{i}")
    assert len(c.state.evidence) == 3

def test_atomic_persistence_shape(tmp_path):
    p = tmp_path / "progress.json"
    c = AutonomousProgressController(p, "M")
    c.record(action="research", new_information=True)
    raw = json.loads(p.read_text())
    assert raw["mission_id"] == "M"
    assert isinstance(raw["evidence"], list)
    assert not (tmp_path / "progress.json.tmp").exists()

def test_state_validation_rejects_negative():
    with pytest.raises(ValueError):
        EvolutionProgressState("M", cycle=-1).validate()

def test_empty_action_rejected(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M")
    with pytest.raises(ValueError):
        c.record(action="")

def test_digest_changes_after_progress(tmp_path):
    c = AutonomousProgressController(tmp_path / "p.json", "M")
    before = c.digest()
    c.record(action="list_toolsets", new_information=True)
    assert c.digest() != before

def test_invalid_file_rejected(tmp_path):
    p = tmp_path / "p.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        AutonomousProgressController(p, "M")

