from __future__ import annotations

import pytest

from app.security.permissions import PermissionLevel, PermissionManager
from app.tools.base import StructuredTool, ToolRegistry, ToolResult
from app.tools.protocol import (
    ParameterDefinition, ToolCall, ToolDefinition, ToolExecutionResult,
    ToolProtocol, ToolProtocolError,
)


class EchoTool(StructuredTool):
    name = "echo"
    description = "Repete um texto."
    required_permission = PermissionLevel.READ

    def run(self, **kwargs):
        return ToolResult(ok=True, data={"text": kwargs["text"]})


class BrokenTool(StructuredTool):
    name = "broken"
    description = "Falha controlada."
    required_permission = PermissionLevel.READ

    def run(self, **kwargs):
        raise RuntimeError("falha de teste")


def protocol():
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.READ)
    registry = ToolRegistry(permissions)
    registry.register(EchoTool())
    registry.register(BrokenTool())
    definitions = {
        "echo": ToolDefinition("echo", "Repete um texto.",
            (ParameterDefinition("text", "string", True),)),
        "broken": ToolDefinition("broken", "Falha controlada."),
    }
    def trusted_test_executor(call):
        try:
            import json
            raw = registry.execute(call.tool, **dict(call.parameters))
            decoded = json.loads(raw)
            return ToolExecutionResult(
                call_id=call.call_id, tool=call.tool,
                ok=bool(decoded.get("ok", True)),
                data=dict(decoded.get("data") or {}),
                error=decoded.get("error"),
            )
        except Exception as exc:
            return ToolExecutionResult(call_id=call.call_id, tool=call.tool,
                                       ok=False, error=str(exc))

    return ToolProtocol(registry, definitions, executor=trusted_test_executor)


def test_tool_call_round_trip():
    call = ToolCall.from_dict({"tool": "echo", "parameters": {"text": "Olá"},
                               "call_id": "c1", "reason": "teste"})
    assert call.to_dict()["tool"] == "echo"
    assert call.parameters["text"] == "Olá"


def test_unknown_tool_rejected_before_execution():
    with pytest.raises(ToolProtocolError):
        protocol().execute(ToolCall("missing", {}))


def test_unknown_parameter_rejected():
    with pytest.raises(ToolProtocolError):
        protocol().execute(ToolCall("echo", {"text": "ok", "extra": "x"}))


def test_required_and_type_validation():
    p = protocol()
    with pytest.raises(ToolProtocolError):
        p.execute(ToolCall("echo", {}))
    with pytest.raises(ToolProtocolError):
        p.execute(ToolCall("echo", {"text": 123}))


def test_execution_returns_stable_result():
    result = protocol().execute(ToolCall("echo", {"text": "Olá"}, call_id="c7"))
    assert isinstance(result, ToolExecutionResult)
    assert result.to_dict() == {"call_id": "c7", "tool": "echo", "ok": True,
                                "data": {"text": "Olá"}, "error": None}


def test_execution_failure_is_normalized():
    result = protocol().execute(ToolCall("broken", {}, call_id="c8"))
    assert result.ok is False
    assert result.call_id == "c8"
    assert "falha de teste" in (result.error or "")


def test_permission_still_has_authority():
    permissions = PermissionManager()
    registry = ToolRegistry(permissions)
    registry.register(EchoTool())
    p = ToolProtocol(registry, {"echo": ToolDefinition(
        "echo", "Repete um texto.",
        (ParameterDefinition("text", "string", True),))})
    result = p.execute(ToolCall("echo", {"text": "bloqueado"}))
    assert result.ok is False
    assert "READ" in (result.error or "")


def test_call_rejects_unknown_envelope_fields():
    with pytest.raises(ToolProtocolError):
        ToolCall.from_dict({"tool": "echo", "parameters": {}, "execute_now": True})


def test_definition_rejects_duplicate_parameters():
    with pytest.raises(ToolProtocolError):
        ToolDefinition("echo", "x", (
            ParameterDefinition("x", "string"), ParameterDefinition("x", "string")))


def test_execution_without_gateway_fails_closed():
    permissions = PermissionManager()
    registry = ToolRegistry(permissions)
    registry.register(EchoTool())
    p = ToolProtocol(registry, {"echo": ToolDefinition(
        "echo", "Repete um texto.",
        (ParameterDefinition("text", "string", True),))})
    with pytest.raises(ToolProtocolError):
        p.execute(ToolCall("echo", {"text": "blocked"}))
