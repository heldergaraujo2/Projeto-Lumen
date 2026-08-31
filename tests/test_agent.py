"""Testes do Agent Core."""
from __future__ import annotations

import pytest

from app.ai.mock import MockProvider
from app.ai.provider import AIProvider, ProviderError
from app.core.agent import Agent, AgentError
from app.memory.store import MemoryStore
from app.security.permissions import PermissionDeniedError, PermissionLevel, PermissionManager


def make_agent(tmp_path, provider=None, permissions=None) -> Agent:
    memory = MemoryStore(tmp_path / "conversation.json")
    return Agent(
        provider=provider or MockProvider(),
        memory=memory,
        permissions=permissions or PermissionManager(),
    )


def test_agent_conversation_round_trip(tmp_path):
    """5. Agent conversa com o provider e registra tudo na memória."""
    agent = make_agent(tmp_path)
    reply = agent.send_message("Olá Lumen")

    assert reply.strip()
    messages = agent.memory.all_messages()
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "Olá Lumen"
    assert messages[1].content == reply


def test_agent_rejects_empty_message(tmp_path):
    with pytest.raises(ValueError):
        make_agent(tmp_path).send_message("   ")


def test_agent_wraps_provider_failures(tmp_path):
    class FailingProvider(AIProvider):
        name = "failing"

        def generate(self, message, context=None):
            raise ProviderError("sem rede")

    agent = make_agent(tmp_path, provider=FailingProvider())
    with pytest.raises(AgentError):
        agent.send_message("oi")

    # A mensagem do usuário permanece salva mesmo com o provedor caído.
    assert agent.memory.count == 1
    assert agent.memory.all_messages()[0].role == "user"


def test_agent_sends_prior_context_to_provider(tmp_path):
    class RecordingProvider(AIProvider):
        name = "recording"

        def __init__(self):
            self.calls: list[tuple[str, list[dict]]] = []

        def generate(self, message, context=None):
            self.calls.append((message, [dict(item) for item in context or []]))
            return "ok"

    provider = RecordingProvider()
    agent = make_agent(tmp_path, provider=provider)
    agent.send_message("primeira")
    agent.send_message("segunda")

    message, context = provider.calls[1]
    assert message == "segunda"
    assert [item["content"] for item in context] == ["primeira", "ok"]


def test_agent_requires_chat_permission(tmp_path):
    permissions = PermissionManager()
    permissions.revoke(PermissionLevel.CHAT)
    agent = make_agent(tmp_path, permissions=permissions)

    with pytest.raises(PermissionDeniedError):
        agent.send_message("oi")
    assert agent.memory.count == 0
