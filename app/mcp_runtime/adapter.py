"""Bridge configured MCP servers into Lumen's existing ToolRegistry.

Only operator-configured servers and explicitly allow-listed tool names are
callable. Calls pass through the COMPUTER_CONTROL permission gate and controller
checkpoint before the external process is invoked.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.mcp_runtime.stdio import MCPError, MCPServerConfig, MCPStdioClient


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


async def call_mcp_tool(server: MCPServerConfig, tool_name: str,
                        arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Run one verified, allow-listed MCP call and always close its process."""
    if tool_name not in server.allowed_tools:
        raise MCPError(f"Tool '{tool_name}' is not allow-listed for server '{server.name}'")
    client = MCPStdioClient(server)
    try:
        await client.start()
        return await client.call_tool(tool_name, arguments)
    finally:
        await client.close()


__all__ = ["MCPRuntimeConfig", "call_mcp_tool"]
