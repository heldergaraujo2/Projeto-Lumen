from __future__ import annotations

import json

from app.core.bridge import RequestState, ToolCallingBridge
from app.core.agent import Agent
from app.memory.store import MemoryStore
from app.planner.models import Plan, PlanStatus, PlannedTask
from app.security.permissions import PermissionManager
from app.tools.control import ToolsController
from app.tools.protocol import ToolCall, ToolProtocolError


def make_controller(tmp_path):
    return ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
    )


def test_tool_call_gateway_executes_read_through_plan(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "hello.txt").write_text("Olá Lumen", encoding="utf-8")
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws), writable=False)
    controller.grant_permission("READ")

    result = controller.run_tool_call(
        ToolCall("read_file", {"path": "hello.txt"}, call_id="c-read", reason="ler arquivo")
    )

    assert result.ok is True
    assert result.call_id == "c-read"
    assert result.data["execution_report"]["status"] == "COMPLETED"


def test_tool_call_gateway_denies_missing_permission(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "hello.txt").write_text("conteúdo", encoding="utf-8")
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws))

    result = controller.run_tool_call(ToolCall("read_file", {"path": "hello.txt"}, call_id="c-deny"))

    assert result.ok is False
    assert "READ" in (result.error or "")


def test_tool_call_gateway_preserves_checkpoint(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("WRITE")

    result = controller.run_tool_call(
        ToolCall("create_file", {"path": "novo.txt", "content": "x"}, call_id="c-write")
    )

    assert result.ok is False
    assert result.data["awaiting_approval"] is True
    assert controller.has_pending is True
    assert not (ws / "novo.txt").exists()


def test_tool_call_protocol_rejects_unknown_parameter_before_plan(tmp_path):
    controller = make_controller(tmp_path)
    with __import__("pytest").raises(ToolProtocolError):
        controller.validate_tool_call(
            ToolCall("read_file", {"path": "x.txt", "extra": "x"})
        )


def test_bridge_accepts_structured_tool_call(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "hello.txt").write_text("ok", encoding="utf-8")
    controller = make_controller(tmp_path)
    controller.add_workspace(str(ws))
    controller.grant_permission("READ")

    bridge = ToolCallingBridge(None, controller)
    outcome = bridge.process_tool_call(
        {"tool": "read_file", "parameters": {"path": "hello.txt"}, "call_id": "bridge-1"}
    )

    assert outcome.state is RequestState.EXECUTED_UNVERIFIED
    assert outcome.execution_evidence
    assert outcome.execution_evidence[0].result_sha256
    assert outcome.plan_id


def test_agent_executes_tool_plan_through_controller_registry(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "source.txt"
    source.write_text("conteúdo real", encoding="utf-8")
    permissions = PermissionManager()
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
    )
    controller.add_workspace(str(workspace), writable=False)
    controller.grant_permission("READ")
    agent = Agent(
        provider=__import__("app.ai.mock", fromlist=["MockProvider"]).MockProvider(),
        memory=MemoryStore(tmp_path / "conversation.json"),
        permissions=permissions,
    )
    agent.set_tools_controller(controller)
    plan = Plan(
        id="PLN-AGENT-TOOLS", objective="ler arquivo", status=PlanStatus.READY,
        tasks=(PlannedTask(
            id="T1", description="ler source.txt", order=1,
            tool="read_file", parameters={"path": str(source)},
        ),),
    )

    report = agent.execute_plan(plan)

    assert report.status is PlanStatus.COMPLETED
    result = json.loads(report.task_run("T1").result)
    assert result["ok"] is True
    assert result["data"]["content"] == "conteúdo real"
