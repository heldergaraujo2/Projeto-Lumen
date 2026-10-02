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



def test_describe_toolset_injects_progress_selected_toolset_when_planner_omits_name(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionEngine
    from app.evolution.autonomous_progress import AutonomousProgressController
    from app.learning.runtime import LearningRuntime, LearningStore
    from app.learning.runtime import LearningRuntime
    from app.learning.store import LearningStore

    class Broker:
        def list_toolsets(self):
            return {"toolsets": [{"name": "SlateInspectorToolset.SlateInspectorToolset"}]}

    path = tmp_path / "mission.json"
    record = create_mission(path, goal="operate Unreal", project_root=tmp_path)
    store = MissionStore(path)
    engine = object.__new__(AutonomousMissionEngine)
    engine.record = record
    engine.store = store
    engine.broker = Broker()
    engine.progress = AutonomousProgressController(tmp_path / "progress.json", record.mission_id)
    engine.progress.record(
        action="list_toolsets", result="toolsets_listed", success=True,
        new_information=True,
        details={"toolsets": ["SlateInspectorToolset.SlateInspectorToolset"]},
    )
    engine.decision_provider = lambda _goal, _context: {
        "action": "describe_toolset", "reason": "inspect", "toolset_name": "",
        "tool_name": "", "query": "", "arguments": {},
    }

    decision = engine.decide("{}")
    assert decision["action"] == "describe_toolset"
    assert decision["toolset_name"] == "SlateInspectorToolset.SlateInspectorToolset"


def test_toolset_names_parses_real_unreal_mcp_text_envelope():
    from app.evolution.autonomous_mission import AutonomousMissionEngine

    payload = {
        "content": [
            {
                "type": "text",
                "text": "- ToolsetRegistry.AgentSkillToolset: Fornece ferramentas para anunciar, ler e criar/atualizar habilidades.\n- SlateInspectorToolset.SlateInspectorToolset: Conjunto de ferramentas de automação de UI do Slate estilo Playwright.\n\nExpõe ferramentas de instantâneo."
            }
        ]
    }

    assert AutonomousMissionEngine._toolset_names(payload) == (
        "ToolsetRegistry.AgentSkillToolset",
        "SlateInspectorToolset.SlateInspectorToolset",
    )

def test_autonomous_progress_guard_closes_discovery_research_loop(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionEngine
    from app.evolution.autonomous_progress import AutonomousProgressController

    class Broker:
        def list_toolsets(self):
            return {
                "toolsets": [
                    {"name": "SlateInspectorToolset.SlateInspectorToolset"},
                ]
            }

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
    assert second["toolset_name"] == "SlateInspectorToolset.SlateInspectorToolset"

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


def test_unreal_call_failure_is_persisted_and_does_not_block_the_mission(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionEngine
    from app.evolution.autonomous_progress import AutonomousProgressController
    from app.learning.runtime import LearningRuntime, LearningStore

    class Broker:
        def call(self, toolset_name, tool_name, arguments):
            raise TimeoutError("Unreal MCP call timed out")

    path = tmp_path / "mission.json"
    record = create_mission(path, goal="operate Unreal", project_root=tmp_path)
    store = MissionStore(path)
    engine = object.__new__(AutonomousMissionEngine)
    engine.record = record
    engine.store = store
    engine.broker = Broker()
    engine.progress = AutonomousProgressController(tmp_path / "progress.json", record.mission_id)
    engine.learning = LearningRuntime(LearningStore(tmp_path / "knowledge.json"))
    engine.decide = lambda _context: {
        "action": "unreal_call",
        "reason": "exercise capability",
        "toolset_name": "SlateInspectorToolset.SlateInspectorToolset",
        "tool_name": "Snapshot",
        "arguments": {},
    }

    result = engine.step({})
    assert result == "unreal_call_failed"
    assert record.status == "EVOLVING"
    assert record.last_result == "unreal_call_failed"
    assert "TimeoutError" in record.last_error
    assert engine.progress.state.last_action == "unreal_call"
    assert engine.progress.state.failure_counts["unreal_call"] == 1
    assert engine.progress.state.last_error == record.last_error


def test_failed_unreal_call_recommends_research_before_retry(tmp_path: Path):
    from app.evolution.autonomous_progress import AutonomousProgressController

    controller = AutonomousProgressController(tmp_path / "progress.json", "mission")
    controller.record(
        action="unreal_call",
        result="unreal_call_failed",
        success=False,
        error="TimeoutError: Unreal MCP call timed out",
        details={
            "toolset": "SlateInspectorToolset.SlateInspectorToolset",
            "tool": "Snapshot",
        },
    )

    decision = controller.recommend(
        ("research", "unreal_call", "evolve_code", "observe_unreal"),
        context={
            "can_research": True,
            "can_unreal_call": True,
            "can_evolve_code": True,
        },
    )
    assert decision.action == "research"
    assert decision.recovery is True
