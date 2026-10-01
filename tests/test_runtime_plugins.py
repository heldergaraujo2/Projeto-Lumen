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

def test_mcp_discovery_uses_real_protocol(monkeypatch):
    from app.unreal.mcp import MCPResponse

    class FakeMCPClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def list_tools(self):
            return MCPResponse(result={"tools": []})

    monkeypatch.setattr("app.unreal.mcp.UnrealMCPClient", FakeMCPClient)
    from app.runtime.plugins import _mcp_available

    assert _mcp_available() is True


def test_mcp_discovery_rejects_protocol_error(monkeypatch):
    from app.unreal.mcp import MCPResponse

    class FakeMCPClient:
        def __init__(self, **kwargs):
            pass

        def list_tools(self):
            return MCPResponse(error={"code": -32600, "message": "invalid"})

    monkeypatch.setattr("app.unreal.mcp.UnrealMCPClient", FakeMCPClient)
    from app.runtime.plugins import _mcp_available

    assert _mcp_available() is False
