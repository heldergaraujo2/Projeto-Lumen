"""Notificação pós-aprovação no chat da janela principal (0.6.6).

Cobre o fluxo que faltava: APROVAR/RECUSAR na tela 🛡 deve produzir a
mensagem final (sucesso/falha/recusa) no CHAT da janela principal, pelo
callback ``on_plan_finished`` → formatador do bridge → fila existente.
"""
from __future__ import annotations

import json

import pytest

import app.ui.main_window as main_window_module
import app.ui.tools_dialog as tools_dialog_module
from app.ai.mock import MockProvider
from app.core.agent import Agent
from app.core.bridge import RequestState
from app.memory.store import MemoryStore
from app.security.permissions import PermissionManager
from app.tools.control import ToolsController
from tests.fake_tk import FakeMessagebox, FakeRoot, FakeTkModule

MSG = (
    "Crie um arquivo chamado teste_lumen.txt dentro do workspace atual "
    "contendo exatamente:\n\nTESTE LUMEN 0.6.3"
)


@pytest.fixture(autouse=True)
def fake_tk(monkeypatch):
    fake = FakeTkModule()
    monkeypatch.setattr(main_window_module, "tk", fake)
    monkeypatch.setattr(tools_dialog_module, "tk", fake)
    monkeypatch.setattr(tools_dialog_module, "messagebox", FakeMessagebox(True))
    return fake


@pytest.fixture
def env(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    perms = PermissionManager()
    agent = Agent(MockProvider(), MemoryStore(tmp_path / "c.json"),
                  permissions=perms)
    controller = ToolsController(
        perms,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )
    agent.set_tools_controller(controller)
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")
    window = main_window_module.LumenWindow(
        FakeRoot(), agent, tools_controller=controller,
    )
    return {"ws": ws, "tmp": tmp_path, "agent": agent,
            "controller": controller, "window": window}


def deliver(window, text: str) -> None:
    """Caminho de produção do worker: fila → _poll_queue → chat."""
    window._queue.put(("reply", text))
    window._poll_queue()


def open_dialog(controller) -> tools_dialog_module.ToolsDialog:
    # Mesma montagem de MainWindow._open_tools (callback da janela):
    return tools_dialog_module.ToolsDialog(
        FakeRoot(), controller,
        on_plan_finished=None,  # substituído pelo caller nos testes
    )


# ============================================ A) pausa continua funcionando
def test_a_chat_action_pauses_with_message_in_chat(env):
    outcome = env["agent"].process_message(MSG)
    assert outcome.state is RequestState.WAITING_APPROVAL
    deliver(env["window"], outcome.text)
    assert "PAUSADO" in env["window"].conversation.text
    assert env["controller"].has_pending


def test_open_tools_passes_the_callback_to_dialog(env, monkeypatch):
    captured = {}
    real = tools_dialog_module.ToolsDialog

    def spy(parent, controller, **kwargs):
        captured.update(kwargs)
        return real(parent, controller, **kwargs)

    monkeypatch.setattr(tools_dialog_module, "ToolsDialog", spy)
    env["window"]._open_tools()
    assert callable(captured.get("on_plan_finished"))


# ============================================ B/E/F/G) aprovar → sucesso
def test_b_approve_shows_completion_in_chat_and_creates_file(env):
    dialog = tools_dialog_module.ToolsDialog(
        FakeRoot(), env["controller"],
        on_plan_finished=env["window"]._on_plan_finished,
    )
    outcome = env["agent"].process_message(MSG)
    deliver(env["window"], outcome.text)
    dialog._approve()
    env["window"]._poll_queue()  # drena a mensagem final do callback

    # B) mensagem final no chat
    chat = env["window"].conversation.text
    assert "concluído" in chat and "PLN-" in chat
    # E) arquivo criado após aprovação
    created = env["ws"] / "teste_lumen.txt"
    assert created.exists()
    # F) conteúdo exato
    assert created.read_text(encoding="utf-8") == "TESTE LUMEN 0.6.3"
    # diálogo segue com seu status local (comportamento preservado)
    assert "COMPLETED" in dialog.status_label.cget("text")
    # memória linear registrou o desfecho (caminho do bridge)
    recent = " ".join(m.content for m in env["agent"].memory.recent(10))
    assert "concluído" in recent


def test_g_audit_still_recorded_after_approval(env):
    dialog = tools_dialog_module.ToolsDialog(
        FakeRoot(), env["controller"],
        on_plan_finished=env["window"]._on_plan_finished,
    )
    env["agent"].process_message(MSG)
    dialog._approve()
    lines = [json.loads(l) for l in
             (env["tmp"] / "audit" / "audit.jsonl").read_text().splitlines()
             if l.strip()]
    assert any(r.get("tool") == "create_file" for r in lines)


# ============================================ C) recusar → nada executa
def test_c_refuse_blocks_and_reports_to_chat(env):
    dialog = tools_dialog_module.ToolsDialog(
        FakeRoot(), env["controller"],
        on_plan_finished=env["window"]._on_plan_finished,
    )
    outcome = env["agent"].process_message(MSG)
    deliver(env["window"], outcome.text)
    dialog._refuse()
    env["window"]._poll_queue()

    chat = env["window"].conversation.text
    assert "falhou" in chat or "NÃO foi executada" in chat  # desfecho claro
    assert not (env["ws"] / "teste_lumen.txt").exists()      # nada executado
    assert not env["controller"].has_pending


# ============================================ D) falha de execução → chat
def test_d_execution_failure_reaches_chat(env):
    (env["ws"] / "teste_lumen.txt").write_text("JÁ EXISTIA", encoding="utf-8")
    dialog = tools_dialog_module.ToolsDialog(
        FakeRoot(), env["controller"],
        on_plan_finished=env["window"]._on_plan_finished,
    )
    env["agent"].process_message(MSG)
    dialog._approve()  # executa e FALHA (arquivo já existe)
    env["window"]._poll_queue()

    chat = env["window"].conversation.text
    assert "falhou" in chat and "já existe" in chat.lower()
    # conteúdo original intacto
    assert (env["ws"] / "teste_lumen.txt").read_text(encoding="utf-8") == \
        "JÁ EXISTIA"


# ============================================ retrocompatibilidade
def test_dialog_without_callback_keeps_previous_behavior(env):
    env["agent"].process_message(MSG)
    dialog = open_dialog(env["controller"])  # sem callback
    dialog._approve()                        # não deve explodir
    assert "COMPLETED" in dialog.status_label.cget("text")
    assert (env["ws"] / "teste_lumen.txt").exists()


def test_callback_error_does_not_break_dialog(env):
    def boom(report):
        raise RuntimeError("callback hostil")

    dialog = tools_dialog_module.ToolsDialog(
        FakeRoot(), env["controller"], on_plan_finished=boom,
    )
    env["agent"].process_message(MSG)
    dialog._approve()  # exceção do callback é engolida com log
    assert "COMPLETED" in dialog.status_label.cget("text")
    assert (env["ws"] / "teste_lumen.txt").exists()
