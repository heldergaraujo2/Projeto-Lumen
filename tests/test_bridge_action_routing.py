"""Regressions for explicit action routing in the chat/tool bridge."""
from __future__ import annotations

from types import SimpleNamespace

from app.core.bridge import (
    RequestState,
    ToolCallingBridge,
    _is_explicit_action_request,
)


class MemoryStub:
    def __init__(self):
        self.messages = []

    def add_message(self, role, content):
        self.messages.append((role, content))


class AgentStub:
    def __init__(self, kinds):
        self.kinds = list(kinds)
        self.memory = MemoryStub()
        self.plan_requests = []
        self.chat_requests = []

    def request_tool_plan(self, text, catalog, **options):
        self.plan_requests.append((text, catalog, options))
        kind = self.kinds.pop(0)
        return SimpleNamespace(kind=kind, plan=SimpleNamespace(id="plan-test"))

    def send_message(self, text, on_delta=None):
        self.chat_requests.append(text)
        return "Resposta conversacional."


class ControllerStub:
    def planning_catalog(self):
        return {"read_file": {"description": "read"}}


def test_explicit_file_and_web_actions_are_detected():
    assert _is_explicit_action_request("Leia o arquivo docs/README.md")
    assert _is_explicit_action_request("Pesquise na internet sobre REA")
    assert _is_explicit_action_request("Execute os testes pytest")


def test_generic_unrestricted_access_request_is_not_an_action():
    assert not _is_explicit_action_request("Quero acesso irrestrito a todas as ferramentas")
    assert not _is_explicit_action_request("Como posso ler um arquivo?")
    assert not _is_explicit_action_request("Não leia o arquivo docs/README.md")


def test_explicit_action_retries_planner_and_never_falls_back_to_chat():
    agent = AgentStub(["conversation", "conversation"])
    bridge = ToolCallingBridge(agent, ControllerStub())

    outcome = bridge.process("Leia o arquivo docs/README.md")

    assert outcome.state is RequestState.PLAN_INVALID
    assert "Nenhuma ação foi executada" in outcome.text
    assert len(agent.plan_requests) == 2
    assert agent.chat_requests == []
    assert "ROTEAMENTO OBRIGATÓRIO" in agent.plan_requests[1][0]
    assert agent.plan_requests[1][2]["require_plan"] is True


def test_pure_conversation_still_uses_chat_path():
    agent = AgentStub(["conversation"])
    bridge = ToolCallingBridge(agent, ControllerStub())

    outcome = bridge.process("Olá, como você está?")

    assert outcome.state is RequestState.CONVERSATIONAL
    assert outcome.text == "Resposta conversacional."
    assert len(agent.plan_requests) == 1
    assert agent.chat_requests == ["Olá, como você está?"]
