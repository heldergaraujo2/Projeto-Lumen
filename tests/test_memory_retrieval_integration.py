"""Regressao: recuperacao relevante da memoria no fluxo real do Agent."""
from __future__ import annotations

from app.ai.provider import AIProvider
from app.core.agent import Agent
from app.memory.records import MemoryKind
from app.memory.store import MemoryStore
from app.memory.system import MemorySystem
from app.security.permissions import PermissionManager


class RecordingProvider(AIProvider):
    name = "recording"

    def __init__(self):
        self.calls = []

    def generate(self, message, context=None):
        self.calls.append({
            "message": message,
            "context": [dict(item) for item in (context or [])],
        })
        return "Resposta de teste."


def test_relevant_search_ranks_exact_topic_above_noise(tmp_path):
    memory = MemoryStore(tmp_path / "conversation.json")
    memory.add_message("user", "Hoje quero falar sobre receitas de bolo.")
    memory.add_message("assistant", "Posso ajudar com receitas.")
    memory.add_message("user", "Quem é o criador da Lumen?")
    memory.add_message("assistant", "A conversa não confirmou o nome do criador.")

    results = memory.search_relevant("quem é seu criador?", limit=3)

    assert results
    assert any("criador" in message.content.lower() for message in results)
    assert all("receitas" not in message.content.lower() for message in results)


def test_agent_includes_relevant_persistent_conversation_in_provider_context(tmp_path):
    store = MemoryStore(tmp_path / "conversation.json")
    store.add_message("user", "Quem é o criador da Lumen?")
    store.add_message("assistant", "Ainda não confirmamos o nome do criador da Lumen.")
    store.add_message("user", "Falamos também sobre receitas de bolo.")
    provider = RecordingProvider()
    agent = Agent(provider=provider, memory=store, permissions=PermissionManager(), context_window=1)

    reply = agent.send_message("Retome o que sabemos sobre o criador da Lumen.")

    assert reply == "Resposta de teste."
    context = provider.calls[0]["context"]
    recalled = [item for item in context if item.get("role") == "system"]
    assert len(recalled) == 1
    assert "MEMORIA RECUPERADA" in recalled[0]["content"]
    assert "Ainda não confirmamos o nome do criador da Lumen." in recalled[0]["content"]
    assert "receitas de bolo" not in recalled[0]["content"]


def test_agent_includes_relevant_structured_knowledge(tmp_path):
    store = MemoryStore(tmp_path / "memory" / "conversation.json")
    memory_system = MemorySystem(tmp_path)
    memory_system.remember(
        MemoryKind.KNOWLEDGE,
        "Decisão de arquitetura da Lumen",
        "O projeto usa GitHub como fonte única da verdade.",
        origin="agent",
        tags=("arquitetura", "github"),
    )
    provider = RecordingProvider()
    agent = Agent(
        provider=provider,
        memory=store,
        permissions=PermissionManager(),
        memory_system=memory_system,
    )

    agent.send_message("Qual é a fonte da verdade do projeto?")

    context = provider.calls[0]["context"]
    recalled = [item for item in context if item.get("role") == "system"]
    assert len(recalled) == 1
    assert "[KNOWLEDGE] Decisão de arquitetura da Lumen" in recalled[0]["content"]
    assert "GitHub como fonte única da verdade" in recalled[0]["content"]
