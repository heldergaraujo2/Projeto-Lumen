"""External MCP adapter registered in Lumen's permission-gated tool registry."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.mcp_runtime.adapter import MCPRuntimeConfig, call_mcp_tool
from app.mcp_runtime.stdio import MCPError
from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult
from app.tools.filesystem import FilesystemAudit


class MCPCallTool(StructuredTool):
    name = "mcp_call"
    description = (
        "Executa uma ferramenta de um servidor MCP local previamente configurado e allow-listado. "
        "Exige COMPUTER_CONTROL e checkpoint de aprovação antes de qualquer chamada."
    )
    required_permission = PermissionLevel.COMPUTER_CONTROL

    def __init__(self, config: MCPRuntimeConfig, audit: FilesystemAudit | None = None) -> None:
        self._config = config
        self._audit = audit

    def run(self, *, server_name: str, tool_name: str, arguments_json: str = "{}") -> ToolResult:
        if not isinstance(server_name, str) or not server_name.strip():
            return ToolResult(False, error="server_name must be a non-empty string")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return ToolResult(False, error="tool_name must be a non-empty string")
        if not isinstance(arguments_json, str) or len(arguments_json.encode("utf-8")) > 64_000:
            return ToolResult(False, error="arguments_json must be text no larger than 64 KB")
        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError:
            return ToolResult(False, error="arguments_json is not valid JSON")
        if not isinstance(arguments, dict):
            return ToolResult(False, error="arguments_json must decode to a JSON object")
        try:
            server = self._config.server(server_name)
            result = asyncio.run(call_mcp_tool(server, tool_name, arguments))
        except (MCPError, ValueError, OSError, RuntimeError) as exc:
            if self._audit is not None:
                self._audit.record(
                    tool=self.name, operation="mcp_call", requested_path=None,
                    success=False, error=f"{type(exc).__name__}: {str(exc)[:240]}",
                    mcp_server=server_name, mcp_tool=tool_name,
                )
            return ToolResult(False, error=f"MCP call failed: {type(exc).__name__}: {str(exc)[:240]}")
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 64_000:
            if self._audit is not None:
                self._audit.record(
                    tool=self.name, operation="mcp_call", requested_path=None,
                    success=False, error="MCP response exceeded 64 KB",
                    mcp_server=server_name, mcp_tool=tool_name,
                )
            return ToolResult(False, error="MCP response exceeded the 64 KB output limit")
        if self._audit is not None:
            self._audit.record(
                tool=self.name, operation="mcp_call", requested_path=None,
                success=True, mcp_server=server_name, mcp_tool=tool_name,
            )
        return ToolResult(True, data={"server": server_name, "tool": tool_name, "result": result})


__all__ = ["MCPCallTool"]
