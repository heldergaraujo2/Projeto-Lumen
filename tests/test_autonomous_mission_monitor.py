from __future__ import annotations

import json
import time

import pytest

tk = pytest.importorskip("tkinter")

from app.ui.autonomous_mission_monitor import AutonomousMissionMonitor


@pytest.fixture()
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tkinter sem display: {exc}")
    yield window
    try:
        window.destroy()
    except tk.TclError:
        pass


def test_monitor_reads_mission_and_live_events(tmp_path, root):
    evolution = tmp_path / "evolution"
    evolution.mkdir()
    mission = {
        "mission_id": "M1",
        "goal": "Torne a Lúmen autônoma",
        "project_root": str(tmp_path),
        "status": "EVOLVING",
        "cycle": 3,
        "last_action": "research",
        "last_error": "",
        "phase": "RESEARCH",
        "last_result": "research_ok:knowledge=2",
        "last_started_at": time.time(),
        "last_duration_seconds": 0.5,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    (evolution / "mission.json").write_text(json.dumps(mission), encoding="utf-8")
    (evolution / "evolution_log.jsonl").write_text(
        json.dumps({
            "timestamp": time.time(),
            "event": "action_completed",
            "mission_id": "M1",
            "cycle": 3,
            "status": "EVOLVING",
            "phase": "RESEARCH",
            "action": "research",
            "result": "ok",
        }) + "\n",
        encoding="utf-8",
    )

    monitor = AutonomousMissionMonitor(root, data_dir=tmp_path)
    root.update()

    assert monitor.status.cget("text") == "EVOLUINDO"
    assert monitor.phase.cget("text") == "PESQUISA"
    assert monitor.action.cget("text") == "pesquisa"
    assert "Torne a Lúmen autônoma" in monitor.goal.cget("text")
    assert "action_completed" in monitor.log.get("1.0", tk.END)
    assert "Lúmen:" in monitor.log.get("1.0", tk.END)
    monitor.close()


def test_monitor_explains_completed_code_evolution_in_natural_language():
    text = AutonomousMissionMonitor._natural_explanation(
        {"event": "action_completed", "action": "evolve_code", "result": "verified"}
    )
    assert "evolução no código" in text
    assert "validação" in text
    assert "evidência" in text


def test_monitor_explains_errors_and_recovery_plan():
    text = AutonomousMissionMonitor._natural_explanation(
        {
            "event": "action_failed",
            "action": "evolve_code",
            "error": "AssertionError: teste falhou",
            "gap": "Pesquisar a causa e corrigir a implementação antes de testar novamente.",
        }
    )
    assert "falhou" in text
    assert "AssertionError: teste falhou" in text
    assert "corrigir" in text
    assert "testar novamente" in text


def test_monitor_explains_guarded_planner_decision():
    text = AutonomousMissionMonitor._natural_explanation(
        {
            "event": "decision_guarded",
            "proposed_action": "done",
            "selected_action": "research",
            "reason": "faltam evidências",
        }
    )
    assert "sugeriu 'done'" in text
    assert "não aceitou" in text
    assert "research" in text
    assert "faltam evidências" in text


def test_monitor_explains_unreal_call_and_required_verification():
    text = AutonomousMissionMonitor._natural_explanation(
        {
            "event": "action_completed",
            "action": "unreal_call",
            "toolset": "SlateInspectorToolset.SlateInspectorToolset",
            "tool": "Click",
        }
    )
    assert "SlateInspectorToolset.SlateInspectorToolset.Click" in text
    assert "observar" in text
    assert "efeito" in text
