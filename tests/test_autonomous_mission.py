import json
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


def test_planner_failure_falls_back_to_progress_guard(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionEngine
    from app.evolution.autonomous_progress import AutonomousProgressController

    path = tmp_path / "mission.json"
    record = create_mission(path, goal="operate Unreal", project_root=tmp_path)
    store = MissionStore(path)
    engine = object.__new__(AutonomousMissionEngine)
    engine.record = record
    engine.store = store
    engine.progress = AutonomousProgressController(tmp_path / "progress.json", record.mission_id)
    engine.ollama = type("Ollama", (), {"model": "qwen3:8b"})()
    engine.decision_provider = lambda _goal, _context: (_ for _ in ()).throw(
        TimeoutError("planner timed out")
    )

    decision = engine.decide("{}")

    assert decision["action"] == "list_toolsets"
    assert "planner timed out" in decision["reason"]
    events = [
        json.loads(line)
        for line in store.event_path.read_text(encoding="utf-8").splitlines()
    ]
    assert any(event["event"] == "decision_failed" for event in events)
    assert any(
        event["event"] == "decision_guarded"
        and event.get("selected_action") == "list_toolsets"
        for event in events
    )


def test_invalid_planner_json_falls_back_to_progress_guard(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionEngine
    from app.evolution.autonomous_progress import AutonomousProgressController

    class Ollama:
        model = "qwen3:8b"

        def chat(self, *_args, **_kwargs):
            return "{invalid json"

    path = tmp_path / "mission.json"
    record = create_mission(path, goal="operate Unreal", project_root=tmp_path)
    store = MissionStore(path)
    engine = object.__new__(AutonomousMissionEngine)
    engine.record = record
    engine.store = store
    engine.progress = AutonomousProgressController(tmp_path / "progress.json", record.mission_id)
    engine.ollama = Ollama()
    engine.decision_provider = None

    decision = engine.decide("{}")

    assert decision["action"] == "list_toolsets"
    assert "invalid autonomous mission JSON" in decision["reason"]
    events = [
        json.loads(line)
        for line in store.event_path.read_text(encoding="utf-8").splitlines()
    ]
    assert any(event["event"] == "decision_failed" for event in events)



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


def test_stagnation_guard_never_selects_describe_without_toolset_inventory(tmp_path: Path):
    from app.evolution.autonomous_progress import AutonomousProgressController

    controller = AutonomousProgressController(
        tmp_path / "progress.json",
        "mission",
        stagnation_limit=1,
    )
    controller.state.stagnation_steps = 1
    decision = controller.recommend(
        ("describe_toolset", "list_toolsets", "research"),
        context={"can_research": True},
    )
    assert decision.action == "list_toolsets"


def test_mission_store_retries_transient_windows_permission_error(tmp_path: Path):
    from unittest.mock import patch

    path = tmp_path / "mission.json"
    store = MissionStore(path)
    record = create_mission(path, goal="goal", project_root=tmp_path)
    original_replace = Path.replace
    calls = {"count": 0}

    def flaky_replace(self: Path, target: Path):
        calls["count"] += 1
        if calls["count"] < 3:
            raise PermissionError("simulated Windows file lock")
        return original_replace(self, target)

    with patch.object(Path, "replace", new=flaky_replace):
        store.save(record)

    assert calls["count"] == 3
    assert store.load() == record

def test_generic_admission_counts_detailed_action_fingerprints(tmp_path: Path):
    from app.evolution.autonomous_progress import AutonomousProgressController

    controller = AutonomousProgressController(
        tmp_path / "progress.json",
        "mission",
        repeat_limit=2,
    )
    controller.record(
        action="list_toolsets",
        result="toolsets_listed",
        success=True,
        new_information=False,
        details={"toolsets": ["A"]},
    )
    controller.record(
        action="list_toolsets",
        result="toolsets_listed",
        success=True,
        new_information=False,
        details={"toolsets": ["B"]},
    )

    assert controller.admit("list_toolsets") is False


def test_failed_unreal_call_persists_capability_gap(tmp_path: Path):
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

    assert engine.step({}) == "unreal_call_failed"
    assert "Unreal capability failed:" in engine.progress.state.current_gap


def test_evolve_code_replaces_frozen_config_goal(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionEngine
    from app.evolution.autonomous_loop import EvolutionConfig
    from app.evolution.autonomous_progress import AutonomousProgressController
    from app.learning.runtime import LearningRuntime, LearningStore

    class Evolution:
        def __init__(self):
            self.config = EvolutionConfig(repo=tmp_path, goal="old goal")
            self.seen_goal = ""

        def cycle(self, _cycle):
            self.seen_goal = self.config.goal
            return "verified-commit"

    path = tmp_path / "mission.json"
    record = create_mission(path, goal="evolve Unreal capability", project_root=tmp_path)
    store = MissionStore(path)
    evolution = Evolution()
    engine = object.__new__(AutonomousMissionEngine)
    engine.record = record
    engine.store = store
    engine.progress = AutonomousProgressController(tmp_path / "progress.json", record.mission_id)
    engine.learning = LearningRuntime(LearningStore(tmp_path / "knowledge.json"))
    engine._evolution = evolution
    engine.decide = lambda _context: {"action": "evolve_code", "reason": "implement missing capability"}

    assert engine.step({}) == "evolve_code"
    assert "evolve Unreal capability" in evolution.seen_goal
    assert "CAPABILITY GAP:" in evolution.seen_goal


def test_evolve_code_failure_is_persisted_and_researchable(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionEngine
    from app.evolution.autonomous_progress import AutonomousProgressController
    from app.learning.runtime import LearningRuntime, LearningStore

    class Evolution:
        def cycle(self, _cycle):
            raise RuntimeError("candidate change failed validation")

    path = tmp_path / "mission.json"
    record = create_mission(path, goal="evolve Unreal capability", project_root=tmp_path)
    store = MissionStore(path)
    engine = object.__new__(AutonomousMissionEngine)
    engine.record = record
    engine.store = store
    engine.progress = AutonomousProgressController(tmp_path / "progress.json", record.mission_id)
    engine.learning = LearningRuntime(LearningStore(tmp_path / "knowledge.json"))
    engine._evolution = Evolution()
    engine.decide = lambda _context: {"action": "evolve_code", "reason": "implement missing capability"}

    assert engine.step({}) == "evolve_code_failed"
    assert record.status == "EVOLVING"
    assert record.last_result == "evolve_code_failed"
    assert "candidate change failed validation" in record.last_error
    assert engine.progress.state.failure_counts["evolve_code"] == 1
    assert "Autonomous code evolution failed." in engine.progress.state.current_gap


def test_failed_evolve_code_recommends_research(tmp_path: Path):
    from app.evolution.autonomous_progress import AutonomousProgressController

    controller = AutonomousProgressController(tmp_path / "progress.json", "mission")
    controller.record(
        action="evolve_code",
        result="evolve_code_failed",
        success=False,
        error="RuntimeError: candidate change failed validation",
        gap="Autonomous code evolution failed.",
        details={"evolution_cycle": 1},
    )

    decision = controller.recommend(
        ("research", "evolve_code", "observe_unreal"),
        context={
            "can_research": True,
            "can_evolve_code": True,
            "capability_gap": controller.state.current_gap,
        },
    )
    assert decision.action == "research"


def test_progress_guard_failure_enters_autonomous_recovery_instead_of_blocking(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionEngine
    from app.evolution.autonomous_progress import AutonomousProgressController

    path = tmp_path / "mission.json"
    record = create_mission(path, goal="operate Unreal", project_root=tmp_path)
    store = MissionStore(path)
    engine = object.__new__(AutonomousMissionEngine)
    engine.record = record
    engine.store = store
    engine.progress = AutonomousProgressController(tmp_path / "progress.json", record.mission_id)
    engine.decision_provider = lambda _goal, _context: {
        "action": "research", "reason": "planner has no new action", "query": "",
        "toolset_name": "", "tool_name": "", "arguments": {},
    }

    def exhausted(*_args, **_kwargs):
        raise RuntimeError("autonomous progress exhausted: planner must provide new evidence")

    engine.progress.recommend = exhausted

    decision = engine.decide("{}")

    assert decision["action"] == "research"
    assert record.status == "EVOLVING"
    assert record.phase == "RECOVERY"
    assert "progress exhausted" in record.last_error
    events = [json.loads(line) for line in store.event_path.read_text(encoding="utf-8").splitlines()]
    assert any(event["event"] == "decision_failed" and event.get("fallback") == "autonomous_recovery" for event in events)



def test_recovery_research_escalates_to_bounded_code_correction(tmp_path: Path):
    from app.evolution.autonomous_progress import AutonomousProgressController

    controller = AutonomousProgressController(tmp_path / "progress.json", "mission", repeat_limit=2)
    controller.record(
        action="evolve_code",
        result="evolve_code_failed",
        success=False,
        error="RuntimeError: code evolution rolled back",
        gap="Autonomous code evolution failed.",
        details={"evolution_cycle": 1},
    )
    controller.record(
        action="research",
        result="knowledge=0",
        success=True,
        new_information=True,
        research_finding="Diagnose the failed code evolution",
        gap="Autonomous code evolution failed.",
        details={"knowledge_items": 0, "recovery": True},
    )

    decision = controller.recommend(
        ("research", "evolve_code", "observe_unreal"),
        context={
            "can_research": True,
            "can_evolve_code": True,
            "can_observe": True,
            "capability_gap": controller.state.current_gap,
            "recovery": True,
        },
    )

    assert decision.action == "evolve_code"
    assert decision.recovery is True
    assert controller.state.recovery_counts["evolve_code"] == 1


def test_progress_guard_recovery_fallback_marks_research_as_recovery(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionEngine
    from app.evolution.autonomous_progress import AutonomousProgressController

    path = tmp_path / "mission.json"
    record = create_mission(path, goal="operate Unreal", project_root=tmp_path)
    store = MissionStore(path)
    engine = object.__new__(AutonomousMissionEngine)
    engine.record = record
    engine.store = store
    engine.progress = AutonomousProgressController(tmp_path / "progress.json", record.mission_id)
    engine.decision_provider = lambda _goal, _context: (_ for _ in ()).throw(TimeoutError("planner timed out"))

    decision = engine.decide("{}")

    assert decision["action"] == "list_toolsets"
    assert decision.get("recovery") is False

    engine.progress.state.current_gap = "planner failure requires diagnosis"
    from app.evolution.autonomous_progress import ProgressDecision

    engine.progress.recommend = lambda *_args, **_kwargs: ProgressDecision(
        "research",
        "recover by researching the planner failure",
        True,
        True,
    )
    decision = engine.decide("{}")
    assert decision["action"] == "research"
    assert decision["recovery"] is True


def test_supervisor_start_resumes_blocked_mission(tmp_path: Path):
    from app.evolution.autonomous_mission import AutonomousMissionSupervisor

    path = tmp_path / "data" / "evolution" / "mission.json"
    record = create_mission(path, goal="operate Unreal", project_root=tmp_path)
    record.status = "BLOCKED"
    record.phase = "PLANNING"
    record.last_error = "autonomous progress exhausted"
    MissionStore(path).save(record)

    supervisor = object.__new__(AutonomousMissionSupervisor)
    supervisor.store = MissionStore(path)
    supervisor._stop = __import__("threading").Event()
    supervisor._thread = None
    supervisor.poll_seconds = 5.0
    supervisor.probe = type("Probe", (), {"probe": lambda self: (False, {"error": "test probe disabled"})})()

    supervisor.start()

    resumed = MissionStore(path).load()
    assert resumed is not None
    assert resumed.status == "EVOLVING"
    assert resumed.phase == "PLANNING"
    assert resumed.last_error == ""
    events = [
        json.loads(line)
        for line in supervisor.store.event_path.read_text(encoding="utf-8").splitlines()
    ]
    assert any(event["event"] == "mission_resumed" for event in events)
    assert any(event["event"] == "supervisor_started" for event in events)
    supervisor.stop()


def test_run_command_starts_existing_mission_and_supports_once_mode(tmp_path: Path, monkeypatch, capsys):
    import sys
    import app.evolution.autonomous_mission as mission_module

    path = tmp_path / "data" / "evolution" / "mission.json"
    record = create_mission(path, goal="voice mission", project_root=tmp_path, requires_unreal=False)

    class FakeSupervisor:
        def __init__(self, **kwargs):
            self.store = MissionStore(path)
            self.started = False
            self.stopped = False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    holder = {}
    def factory(**kwargs):
        supervisor = FakeSupervisor(**kwargs)
        holder["supervisor"] = supervisor
        return supervisor

    monkeypatch.setattr(mission_module, "AutonomousMissionSupervisor", factory)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autonomous_mission",
            "run",
            "--project-root",
            str(tmp_path),
            "--data-dir",
            str(tmp_path / "data"),
            "--once",
            "--once-seconds",
            "0.05",
        ],
    )

    assert mission_module.main() == 0
    assert holder["supervisor"].started is True
    assert holder["supervisor"].stopped is True
    assert "LUMEN-MISSION-" in capsys.readouterr().out
