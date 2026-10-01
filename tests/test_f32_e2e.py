"""F32 end-to-end closed-loop lifecycle validation.

Validates observation, degradation trigger, planning, evolution gate,
explicit approval boundary, promotion metadata, monitoring, and
persistence/restart. No provider, driver, build, deployment, experiment,
or external application is executed.
"""

from pathlib import Path

from app.evolution.closed_loop import (
    ClosedLoopState,
    PersistentClosedLoopEvolution,
)
from app.evolution.continuous_intelligence import IntelligenceObservation
from app.evolution.models import Capability, CapabilityMeasurement, EvolutionRisk


def test_f32_end_to_end_closed_loop_persistence_and_approval(tmp_path: Path) -> None:
    path = tmp_path / "closed-loop.json"

    first = PersistentClosedLoopEvolution(path)

    # F24's evolution planner requires a registered capability and baseline
    # measurement when F32 opens the evolution gate. This is test setup only;
    # F32 continues to consume evidence and never executes the improvement.
    evolution = first.orchestrator.evolution
    evolution.register_capability(
        Capability(
            capability_id="reasoning",
            name="Reasoning",
            description="E2E test capability",
        )
    )
    evolution.baseline(
        CapabilityMeasurement(
            capability_id="reasoning",
            score=0.80,
            metric="quality",
            sample_size=5,
            evidence=("f31-verified-experience",),
        )
    )

    started = first.start("reasoning", 0.80)
    observed = first.observe(
        started.loop_id,
        IntelligenceObservation(
            "CI-EV-000001",
            "reasoning",
            0.60,
            5,
            "f31-verified-experience",
            0.80,
        ),
    )
    assert observed.state == ClosedLoopState.TRIGGERED

    trigger = first.trigger(started.loop_id)
    assert trigger is not None
    assert trigger.evidence_ids == ("CI-EV-000001",)
    assert trigger.risk is EvolutionRisk.HIGH

    planned = first.plan(
        started.loop_id,
        actions=("research", "benchmark", "security_review"),
        evidence_ids=trigger.evidence_ids,
    )
    assert planned.state == ClosedLoopState.PLANNED
    assert first.plans()[0].requires_human_approval is True

    context = first.open_evolution_gate(
        started.loop_id,
        problem="improve reasoning",
        risk=EvolutionRisk.HIGH,
    )
    assert context.state.value == "proposed"
    waiting = first.get(started.loop_id)
    assert waiting.state == ClosedLoopState.WAITING_EVIDENCE
    assert waiting.approval_required is True

    second = PersistentClosedLoopEvolution(path)
    reloaded = second.get(started.loop_id)
    assert reloaded.state == ClosedLoopState.WAITING_EVIDENCE
    assert reloaded.trigger_id == trigger.trigger_id
    assert reloaded.plan_id == planned.plan_id
    assert reloaded.evolution_id == context.evolution_id

    try:
        second.mark_promoted(started.loop_id)
    except ValueError:
        pass
    else:
        raise AssertionError("promotion bypassed the explicit approval gate")

    approved = second.mark_waiting_approval(started.loop_id)
    assert approved.state == ClosedLoopState.WAITING_APPROVAL

    promoted = second.mark_promoted(started.loop_id)
    assert promoted.state == ClosedLoopState.PROMOTED

    monitored = second.begin_monitoring(started.loop_id)
    assert monitored.state == ClosedLoopState.MONITORED

    third = PersistentClosedLoopEvolution(path)
    final = third.get(started.loop_id)
    assert final.state == ClosedLoopState.MONITORED
    assert final.observation_ids == ("CI-EV-000001",)
    assert third.counts() == {"loops": 1, "plans": 1}
    assert len(third.digest()) == 64

    assert not hasattr(third, "execute")
    assert not hasattr(third, "run_provider")
    assert not hasattr(third, "deploy")
