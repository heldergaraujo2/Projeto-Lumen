"""Bridge configured MCP servers into Lumen's existing ToolRegistry.

Only operator-configured servers and explicitly allow-listed tool names are
callable. Calls pass through the COMPUTER_CONTROL permission gate and controller
checkpoint before the external process is invoked.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.mcp_runtime.stdio import MCPError, MCPServerConfig, MCPStdioClient
from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult
from app.tools.audit_log import FilesystemAudit


@dataclass(frozen=True)
class MCPRuntimeConfig:
    servers: tuple[MCPServerConfig, ...] = ()

    @classmethod
    def load(cls, path: Path | str) -> "MCPRuntimeConfig":
        config_path = Path(path)
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"MCP config could not be read ({type(exc).__name__})") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("MCP config schema_version must be 1")
        raw_servers = raw.get("servers", [])
        if not isinstance(raw_servers, list):
            raise ValueError("MCP config servers must be an array")
        servers: list[MCPServerConfig] = []
        names: set[str] = set()
        for item in raw_servers:
            if not isinstance(item, dict) or item.get("enabled") is not True:
                continue
            if item.get("transport", "stdio") != "stdio":
                raise ValueError("Only stdio MCP transport is currently supported")
            name = item.get("name")
            command = item.get("command")
            args = item.get("args", [])
            allowed = item.get("allowed_tools", [])
            env = item.get("env", {})
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ValueError("Enabled MCP servers need unique non-empty names")
            if not isinstance(command, str) or not command.strip():
                raise ValueError(f"MCP server {name!r} needs a command")
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise ValueError(f"MCP server {name!r} args must be an array of strings")
            if not isinstance(allowed, list) or not all(isinstance(tool, str) and tool.strip() for tool in allowed):
                raise ValueError(f"MCP server {name!r} allowed_tools must be non-empty strings")
            if len(set(allowed)) != len(allowed):
                raise ValueError(f"MCP server {name!r} has duplicate allow-listed tools")
            if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
                raise ValueError(f"MCP server {name!r} env must map strings to strings")
            if not allowed:
                continue
            servers.append(MCPServerConfig(
                name=name, command=command, args=tuple(args),
                cwd=item.get("cwd") if isinstance(item.get("cwd"), str) else None,
                env=env, allowed_tools=frozenset(allowed),
                request_timeout=float(item.get("request_timeout_seconds", 30)),
                startup_timeout=float(item.get("startup_timeout_seconds", 15)),
            ))
            names.add(name)
        return cls(tuple(servers))

    def server(self, name: str) -> MCPServerConfig:
        for server in self.servers:
            if server.name == name:
                return server
        raise MCPError(f"MCP server '{name}' is not configured and enabled")

    @property
    def has_allowlisted_tools(self) -> bool:
        return any(server.allowed_tools for server in self.servers)


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
            if tool_name not in server.allowed_tools:
                raise MCPError(f"Tool '{tool_name}' is not allow-listed for server '{server_name}'")
            result = asyncio.run(self._execute(server, tool_name, arguments))
        except (MCPError, ValueError, OSError, RuntimeError) as exc:
            if self._audit is not None:
                self._audit.record(tool=self.name, operation="mcp_call", success=False,
                                   error=f"{type(exc).__name__}: {str(exc)[:240]}",
                                   mcp_server=server_name, mcp_tool=tool_name)
            return ToolResult(False, error=f"MCP call failed: {type(exc).__name__}: {str(exc)[:240]}")
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 64_000:
            return ToolResult(False, error="MCP response exceeded the 64 KB output limit")
        if self._audit is not None:
            self._audit.record(tool=self.name, operation="mcp_call", success=True,
                               mcp_server=server_name, mcp_tool=tool_name)
        return ToolResult(True, data={"server": server_name, "tool": tool_name, "result": result})

    async def _execute(self, server: MCPServerConfig, tool_name: str,
                       arguments: Mapping[str, Any]) -> dict[str, Any]:
        client = MCPStdioClient(server)
        try:
            await client.start()
            return await client.call_tool(tool_name, arguments)
        finally:
            await client.close()


__all__ = ["MCPCallTool", "MCPRuntimeConfig"]
