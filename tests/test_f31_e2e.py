"""F31 end-to-end lifecycle validation.

Exercises the real F31 persistence/restart/reuse/adaptation contract without
granting execution authority or touching external applications.
"""
import json
import subprocess
import sys
from pathlib import Path

from app.experience import (
    ExperienceEvent,
    ExperienceOutcome,
    ExperienceStore,
    ExperienceTrace,
    PersistentWorkflowRegistry,
    WorkflowIntelligence,
)
from app.workflows import WorkflowEvidence, WorkflowOutcome


def _trace(experience_id: str, path: str, value: str, fingerprint: str) -> ExperienceTrace:
    return ExperienceTrace(
        experience_id=experience_id,
        goal="abrir asset no Unreal",
        events=(
            ExperienceEvent(
                0, "open_asset", (("path", path),), fingerprint, True, ExperienceOutcome.SUCCESS
            ),
            ExperienceEvent(
                1, "select_value", (("value", value),), fingerprint + "-2", True, ExperienceOutcome.SUCCESS
            ),
        ),
        outcome=ExperienceOutcome.SUCCESS,
        context=(("application", "UnrealEditor"),),
    )


def test_f31_end_to_end_restart_recall_reuse_adapt_verify(tmp_path: Path) -> None:
    experience_path = tmp_path / "experience.json"
    workflow_path = tmp_path / "workflows.json"

    # Real lifecycle start: two successful, verified experiences are recorded.
    first_store = ExperienceStore(experience_path)
    first_registry = PersistentWorkflowRegistry(workflow_path)
    intelligence = WorkflowIntelligence(
        experience_store=first_store,
        workflow_registry=first_registry,
    )
    first = _trace("e2e-1", "/Game/A", "A", "fp-A")
    second = _trace("e2e-2", "/Game/B", "B", "fp-B")
    intelligence.record(first)
    intelligence.record(second)

    # Generalization creates reusable knowledge only from verified success.
    result = intelligence.generalize(
        workflow_id="asset.open",
        name="Open asset",
        traces=(first, second),
    )
    assert result.generalized_variables == ("step0_path", "step1_value")

    # Verification is an explicit evidence gate before reuse.
    assert intelligence.reuse("abrir asset Unreal") == ()
    intelligence.record_verification(
        workflow_id="asset.open",
        success=True,
        observation_fingerprint="verified-open",
    )

    # Adaptation happens in-memory after exact bindings are supplied.
    adapted = intelligence.adapt(
        "asset.open",
        {"step0_path": "/Game/C", "step1_value": "C"},
    )
    assert dict(adapted.steps[0].parameters)["path"] == "/Game/C"

    # Simulate an actual process restart: a fresh interpreter reloads both stores.
    probe = tmp_path / "restart_probe.py"
    probe.write_text(
        """
import json
import sys
from app.experience import ExperienceStore, PersistentWorkflowRegistry, WorkflowIntelligence

experience_path, workflow_path = sys.argv[1:3]
store = ExperienceStore(experience_path)
registry = PersistentWorkflowRegistry(workflow_path)
intel = WorkflowIntelligence(experience_store=store, workflow_registry=registry)
experience = store.get("e2e-1")
matches = intel.reuse("abrir asset Unreal")
adapted = intel.adapt("asset.open", {"step0_path": "/Game/C", "step1_value": "C"})
print(json.dumps({
    "experience_reloaded": experience is not None,
    "experience_goal": None if experience is None else experience.goal,
    "match_count": len(matches),
    "workflow_reloaded": registry.get("asset.open") is not None,
    "adapted_path": dict(adapted.steps[0].parameters)["path"],
    "evidence_count": len(registry.evidence("asset.open")),
}))
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(probe), str(experience_path), str(workflow_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    result_after_restart = json.loads(completed.stdout)

    assert result_after_restart == {
        "experience_reloaded": True,
        "experience_goal": "abrir asset no Unreal",
        "match_count": 1,
        "workflow_reloaded": True,
        "adapted_path": "/Game/C",
        "evidence_count": 1,
    }

    # Final evidence remains metadata only; this test never invokes a driver.
    registry = PersistentWorkflowRegistry(workflow_path)
    stats = registry.stats("asset.open")
    assert stats.attempts == 1
    assert stats.successes == 1
    assert stats.last_outcome is WorkflowOutcome.SUCCESS
