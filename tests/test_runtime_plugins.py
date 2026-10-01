from __future__ import annotations
from app.runtime.plugins import PluginManager, PluginStatus

def test_plugin_manager_discovers_builtin_components(monkeypatch):
    monkeypatch.setattr("app.runtime.plugins._ollama_available", lambda: False)
    monkeypatch.setattr("app.runtime.plugins._mcp_available", lambda: False)
    reports = PluginManager().discover()
    by_id = {item.descriptor.id: item for item in reports}
    assert by_id["computer_control"].status is PluginStatus.AVAILABLE
    assert by_id["web_research"].status is PluginStatus.AVAILABLE
    assert by_id["unreal"].status is PluginStatus.AVAILABLE
    assert by_id["ollama"].status is PluginStatus.DEGRADED
    assert by_id["mcp"].status is PluginStatus.DEGRADED

def test_plugin_discovery_is_diagnostic_only():
    manager = PluginManager()
    assert not hasattr(manager, "grant_permission")
    assert not hasattr(manager, "arm_driver")
