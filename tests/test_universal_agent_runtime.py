from __future__ import annotations

from pathlib import Path
import sys
import types

from app.agent_runtime.universal import UniversalAgentRuntime


class _Permissions:
    def __init__(self, granted: set[str]) -> None:
        self.granted = granted

    def is_granted(self, level) -> bool:
        return getattr(level, "name", str(level)) in self.granted


def test_runtime_reports_optional_dependencies_without_importing_them(monkeypatch):
    runtime = UniversalAgentRuntime(
        repo=Path("."),
        model="qwen3:8b",
        ollama_url="http://127.0.0.1:11434",
    )
    status = runtime.status()
    assert set(status) == {"openai_agents", "openhands", "browser_use"}


def test_browser_mutation_is_blocked_without_computer_control(monkeypatch):
    runtime = UniversalAgentRuntime(
        repo=Path("."),
        model="qwen3:8b",
        ollama_url="http://127.0.0.1:11434",
        permissions=_Permissions({"WEB_ACCESS"}),
    )
    assert runtime._granted("WEB_ACCESS")
    assert not runtime._granted("COMPUTER_CONTROL")


def test_code_mutation_requires_write_and_terminal():
    runtime = UniversalAgentRuntime(
        repo=Path("."),
        model="qwen3:8b",
        ollama_url="http://127.0.0.1:11434",
        permissions=_Permissions({"WRITE"}),
    )
    assert runtime._granted("WRITE")
    assert not runtime._granted("TERMINAL")


def test_runtime_is_optional_when_agents_sdk_is_unavailable(monkeypatch):
    runtime = UniversalAgentRuntime(
        repo=Path("."),
        model="qwen3:8b",
        ollama_url="http://127.0.0.1:11434",
    )
    monkeypatch.setitem(sys.modules, "agents", types.ModuleType("agents"))
    assert runtime.available() is False
