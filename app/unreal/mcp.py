"""Controlled MCP client for Unreal Editor integrations.

This module speaks the 2025-era MCP Streamable HTTP handshake used by the
Unreal Engine ModelContextProtocol plugin. It is intentionally transport-only:
authorization, approvals and physical Computer Control remain outside this
client.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


class UnrealMCPError(RuntimeError):
    """Base error for Unreal MCP transport/protocol failures."""


class UnrealMCPProtocolError(UnrealMCPError):
    """The server returned a JSON-RPC error or malformed MCP response."""


@dataclass(frozen=True)
class MCPResponse:
    result: Any = None
    error: dict[str, Any] | None = None
    raw: Any = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


class UnrealMCPClient:
    """Small dependency-free MCP Streamable HTTP client.

    The client only supports loopback HTTP by default. It never executes
    Unreal commands itself; callers must apply Lumen policy/approval gates
    before invoking mutating MCP tools.
    """

    PROTOCOL_VERSION = "2025-06-18"

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8000/mcp",
        *,
        timeout: float = 15.0,
        opener: Callable[..., Any] | None = None,
        allow_non_loopback: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen
        self.session_id: str | None = None
        self._session_initialized = False
        self._next_id = 1
        self._validate_endpoint(allow_non_loopback)

    def _validate_endpoint(self, allow_non_loopback: bool) -> None:
        parsed = urllib.parse.urlparse(self.endpoint)
        if parsed.scheme != "http" or not parsed.hostname or parsed.path != "/mcp":
            raise ValueError("Unreal MCP endpoint must be an HTTP /mcp URL")
        if allow_non_loopback:
            return
        try:
            is_loopback = ipaddress_is_loopback(parsed.hostname)
        except ValueError:
            is_loopback = parsed.hostname.lower() == "localhost"
        if not is_loopback:
            raise ValueError("Unreal MCP endpoint must be loopback by default")

    def initialize(self, *, client_name: str = "Lumen", client_version: str = "0.6.8") -> MCPResponse:
        response = self._request(
            "initialize",
            {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": client_version},
            },
        )
        if not response.is_error:
            self._session_initialized = True
        return response

    def notify_initialized(self) -> int:
        return self._notification("notifications/initialized")

    def list_tools(self) -> MCPResponse:
        self._ensure_session()
        return self._request("tools/list", {})

    def list_toolsets(self) -> MCPResponse:
        return self.call_tool("list_toolsets", {})

    def describe_toolset(self, toolset_name: str) -> MCPResponse:
        return self.call_tool("describe_toolset", {"toolset_name": toolset_name})

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> MCPResponse:
        if not tool_name or tool_name != tool_name.strip():
            raise ValueError("tool_name must be non-empty")
        self._ensure_session()
        return self._request(
            "tools/call",
            {"name": "call_tool", "arguments": {"tool_name": tool_name, "arguments": arguments or {}}},
        )

    def call_toolset_tool(
        self,
        toolset_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPResponse:
        if not toolset_name.strip() or not tool_name.strip():
            raise ValueError("toolset_name and tool_name are required")
        self._ensure_session()
        return self._request(
            "tools/call",
            {
                "name": "call_tool",
                "arguments": {
                    "toolset_name": toolset_name,
                    "tool_name": tool_name,
                    "arguments": arguments or {},
                },
            },
        )

    def _ensure_session(self) -> None:
        if self._session_initialized:
            return
        response = self.initialize()
        if response.is_error:
            raise UnrealMCPProtocolError(f"MCP initialize failed: {response.error}")
        self.notify_initialized()

    def _notification(self, method: str) -> int:
        payload = {"jsonrpc": "2.0", "method": method}
        request = self._build_request(payload)
        with self._opener(request, timeout=self.timeout) as response:
            return getattr(response, "status", response.getcode())

    def _request(self, method: str, params: dict[str, Any]) -> MCPResponse:
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        request = self._build_request(payload)
        try:
            with self._opener(request, timeout=self.timeout) as response:
                if getattr(response, "headers", None) is not None:
                    session = response.headers.get("Mcp-Session-Id")
                    if session:
                        self.session_id = session
                body = response.read().decode("utf-8")
                document = parse_mcp_body(body)
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise UnrealMCPError(f"Unreal MCP request failed: {exc}") from exc
        except OSError as exc:
            raise UnrealMCPError(f"Unreal MCP transport failed: {exc}") from exc

        if not isinstance(document, dict) or document.get("jsonrpc") != "2.0":
            raise UnrealMCPProtocolError("invalid JSON-RPC response")
        if "error" in document:
            return MCPResponse(error=document["error"], raw=document)
        if "result" not in document:
            raise UnrealMCPProtocolError("JSON-RPC response has neither result nor error")
        return MCPResponse(result=document["result"], raw=document)

    def _build_request(self, payload: dict[str, Any]) -> urllib.request.Request:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.PROTOCOL_VERSION,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )


def ipaddress_is_loopback(host: str) -> bool:
    import ipaddress

    return ipaddress.ip_address(host).is_loopback


def parse_mcp_body(body: str) -> dict[str, Any]:
    """Parse either JSON response or the SSE data envelope used by Unreal MCP."""
    text = body.strip()
    if not text:
        raise UnrealMCPProtocolError("empty MCP response")
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data = line[5:].strip()
            if data:
                try:
                    value = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise UnrealMCPProtocolError("invalid SSE JSON payload") from exc
                if isinstance(value, dict):
                    events.append(value)
    if not events:
        raise UnrealMCPProtocolError("unsupported MCP response body")
    return events[-1]
