from __future__ import annotations

import asyncio
import sys

import pytest

from app.mcp_runtime import MCPError, MCPServerConfig, MCPStdioClient
from app.mcp_runtime.stdio import _child_environment


FAKE_SERVER = r'''import json, sys
for line in sys.stdin:
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "echo", "description": "test echo", "inputSchema": {"type": "object"}}]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": json.dumps(msg.get("params", {}).get("arguments", {}))}], "isError": False}
    elif "id" not in msg:
        continue
    else:
        result = {}
    if "id" in msg:
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
'''


def config(*, allowed_tools=frozenset({"echo"})) -> MCPServerConfig:
    return MCPServerConfig(
        name="fake",
        command=sys.executable,
        args=("-u", "-c", FAKE_SERVER),
        allowed_tools=allowed_tools,
        request_timeout=2,
        startup_timeout=2,
    )


def test_mcp_stdio_handshake_list_and_call() -> None:
    async def run() -> None:
        client = MCPStdioClient(config())
        try:
            await client.start()
            tools = await client.list_tools()
            assert [tool.name for tool in tools] == ["echo"]
            result = await client.call_tool("echo", {"message": "ok"})
            assert result["isError"] is False
            assert '"message": "ok"' in result["content"][0]["text"]
        finally:
            await client.close()
    asyncio.run(run())


def test_mcp_stdio_denies_non_allowlisted_tool() -> None:
    async def run() -> None:
        client = MCPStdioClient(config(allowed_tools=frozenset()))
        try:
            await client.start()
            with pytest.raises(MCPError, match="not allow-listed"):
                await client.call_tool("echo", {})
        finally:
            await client.close()
    asyncio.run(run())


def test_mcp_stdio_rejects_unadvertised_tool() -> None:
    async def run() -> None:
        client = MCPStdioClient(config(allowed_tools=frozenset({"not-real"})))
        try:
            await client.start()
            with pytest.raises(MCPError, match="not advertised"):
                await client.call_tool("not-real", {})
        finally:
            await client.close()
    asyncio.run(run())


def test_mcp_child_environment_does_not_inherit_unrelated_secrets() -> None:
    env = _child_environment(
        {
            "PATH": "/safe/bin",
            "HOME": "/home/test",
            "LUMEN_API_KEY": "must-not-leak",
            "OPENAI_API_KEY": "must-not-leak-either",
            "CUSTOM_PARENT_SECRET": "must-not-leak",
        },
        {"MCP_TOKEN": "explicitly-configured"},
    )

    assert env["PATH"] == "/safe/bin"
    assert env["HOME"] == "/home/test"
    assert env["MCP_TOKEN"] == "explicitly-configured"
    assert "LUMEN_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "CUSTOM_PARENT_SECRET" not in env
