from pathlib import Path

from app.evolution.autonomous_mission import MissionStore, create_mission
from app.evolution.voice_mission import VOICE_GOAL


def test_voice_preset_mission_can_be_created_without_unreal(tmp_path: Path):
    record = create_mission(
        tmp_path / "mission.json",
        goal=VOICE_GOAL,
        project_root=tmp_path,
        requires_unreal=False,
    )
    assert record.requires_unreal is False
    assert "microfone" in record.goal.lower()
    loaded = MissionStore(tmp_path / "mission.json").load()
    assert loaded is not None
    assert loaded.requires_unreal is False


def test_non_unreal_mission_starts_evolving_without_waiting_for_unreal(tmp_path: Path):
    record = create_mission(
        tmp_path / "mission.json",
        goal=VOICE_GOAL,
        project_root=tmp_path,
        requires_unreal=False,
    )
    assert record.status == "EVOLVING"
    assert record.phase == "PLANNING"


def test_legacy_mission_records_keep_unreal_requirement_default(tmp_path: Path):
    path = tmp_path / "mission.json"
    path.write_text(
        '{"mission_id":"M","goal":"legacy","project_root":"."}',
        encoding="utf-8",
    )
    record = MissionStore(path).load()
    assert record is not None
    assert record.requires_unreal is True
