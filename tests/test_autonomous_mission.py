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
