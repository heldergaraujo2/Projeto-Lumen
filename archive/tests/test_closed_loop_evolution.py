import pytest
from app.evolution.closed_loop import ClosedLoopEvolution, ClosedLoopState, PersistentClosedLoopEvolution
from app.evolution.continuous_intelligence import IntelligenceObservation
from app.evolution.models import Capability, CapabilityMeasurement, EvolutionRisk
from app.evolution.orchestrator import EvolutionRuntimeOrchestrator

def observation(observation_id="CI-EV-000001", score=.8):
    return IntelligenceObservation(observation_id, "reasoning", score, 5, "fixture", .8)

def test_stable_loop_closes_without_opening_evolution():
    loop = ClosedLoopEvolution()
    record = loop.start("reasoning", .8)
    stable = loop.observe(record.loop_id, observation())
    assert stable.state == ClosedLoopState.STABLE
    assert loop.close_stable(record.loop_id).state == ClosedLoopState.CLOSED
    assert loop.counts() == {"loops": 1, "plans": 0}

def test_degradation_creates_triggered_plan_without_execution():
    loop = ClosedLoopEvolution()
    record = loop.start("reasoning", .8)
    loop.observe(record.loop_id, observation(score=.6))
    trigger = loop.trigger(record.loop_id)
    planned = loop.plan(record.loop_id, actions=("research", "benchmark", "security_review"), evidence_ids=trigger.evidence_ids)
    assert planned.state == ClosedLoopState.PLANNED
    assert loop.plans()[0].requires_human_approval

def test_plan_cannot_use_unrelated_evidence():
    loop = ClosedLoopEvolution()
    record = loop.start("reasoning", .8)
    loop.observe(record.loop_id, observation(score=.6))
    trigger = loop.trigger(record.loop_id)
    with pytest.raises(ValueError):
        loop.plan(record.loop_id, actions=("research",), evidence_ids=("OTHER",))

def test_evolution_gate_is_explicit_and_nonexecuting():
    orchestrator = EvolutionRuntimeOrchestrator()
    orchestrator.evolution.register_capability(Capability("reasoning", "Reasoning"))
    orchestrator.evolution.baseline(CapabilityMeasurement("reasoning", .8, "quality", 5))
    loop = ClosedLoopEvolution(orchestrator=orchestrator)
    record = loop.start("reasoning", .8)
    loop.observe(record.loop_id, observation(score=.6))
    trigger = loop.trigger(record.loop_id)
    loop.plan(record.loop_id, actions=("research",), evidence_ids=trigger.evidence_ids)
    context = loop.open_evolution_gate(record.loop_id, problem="improve reasoning", risk=EvolutionRisk.HIGH)
    assert context.state.value == "proposed"
    assert loop.get(record.loop_id).state == ClosedLoopState.WAITING_EVIDENCE
    assert not hasattr(loop, "execute")
    assert not hasattr(loop, "run_provider")
    assert not hasattr(loop, "deploy")

def test_approval_and_promotion_states_are_sequential():
    orchestrator = EvolutionRuntimeOrchestrator()
    orchestrator.evolution.register_capability(Capability("reasoning", "Reasoning"))
    orchestrator.evolution.baseline(CapabilityMeasurement("reasoning", .8, "quality", 5))
    loop = ClosedLoopEvolution(orchestrator=orchestrator)
    record = loop.start("reasoning", .8)
    loop.observe(record.loop_id, observation(score=.6))
    trigger = loop.trigger(record.loop_id)
    loop.plan(record.loop_id, actions=("research",), evidence_ids=trigger.evidence_ids)
    loop.open_evolution_gate(record.loop_id, problem="improve reasoning")
    with pytest.raises(ValueError):
        loop.mark_promoted(record.loop_id)
    loop.mark_waiting_approval(record.loop_id)
    loop.mark_promoted(record.loop_id)
    assert loop.begin_monitoring(record.loop_id).state == ClosedLoopState.MONITORED

def test_reject_requires_reason():
    loop = ClosedLoopEvolution()
    record = loop.start("reasoning", .8)
    with pytest.raises(ValueError):
        loop.close_rejected(record.loop_id, reason="")

def test_atomic_wrong_observation_does_not_change_loop():
    loop = ClosedLoopEvolution()
    record = loop.start("reasoning", .8)
    before = loop.get(record.loop_id)
    with pytest.raises(ValueError):
        loop.observe(record.loop_id, IntelligenceObservation("CI-EV-BAD", "vision", .5, 5, "x", .8))
    assert loop.get(record.loop_id) == before

def test_persistent_loop_roundtrip(tmp_path):
    path = tmp_path / "closed-loop.json"
    first = PersistentClosedLoopEvolution(path)
    record = first.start("reasoning", .8)
    first.observe(record.loop_id, observation(score=.6))
    trigger = first.trigger(record.loop_id)
    first.plan(record.loop_id, actions=("research",), evidence_ids=trigger.evidence_ids)
    second = PersistentClosedLoopEvolution(path)
    assert second.get(record.loop_id).state == ClosedLoopState.PLANNED
    assert second.plans()[0].trigger_id == trigger.trigger_id

def test_persistence_is_metadata_only(tmp_path):
    path = tmp_path / "closed-loop.json"
    loop = PersistentClosedLoopEvolution(path)
    record = loop.start("reasoning", .8)
    loop.observe(record.loop_id, observation())
    raw = path.read_text()
    assert "password" not in raw.lower()
    assert "screenshot" not in raw.lower()

def test_history_is_bounded():
    loop = ClosedLoopEvolution(history_limit=2)
    for i in range(3):
        r = loop.start("reasoning", .8)
        loop.observe(r.loop_id, IntelligenceObservation(f"CI-EV-{i+1:06d}", "reasoning", .8, 5, "x", .8))
    assert loop.counts()["loops"] == 2

def test_digest_is_deterministic():
    loop = ClosedLoopEvolution()
    r = loop.start("reasoning", .8)
    loop.observe(r.loop_id, observation())
    assert loop.digest() == loop.digest()
    assert len(loop.digest()) == 64

def test_policy_requires_human_approval():
    loop = ClosedLoopEvolution()
    record = loop.start("reasoning", .8)
    from dataclasses import replace
    with pytest.raises(ValueError):
        replace(record, approval_required=False).validate()
