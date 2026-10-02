from __future__ import annotations

import json

from app.evolution.cognitive_fusion import CapabilityGap, Experience, ResearchFinding
from app.evolution.operational_brain import ActionOutcome, OperationalBrain


def test_operational_brain_unifies_goal_context_and_decision(tmp_path):
    brain = OperationalBrain(tmp_path, "m1", "become autonomous in Unreal")
    brain.register_gap(CapabilityGap("vision", "Improve Unreal perception", 0.9))
    brain.absorb_research(ResearchFinding(
        "r1", "Unreal perception", "Use live observation plus tool descriptions",
        ("source-a",), 0.9,
    ))

    decision = brain.decide(
        ("research", "observe_unreal", "evolve_code"),
        context={"capability_gap": True, "can_observe": True, "can_evolve_code": True},
    )

    assert decision.action in {"research", "observe_unreal", "evolve_code"}
    context = brain.reasoning_context()
    assert context["objective"] == "become autonomous in Unreal"
    assert context["cognitive_fusion"]["capability_gaps"]
    assert context["cognitive_fusion"]["research"]


def test_operational_brain_learns_from_execution(tmp_path):
    brain = OperationalBrain(tmp_path, "m2", "learn and improve")
    decision = brain.decide(("research",))

    outcome = brain.execute(
        decision,
        lambda action: ActionOutcome(
            action=action,
            success=True,
            result="research complete",
            new_information=True,
            evidence={"lesson": "prefer primary sources"},
        ),
    )

    assert outcome.success
    assert "prefer primary sources" in brain.fusion.memory.lessons()
    assert brain.state.phase == "LEARN"


def test_operational_brain_bounded_recovery(tmp_path):
    brain = OperationalBrain(tmp_path, "m3", "recover from tool failures", max_recovery_attempts=2)
    decision = brain.decide(("research",))

    failed = brain.execute(decision, lambda action: (_ for _ in ()).throw(RuntimeError("boom")))
    assert not failed.success
    assert brain.state.phase == "RECOVER"

    assert brain.recover("research", reason=failed.error)
    assert brain.state.phase == "RESEARCH"
    assert brain.recover("research")
    assert not brain.recover("research")
    assert brain.state.phase == "BLOCKED"


def test_operational_brain_survives_restart(tmp_path):
    first = OperationalBrain(tmp_path, "m4", "persistent mission")
    first.state.cycle = 7
    first.state.phase = "RESEARCH"
    first._persist()

    second = OperationalBrain(tmp_path, "m4", "ignored after persistence")
    assert second.state.objective == "persistent mission"
    assert second.state.cycle == 7
    assert second.state.phase == "RESEARCH"
    assert (tmp_path / "cognitive_fusion_snapshot.json").exists()


def test_operational_brain_archives_cross_mission_state(tmp_path):
    OperationalBrain(tmp_path, "m5", "first")

    second = OperationalBrain(tmp_path, "other", "second")

    assert second.state.mission_id == "other"
    assert second.state.objective == "second"
    assert not second.state.completed
    assert (tmp_path / "operational_brain.archive-m5.json").exists()


def test_operational_brain_snapshot_is_json(tmp_path):
    brain = OperationalBrain(tmp_path, "m6", "json")
    payload = brain.snapshot()
    json.dumps(payload, ensure_ascii=False, default=str)
