from __future__ import annotations

import hashlib
from pathlib import Path

from app.evolution.autonomous_progress import AutonomousProgressController
from app.evolution.cognitive_fusion import CapabilityGap, CognitiveFusion
from app.evolution.operational_brain import OperationalBrain
from app.evolution.autonomous_mission import AutonomousMissionEngine, MissionStore, create_mission


def test_cognitive_fusion_is_the_progress_authority_for_operational_brain(tmp_path: Path):
    brain = OperationalBrain(tmp_path, "mission-1", "operate Unreal")
    assert brain.fusion.progress is not None
    assert brain.fusion.progress.path == tmp_path / "autonomous_progress.json"
    decision = brain.decide(
        ("list_toolsets", "research"),
        context={"can_research": True},
    )
    assert decision.action == "list_toolsets"


def test_operational_brain_archives_state_when_mission_changes(tmp_path: Path):
    brain = OperationalBrain(tmp_path, "mission-old", "old goal")
    brain.state.last_decision = "research"
    brain._persist()

    replacement = OperationalBrain(tmp_path, "mission-new", "new goal")
    assert replacement.state.mission_id == "mission-new"
    assert replacement.state.objective == "new goal"
    assert list(tmp_path.glob("operational_brain.archive-mission-old*.json"))


def test_toolset_description_is_persisted_as_planner_evidence(tmp_path: Path):
    controller = AutonomousProgressController(tmp_path / "progress.json", "mission")
    description = {"tools": [{"name": "Snapshot"}, {"name": "Screenshot"}]}
    controller.record(
        action="describe_toolset",
        result="toolset_described",
        success=True,
        new_information=True,
        details={
            "toolset": "SlateInspectorToolset.SlateInspectorToolset",
            "description": description,
        },
    )
    reloaded = AutonomousProgressController(tmp_path / "progress.json", "mission")
    assert reloaded.state.toolset_descriptions[
        "SlateInspectorToolset.SlateInspectorToolset"
    ] == description
    assert reloaded.planner_context()["toolset_descriptions"][
        "SlateInspectorToolset.SlateInspectorToolset"
    ] == description


def test_post_action_observation_closes_verification_loop(tmp_path: Path):
    controller = AutonomousProgressController(tmp_path / "progress.json", "mission")
    before = hashlib.sha256(b"before").hexdigest()
    after = hashlib.sha256(b"after").hexdigest()

    controller.record(
        action="observe_unreal",
        result="snapshot_ok",
        success=True,
        new_information=True,
        details={"observation_digest": before},
        observation="pre-action snapshot",
    )
    controller.record(
        action="unreal_call",
        result="unreal_call_ok",
        success=True,
        new_information=True,
        capability="unreal:Slate.Snapshot",
        details={"toolset": "Slate", "tool": "Snapshot"},
    )
    assert controller.state.pending_capability == "unreal:Slate.Snapshot"
    assert controller.state.verification_passed is False

    controller.record(
        action="observe_unreal",
        result="verification_ok",
        success=True,
        new_information=True,
        details={"observation_digest": after, "verification": True},
        observation="post-action snapshot changed",
    )
    assert controller.state.verification_passed is True


def test_done_is_not_admissible_without_post_action_verification(tmp_path: Path):
    path = tmp_path / "mission.json"
    record = create_mission(path, goal="operate Unreal", project_root=tmp_path)
    store = MissionStore(path)
    engine = object.__new__(AutonomousMissionEngine)
    engine.record = record
    engine.store = store
    engine.progress = AutonomousProgressController(
        tmp_path / "progress.json", record.mission_id
    )
    engine.ollama = type("Ollama", (), {"model": "qwen3:8b"})()
    engine.decision_provider = lambda _goal, _context: {
        "action": "done",
        "reason": "planner thinks the goal is complete",
        "query": "",
        "toolset_name": "",
        "tool_name": "",
        "arguments": {},
    }

    decision = engine.decide("{}")
    assert decision["action"] == "research"
