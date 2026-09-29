from __future__ import annotations

import json

import pytest

from app.unreal.mcp import (
    MCPResponse,
    UnrealMCPClient,
    UnrealMCPError,
    UnrealMCPProtocolError,
    parse_mcp_body,
)


class FakeResponse:
    def __init__(self, payload, *, status=200, session=None):
        self.status = status
        self._payload = payload
        self.headers = {"Mcp-Session-Id": session} if session else {}

    def read(self):
        return self._payload.encode()

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        return self.responses.pop(0)


def rpc(result, *, session=None):
    return FakeResponse(json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}), session=session)


def test_initialize_captures_session_and_uses_mcp_headers():
    opener = FakeOpener([rpc({"protocolVersion": "2025-06-18"}, session="abc")])
    client = UnrealMCPClient(opener=opener)
    response = client.initialize()

    assert response.result["protocolVersion"] == "2025-06-18"
    assert client.session_id == "abc"
    request = opener.requests[0][0]
    assert request.get_header("Mcp-session-id") is None
    assert request.headers["Mcp-session-id"] == "abc" if "Mcp-session-id" in request.headers else True


def test_second_request_reuses_session_id():
    opener = FakeOpener([
        rpc({"protocolVersion": "2025-06-18"}, session="abc"),
        rpc({"tools": []}),
    ])
    client = UnrealMCPClient(opener=opener)
    client.initialize()
    client.list_tools()
    request = opener.requests[1][0]
    assert request.headers["Mcp-session-id"] == "abc"


def test_sse_response_is_parsed():
    body = 'event: message\\ndata: {"jsonrpc":"2.0","id":2,"result":{"ok":true}}\\n\\n'
    assert parse_mcp_body(body)["result"]["ok"] is True


def test_json_rpc_error_is_returned_without_being_hidden():
    opener = FakeOpener([FakeResponse(json.dumps({
        "jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "bad params"}
    }))])
    response = UnrealMCPClient(opener=opener).initialize()
    assert response.is_error
    assert response.error["code"] == -32602


def test_non_loopback_is_rejected_by_default():
    with pytest.raises(ValueError, match="loopback"):
        UnrealMCPClient("http://example.com/mcp")


def test_malformed_body_is_rejected():
    with pytest.raises(UnrealMCPProtocolError):
        parse_mcp_body("not MCP")


def test_transport_error_is_wrapped():
    class Broken:
        def __call__(self, request, timeout):
            raise TimeoutError("timeout")
    with pytest.raises(UnrealMCPError, match="failed"):
        UnrealMCPClient(opener=Broken()).initialize()


def test_call_toolset_tool_uses_unprefixed_tool_name():
    opener = FakeOpener([rpc({"content": []})])
    client = UnrealMCPClient(opener=opener)
    client.call_toolset_tool(
        "SlateInspectorToolset.SlateInspectorToolset",
        "Snapshot",
        {"ref": "", "maxDepth": 12},
    )
    request = opener.requests[0][0]
    payload = json.loads(request.data.decode())
    assert payload["params"]["name"] == "call_tool"
    assert payload["params"]["arguments"]["tool_name"] == "call_tool"
    assert payload["params"]["arguments"]["arguments"]["tool_name"] == "Snapshot"
