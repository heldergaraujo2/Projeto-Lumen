from pathlib import Path

from app.evolution.autonomous_mission import MissionStore, create_mission
from app.evolution.status import render


def test_mission_store_round_trip(tmp_path: Path):
    path = tmp_path / "mission.json"
    record = create_mission(path, goal="goal", project_root=tmp_path)
    loaded = MissionStore(path).load()
    assert loaded == record
    assert loaded.status == "WAITING_UNREAL"


def test_mission_event_log_and_status(tmp_path: Path):
    path = tmp_path / "mission.json"
    store = MissionStore(path)
    record = create_mission(path, goal="goal", project_root=tmp_path)
    record.status = "EVOLVING"
    record.phase = "PLANNING"
    record.last_action = "research"
    record.last_result = "research_ok"
    record.updated_at = __import__("time").time()
    store.save(record)
    store.event("decision_started", record, model="qwen3:8b")
    store.event("decision", record, action="research", reason="discover capability")

    assert store.event_path.exists()
    output = render(path)
    assert "RUNNING" in output
    assert "PLANNING" in output
    assert "research" in output
    assert "decision" in output


def test_autonomous_progress_guard_closes_discovery_research_loop(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionEngine
    from app.evolution.autonomous_progress import AutonomousProgressController

    class Broker:
        def list_toolsets(self):
            return ["SlateInspectorToolset.SlateInspectorToolset"]

    path = tmp_path / "mission.json"
    record = create_mission(path, goal="autonomously operate Unreal", project_root=tmp_path)
    store = MissionStore(path)

    engine = object.__new__(AutonomousMissionEngine)
    engine.record = record
    engine.store = store
    engine.broker = Broker()
    engine.progress = AutonomousProgressController(
        tmp_path / "autonomous_progress.json",
        record.mission_id,
        repeat_limit=2,
        stagnation_limit=3,
    )
    engine.decision_provider = lambda _goal, _context: {
        "action": "research",
        "reason": "planner keeps researching",
        "query": "Unreal Slate Inspector capabilities",
        "toolset_name": "",
        "tool_name": "",
        "arguments": {},
    }

    first = engine.decide("{}")
    assert first["action"] == "list_toolsets"

    engine.progress.record(
        action="list_toolsets",
        result="toolsets_listed",
        success=True,
        new_information=True,
        details={"toolsets": ["SlateInspectorToolset.SlateInspectorToolset"]},
    )
    second = engine.decide("{}")
    assert second["action"] == "describe_toolset"

    engine.progress.record(
        action="describe_toolset",
        result="toolset_described",
        success=True,
        new_information=True,
        details={"toolset": "SlateInspectorToolset.SlateInspectorToolset"},
    )
    third = engine.decide("{}")
    assert third["action"] == "observe_unreal"

    engine.progress.record(
        action="research",
        result="knowledge=3",
        success=True,
        new_information=True,
        research_finding="missing Unreal capability",
        gap="Required Unreal/Lumen capability identified by research",
    )
    fourth = engine.decide("{}")
    assert fourth["action"] == "evolve_code"
