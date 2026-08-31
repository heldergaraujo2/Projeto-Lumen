"""Testes do Agent Core na 0.2: system prompt, contexto, streaming e erros."""
from __future__ import annotations

import pytest

from app.ai.provider import (
    MissingApiKeyError,
    ProviderError,
    ProviderRateLimitError,
    user_message_for,
)
from app.ai.types import AIResponse, ResponseType, Usage
from app.config.persona import build_system_prompt
from app.core.agent import Agent, AgentError
from app.memory.store import MemoryStore
from app.security.permissions import PermissionManager


class ChatRecorder:
    """Provedor que registra o que o Agent envia e devolve AIResponse."""

    name = "recorder"

    def __init__(self, content="resposta do modelo"):
        self.calls: list[dict] = []
        self._content = content

    def generate(self, message, context=None):  # exigido pela ABC
        return self._content

    def chat(self, message, context=None, *, system_prompt=None, on_delta=None):
        self.calls.append({
            "message": message,
            "context": [dict(item) for item in context or []],
            "system_prompt": system_prompt,
            "on_delta": on_delta,
        })
        if on_delta is not None:
            on_delta(self._content)
        return AIResponse(
            content=self._content, model="modelo-teste",
            usage=Usage(input_tokens=1, output_tokens=2, total_tokens=3),
            finish_reason="stop",
        )


def make_agent(tmp_path, provider=None) -> Agent:
    return Agent(
        provider=provider or ChatRecorder(),
        memory=MemoryStore(tmp_path / "conversation.json"),
        permissions=PermissionManager(),
    )


def test_system_prompt_sent_to_provider(tmp_path):
    provider = ChatRecorder()
    agent = make_agent(tmp_path, provider)
    agent.send_message("oi")

    prompt_enviado = provider.calls[0]["system_prompt"]
    assert prompt_enviado
    assert prompt_enviado == build_system_prompt()
    assert "Lumen" in prompt_enviado
    assert "feminina" in prompt_enviado


def test_history_and_current_message_sent(tmp_path):
    """7. Histórico completo (limitado) + mensagem atual."""
    provider = ChatRecorder()
    agent = make_agent(tmp_path, provider)
    agent.send_message("primeira")
    agent.send_message("segunda")

    call = provider.calls[-1]
    assert call["message"] == "segunda"
    conteudos = [(m["role"], m["content"]) for m in call["context"]]
    assert conteudos == [("user", "primeira"), ("assistant", "resposta do modelo")]


def test_context_limit_respected(tmp_path):
    """8. Limite de contexto configurável (context_window)."""
    provider = ChatRecorder()
    memory = MemoryStore(tmp_path / "conversation.json")
    for i in range(10):
        memory.add_message("user" if i % 2 == 0 else "assistant", f"msg{i}")
    agent = Agent(provider=provider, memory=memory, context_window=3)

    agent.send_message("nova")
    context = provider.calls[0]["context"]
    assert len(context) == 3
    assert [m["content"] for m in context] == ["msg7", "msg8", "msg9"]


def test_on_delta_forwarded_to_provider(tmp_path):
    provider = ChatRecorder(content="resposta em pedaços")
    agent = make_agent(tmp_path, provider)
    recebido: list = []
    reply = agent.send_message("oi", on_delta=recebido.append)
    assert recebido == ["resposta em pedaços"]
    assert reply == "resposta em pedaços"


def test_agent_returns_string_and_keeps_last_response(tmp_path):
    provider = ChatRecorder(content="texto final")
    agent = make_agent(tmp_path, provider)
    reply = agent.send_message("oi")

    assert isinstance(reply, str)
    assert reply == "texto final"
    assert agent.memory.all_messages()[-1].content == "texto final"
    last = agent.last_response
    assert isinstance(last, AIResponse)
    assert last.model == "modelo-teste"
    assert last.usage.total_tokens == 3
    assert last.response_type is ResponseType.FINAL_RESPONSE


def test_empty_response_raises_agent_error(tmp_path):
    class Vazio(ChatRecorder):
        def __init__(self):
            super().__init__(content="   ")  # resposta em branco

    agent = make_agent(tmp_path, Vazio())
    with pytest.raises(AgentError):
        agent.send_message("oi")
    assert agent.memory.count == 1  # só a mensagem do usuário


def test_custom_system_prompt_overrides_default(tmp_path):
    provider = ChatRecorder()
    agent = Agent(provider=provider, memory=MemoryStore(tmp_path / "c.json"),
                  system_prompt="PROMPT PERSONALIZADO")
    agent.send_message("oi")
    assert provider.calls[0]["system_prompt"] == "PROMPT PERSONALIZADO"


@pytest.mark.parametrize("erro,fragmento", [
    (MissingApiKeyError("LUMEN_API_KEY não configurada. Defina no .env."), "LUMEN_API_KEY"),
    (ProviderRateLimitError("Limite de uso da API atingido."), "Limite"),
])
def test_provider_errors_become_friendly_agent_errors(tmp_path, erro, fragmento):
    """11. Erros do provedor viram AgentError com mensagem amigável."""

    class Falha(ChatRecorder):
        def chat(self, message, context=None, *, system_prompt=None, on_delta=None):
            raise erro

    agent = make_agent(tmp_path, Falha())
    with pytest.raises(AgentError) as exc:
        agent.send_message("oi")
    assert fragmento in str(exc.value)
    assert user_message_for(erro)


def test_generic_provider_error_wrapped(tmp_path):
    class Falha(ChatRecorder):
        def chat(self, message, context=None, *, system_prompt=None, on_delta=None):
            raise ProviderError("sem rede")

    agent = make_agent(tmp_path, Falha())
    with pytest.raises(AgentError) as exc:
        agent.send_message("oi")
    assert "sem rede" in str(exc.value)
