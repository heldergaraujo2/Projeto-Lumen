"""Minimal JSON-RPC 2.0 MCP stdio client with explicit tool allow-listing.

No shell is used. The command and arguments are operator-configured; a model
cannot start arbitrary processes. This transport is intentionally separate from
Lumen's permission, policy, checkpoint, audit, and post-action verification layers.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


class MCPError(RuntimeError):
    """MCP transport, protocol, or authorization failure."""


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    command: str
    args: tuple[str, ...] = ()
    cwd: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    allowed_tools: frozenset[str] = frozenset()
    request_timeout: float = 30.0
    startup_timeout: float = 15.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("MCP server name cannot be empty")
        if not self.command.strip():
            raise ValueError("MCP server command cannot be empty")
        if self.request_timeout <= 0 or self.startup_timeout <= 0:
            raise ValueError("MCP timeouts must be positive")
        if any(not name or name.strip() != name for name in self.allowed_tools):
            raise ValueError("allowed tool names must be non-empty and trimmed")


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str = ""
    input_schema: Mapping[str, Any] = field(default_factory=dict)


class MCPStdioClient:
    """Async MCP stdio client supporting initialize, tools/list and tools/call."""

    PROTOCOL_VERSION = "2025-06-18"

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 1
        self._write_lock = asyncio.Lock()
        self._started = False
        self._tools: dict[str, MCPTool] = {}

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self, *, client_name: str = "Lumen", client_version: str = "0.7.0") -> None:
        if self._started and self.is_running:
            return
        env = os.environ.copy()
        # Explicit overrides only; no secrets are logged or echoed.
        env.update({str(k): str(v) for k, v in self.config.env.items()})
        try:
            self._process = await asyncio.create_subprocess_exec(
                self.config.command,
                *self.config.args,
                cwd=self.config.cwd,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except (OSError, ValueError) as exc:
            raise MCPError(f"Could not start configured MCP server '{self.config.name}' ({type(exc).__name__})") from exc
        self._reader_task = asyncio.create_task(self._read_responses(), name=f"mcp-reader:{self.config.name}")
        try:
            result = await asyncio.wait_for(
                self._request("initialize", {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": client_name, "version": client_version},
                }),
                timeout=self.config.startup_timeout,
            )
            if not isinstance(result, dict) or "protocolVersion" not in result:
                raise MCPError("MCP initialize response is missing protocolVersion")
            await self._notify("notifications/initialized")
            self._started = True
        except Exception:
            await self.close()
            raise

    async def list_tools(self, *, refresh: bool = False) -> tuple[MCPTool, ...]:
        self._require_started()
        if self._tools and not refresh:
            return tuple(self._tools.values())
        result = await asyncio.wait_for(self._request("tools/list", {}), self.config.request_timeout)
        raw_tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(raw_tools, list):
            raise MCPError("MCP tools/list response has no tools array")
        discovered: dict[str, MCPTool] = {}
        for item in raw_tools:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            name = item["name"]
            if not name or name.strip() != name:
                continue
            schema = item.get("inputSchema", {})
            discovered[name] = MCPTool(
                name=name,
                description=str(item.get("description", "")),
                input_schema=schema if isinstance(schema, dict) else {},
            )
        self._tools = discovered
        return tuple(discovered.values())

    async def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Call only a configured, explicitly allow-listed tool; never auto-approve."""
        self._require_started()
        if name not in self.config.allowed_tools:
            raise MCPError(f"Tool '{name}' is not allow-listed for MCP server '{self.config.name}'")
        tools = await self.list_tools()
        if name not in {tool.name for tool in tools}:
            raise MCPError(f"Tool '{name}' was not advertised by MCP server '{self.config.name}'")
        result = await asyncio.wait_for(
            self._request("tools/call", {"name": name, "arguments": dict(arguments or {})}),
            timeout=self.config.request_timeout,
        )
        if not isinstance(result, dict):
            raise MCPError("MCP tools/call response is not an object")
        if result.get("isError") is True:
            raise MCPError(f"MCP tool '{name}' reported an execution error")
        return result

    async def close(self, *, terminate_timeout: float = 2.0) -> None:
        process, self._process = self._process, None
        self._started = False
        self._tools.clear()
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=terminate_timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        task, self._reader_task = self._reader_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        for future in self._pending.values():
            if not future.done():
                future.set_exception(MCPError("MCP client closed"))
        self._pending.clear()

    def _require_started(self) -> None:
        if not self._started or not self.is_running:
            raise MCPError(f"MCP server '{self.config.name}' is not started")

    async def _send(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.returncode is not None:
            raise MCPError(f"MCP server '{self.config.name}' is not running")
        wire = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\\n"
        async with self._write_lock:
            process.stdin.write(wire)
            await process.stdin.drain()

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            message = await future
        finally:
            self._pending.pop(request_id, None)
        if "error" in message:
            error = message.get("error")
            code = error.get("code") if isinstance(error, dict) else "unknown"
            raise MCPError(f"MCP method '{method}' failed (code={code})")
        result = message.get("result")
        if not isinstance(result, dict):
            raise MCPError(f"MCP method '{method}' returned no result object")
        return result

    async def _notify(self, method: str) -> None:
        await self._send({"jsonrpc": "2.0", "method": method})

    async def _read_responses(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(message, dict) or "id" not in message:
                    continue  # notifications do not satisfy requests
                request_id = message.get("id")
                future = self._pending.get(request_id) if isinstance(request_id, int) else None
                if future is not None and not future.done():
                    future.set_result(message)
        except asyncio.CancelledError:
            raise
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(MCPError(f"MCP server '{self.config.name}' closed its output"))


__all__ = ["MCPError", "MCPServerConfig", "MCPStdioClient", "MCPTool"]
