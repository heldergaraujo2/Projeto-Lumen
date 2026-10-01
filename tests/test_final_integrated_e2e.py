"""Final integrated E2E: verified F30 evidence -> F31 intelligence -> F32 evolution gate.

This test validates the cross-phase evidence handoff without reopening F30,
performing physical input, invoking a provider, running an experiment, or
promoting a real change.
"""

from pathlib import Path

from app.evolution.closed_loop import ClosedLoopState, PersistentClosedLoopEvolution
from app.evolution.continuous_intelligence import IntelligenceObservation
from app.evolution.models import Capability, CapabilityMeasurement, EvolutionRisk
from app.experience import (
    ExperienceEvent,
    ExperienceOutcome,
    ExperienceStore,
    ExperienceTrace,
    PersistentWorkflowRegistry,
    WorkflowIntelligence,
)


def test_final_integrated_e2e_f30_evidence_to_f31_to_f32(tmp_path: Path) -> None:
    experience_path = tmp_path / "experience.json"
    workflow_path = tmp_path / "workflows.json"
    loop_path = tmp_path / "closed-loop.json"

    # F30 was already physically validated and closed. This identifier is the
    # immutable handoff reference to that existing verification; this test
    # does not execute Unreal or repeat the physical click.
    f30_verification = "f30-real-unreal-content-browser-verified"

    # F31 consumes the verified F30 result as an experience observation.
    store = ExperienceStore(experience_path)
    registry = PersistentWorkflowRegistry(workflow_path)
    intelligence = WorkflowIntelligence(
        experience_store=store,
        workflow_registry=registry,
    )
    trace = ExperienceTrace(
        experience_id="integrated-f30-1",
        goal="abrir asset no Unreal",
        events=(
            ExperienceEvent(
                sequence=0,
                action="open_content_browser_asset",
                parameters=(("path", "/Game/Aether/Characters/Mago"),),
                observation_fingerprint=f30_verification,
                verified=True,
                outcome=ExperienceOutcome.SUCCESS,
            ),
        ),
        outcome=ExperienceOutcome.SUCCESS,
        context=(("application", "UnrealEditor"), ("source", "F30")),
        source="f30_verified_real_validation",
    )
    intelligence.record(trace)
    generalized = intelligence.generalize(
        workflow_id="unreal.asset.open",
        name="Open verified Unreal asset",
        traces=(trace,),
    )
    assert generalized.source_experiences == ("integrated-f30-1",)

    intelligence.record_verification(
        workflow_id="unreal.asset.open",
        success=True,
        observation_fingerprint=f30_verification,
        reason="F30 real post-action verification",
    )
    assert intelligence.reuse("abrir asset no Unreal")

    # F32 receives the verified F31 evidence and turns degradation into an
    # approval-gated evolution cycle. It still does not execute remediation.
    loop = PersistentClosedLoopEvolution(loop_path)
    evolution = loop.orchestrator.evolution
    evolution.register_capability(
        Capability(
            capability_id="unreal_asset_workflow",
            name="Unreal asset workflow",
            description="Integrated E2E capability",
        )
    )
    evolution.baseline(
        CapabilityMeasurement(
            capability_id="unreal_asset_workflow",
            score=0.90,
            metric="verified_workflow_quality",
            sample_size=1,
            evidence=(f30_verification,),
        )
    )

    started = loop.start("unreal_asset_workflow", 0.90)
    observation = IntelligenceObservation(
        "CI-EV-INTEGRATED-000001",
        "unreal_asset_workflow",
        0.60,
        1,
        f30_verification,
        0.90,
    )
    observed = loop.observe(started.loop_id, observation)
    assert observed.state == ClosedLoopState.TRIGGERED

    trigger = loop.trigger(started.loop_id)
    assert trigger is not None
    assert trigger.evidence_ids == ("CI-INTEGRATED-000001",)

    planned = loop.plan(
        started.loop_id,
        actions=("research", "benchmark", "security_review"),
        evidence_ids=trigger.evidence_ids,
    )
    assert planned.evidence_ids == ("CI-INTEGRATED-000001",)

    context = loop.open_evolution_gate(
        started.loop_id,
        problem="improve verified Unreal asset workflow",
        risk=EvolutionRisk.HIGH,
    )
    assert context.state.value == "proposed"

    waiting = loop.get(started.loop_id)
    assert waiting.state == ClosedLoopState.WAITING_EVIDENCE
    assert waiting.approval_required is True

    # Integrated safety invariant: no execution authority is created by the
    # cross-phase handoff.
    assert not hasattr(loop, "execute")
    assert not hasattr(loop, "run_provider")
    assert not hasattr(loop, "deploy")
    assert registry.stats("unreal.asset.open").successes == 1
