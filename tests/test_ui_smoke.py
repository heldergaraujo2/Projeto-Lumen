"""Smoke test da interface Tkinter.

Pulado automaticamente em ambientes sem Tkinter ou sem display
(ex.: servidores CI headless) — nas demais máquinas ele roda.
"""
from __future__ import annotations

import time

import pytest

tk = pytest.importorskip("tkinter")

from app.ai.mock import MockProvider  # noqa: E402
from app.ui.main_window import LumenWindow  # noqa: E402


class StubAgent:
    """Agente falso, apenas para exercitar a UI isoladamente.

    Representa o contrato atual do Agent (0.6.3): além de
    ``send_message`` (com streaming via ``on_delta``), expõe o atributo
    ``provider`` vigente — usado pelo cabeçalho da janela
    (``LumenWindow._provider_subtitle``) —, ``set_provider`` para
    troca em runtime e ``process_message`` (o que a UI chama desde a
    0.6.3: decide conversa × ação e devolve um ``AgentOutcome``).
    """

    def __init__(self) -> None:
        self.received: list[str] = []
        self.provider = MockProvider()  # name="mock" · model_name="lumen-mock"

    def set_provider(self, provider) -> None:
        """Espelha ``Agent.set_provider`` (troca em runtime)."""
        self.provider = provider

    def send_message(self, text: str, on_delta=None) -> str:
        self.received.append(text)
        reply = f"eco: {text}"
        if on_delta is not None:  # caminho de streaming da 0.2
            on_delta(reply)
        return reply

    def process_message(self, text: str, on_delta=None):
        """Espelha ``Agent.process_message`` (0.6.3 — usado pela UI).

        Sem fachada de ferramentas, o Agent real devolve o fluxo
        conversacional clássico como ``AgentOutcome`` — o stub faz o
        mesmo (sem ferramentas envolvidas no smoke test da UI).
        """
        from app.core.bridge import AgentOutcome, RequestState

        reply = self.send_message(text, on_delta=on_delta)
        return AgentOutcome(RequestState.CONVERSATIONAL, reply)


@pytest.fixture()
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:  # sem display disponível
        pytest.skip(f"Tkinter sem display: {exc}")
    yield window
    try:
        window.destroy()
    except tk.TclError:
        pass


def test_window_renders_and_exchanges_messages(root):
    agent = StubAgent()
    window = LumenWindow(root, agent)
    root.update()

    # Janela montada com status inicial.
    assert window.status_label.cget("text").startswith("●")

    # Cabeçalho reflete o contrato Agent.provider (name/model_name).
    assert "provedor: mock" in window.subtitle_label.cget("text")

    # Usuário escreve e envia; resposta deve aparecer na área de conversa.
    window.entry.insert(0, "Olá Lumen")
    window.send()

    deadline = time.time() + 5.0
    found = False
    while time.time() < deadline:
        root.update()
        contents = window.conversation.get("1.0", tk.END)
        if "Você" in contents and "eco: Olá Lumen" in contents:
            found = True
            break
        time.sleep(0.02)

    assert found, "a resposta não apareceu na área de conversa"
    assert agent.received == ["Olá Lumen"]
    assert window.conversation.get("1.0", tk.END).count("eco: Olá Lumen") == 1  # sem duplicar streaming
