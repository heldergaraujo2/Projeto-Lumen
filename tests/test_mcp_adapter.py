from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.mcp_runtime.adapter import MCPRuntimeConfig
from app.tools.mcp import MCPCallTool
from app.tools.control import ToolsController
from app.mcp_runtime.stdio import MCPServerConfig
from app.security.permissions import PermissionDeniedError, PermissionLevel, PermissionManager
from app.tools.base import ToolRegistry

FAKE_SERVER = r'''import json, sys
for line in sys.stdin:
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "echo", "description": "echo args", "inputSchema": {"type": "object"}}]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": json.dumps(msg["params"]["arguments"])}], "isError": False}
    else:
        continue
    if "id" in msg:
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
'''


def test_config_load_keeps_disabled_servers_inert(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"schema_version": 1, "servers": [
        {"name": "fake", "command": sys.executable, "enabled": False,
         "allowed_tools": ["echo"]}
    ]}), encoding="utf-8")
    assert MCPRuntimeConfig.load(path).servers == ()


def test_mcp_tool_uses_existing_permission_gate_and_executes_allowlisted_call(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"schema_version": 1, "servers": [
        {"name": "fake", "transport": "stdio", "command": sys.executable,
         "args": ["-u", "-c", FAKE_SERVER], "enabled": True,
         "allowed_tools": ["echo"], "request_timeout_seconds": 2,
         "startup_timeout_seconds": 2}
    ]}), encoding="utf-8")
    config = MCPRuntimeConfig.load(path)
    permissions = PermissionManager()
    registry = ToolRegistry(permissions)
    registry.register(MCPCallTool(config))
    with pytest.raises(PermissionDeniedError):
        registry.execute("mcp_call", server_name="fake", tool_name="echo", arguments_json='{"x":1}')
    permissions.grant(PermissionLevel.COMPUTER_CONTROL)
    result = json.loads(registry.execute("mcp_call", server_name="fake", tool_name="echo", arguments_json='{"x":1}'))
    assert result["ok"] is True
    assert result["data"]["server"] == "fake"


def test_mcp_tool_rejects_non_allowlisted_name() -> None:
    config = MCPRuntimeConfig((MCPServerConfig(
        name="fake", command=sys.executable, args=("-u", "-c", FAKE_SERVER),
        allowed_tools=frozenset({"echo"}), request_timeout=2, startup_timeout=2),))
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.COMPUTER_CONTROL)
    registry = ToolRegistry(permissions)
    registry.register(MCPCallTool(config))
    result = json.loads(registry.execute("mcp_call", server_name="fake", tool_name="unknown", arguments_json="{}"))
    assert result["ok"] is False
    assert "not allow-listed" in result["error"]


def test_planning_catalog_exposes_configured_mcp_tool_names(tmp_path: Path) -> None:
    mcp_path = tmp_path / "mcp.json"
    mcp_path.write_text(json.dumps({"schema_version": 1, "servers": [
        {"name": "rea", "transport": "stdio", "command": sys.executable,
         "args": [], "enabled": True,
         "allowed_tools": ["open_binary", "function", "strings"]}
    ]}), encoding="utf-8")
    controller = ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit.jsonl",
        mcp_config_file=mcp_path,
    )

    description = controller.planning_catalog()["mcp_call"]["description"]

    assert "rea: function, open_binary, strings" in description
    assert "advertised by the live server" in description
