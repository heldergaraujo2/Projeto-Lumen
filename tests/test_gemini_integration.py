"""Testes de integração do Gemini: ConfigService, diálogo, troca runtime e segurança.

Reaproveita os fakes do OpenAI (``test_config_service``) e o client falso do
Gemini (``test_gemini_provider``) — tudo offline, sem chamadas reais.
"""
from __future__ import annotations

import json
import logging
import threading
import time

import pytest

import app.ui.settings_dialog as settings_dialog_module
from app.ai.gemini_provider import DEFAULT_MODEL, GeminiProvider
from app.ai.mock import MockProvider
from app.ai.openai_provider import OpenAIProvider
from app.config.config_service import ConfigService
from app.config.secrets import API_KEY_NAME, FileSecretStore
from app.config.settings import Settings, setup_logging
from app.config.user_config import UserConfigStore
from app.core.agent import Agent
from app.memory.store import MemoryStore
from app.security.permissions import PermissionManager
from tests.fake_tk import FakeMessagebox, FakeRoot, FakeTtkModule, FakeTkModule
from tests.test_config_service import FakeClient, ok_response
from tests.test_gemini_provider import FakeGeminiClient, gemini_response

CHAVE_GEMINI = "sk-gemini-INTEGRACAO-NAO-REAL"
CHAVE_OPENAI = "sk-openai-INTEGRACAO-NAO-REAL"


def make_service(tmp_path, gemini_client=None, openai_client=None):
    """Serviço real com Agent real; clients fake por provedor."""
    base = Settings(provider="mock", data_dir=tmp_path)
    agent = Agent(
        provider=MockProvider(base),
        memory=MemoryStore(tmp_path / "conversation.json"),
        permissions=PermissionManager(),
    )
    gemini_client = gemini_client or FakeGeminiClient(lambda kw: gemini_response(), [])
    openai_client = openai_client or FakeClient(lambda kw: ok_response(), [])

    def factory(api_key, timeout):
        return gemini_client if getattr(api_key, "startswith", lambda _: False)("sk-gemini") \
            else openai_client

    service = ConfigService(
        base_settings=base,
        user_store=UserConfigStore(tmp_path / "settings.json"),
        secrets=FileSecretStore(tmp_path),
        agent=agent,
        client_factory=factory,
    )
    return service, agent


# ------------------------------------------------------------ salvar/aplicar
def test_save_gemini_applies_to_agent_with_default_model(tmp_path):
    """SALVAR gemini: Agent troca em runtime; modelo padrão quando vazio."""
    service, agent = make_service(tmp_path)
    service.save("gemini", "", api_key=CHAVE_GEMINI)

    assert isinstance(agent.provider, GeminiProvider)
    assert agent.provider.model_name == DEFAULT_MODEL
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved == {"provider": "gemini"}  # modelo vazio não é persistido
    cofre = json.loads((tmp_path / ".credentials.json").read_text(encoding="utf-8"))
    assert cofre[API_KEY_NAME] == CHAVE_GEMINI


def test_runtime_swap_openai_to_gemini_and_back(tmp_path):
    """Troca OpenAI ↔ Gemini em runtime, sem reiniciar."""
    service, agent = make_service(tmp_path)

    service.save("openai", "gpt-4o-mini", api_key=CHAVE_OPENAI)
    assert isinstance(agent.provider, OpenAIProvider)

    service.save("gemini", "gemini-2.5-pro", api_key=CHAVE_GEMINI)
    assert isinstance(agent.provider, GeminiProvider)
    assert agent.provider.model_name == "gemini-2.5-pro"

    service.save("openai", "gpt-4o-mini")  # chave do cofre é mantida
    assert isinstance(agent.provider, OpenAIProvider)

    # mock continua intacto no fim
    service.save("mock", "")
    assert isinstance(agent.provider, MockProvider)
    assert agent.send_message("Olá Lumen").strip()


def test_conversation_with_gemini_provider_via_agent(tmp_path):
    """Conversa completa pelo Agent com o GeminiProvider (client fake)."""
    service, agent = make_service(tmp_path)
    service.save("gemini", "", api_key=CHAVE_GEMINI)

    reply = agent.send_message("Olá Lumen")
    assert reply == "resposta"  # eco do fake gemini_response()
    roles = [m.role for m in agent.memory.all_messages()]
    assert roles == ["user", "assistant"]


# ------------------------------------------------------------- teste conexão
def test_connection_test_gemini_success_and_minimal_request(tmp_path):
    calls: list = []
    client = FakeGeminiClient(lambda kw: gemini_response("pong"), calls)
    service, _ = make_service(tmp_path, gemini_client=client)

    result = service.test_connection("gemini", "", CHAVE_GEMINI)
    assert result.ok is True
    assert "Conexão estabelecida" in result.message
    assert DEFAULT_MODEL in result.message

    kwargs = calls[0]
    assert kwargs["contents"] == [{"role": "user", "parts": [{"text": "ping"}]}]
    # Sonda do Gemini NÃO limita tokens (thinking geraria falso negativo).
    assert "max_output_tokens" not in (kwargs["config"] or {})
    # A chave nunca vai no payload ao modelo.
    assert CHAVE_GEMINI not in json.dumps(kwargs, default=str)


def test_connection_test_gemini_invalid_key_friendly(tmp_path):
    class ClientError(Exception):
        def __init__(self):
            super().__init__("400 API key not valid")
            self.code = 400

    client = FakeGeminiClient(lambda kw: (_ for _ in ()).throw(ClientError()), [])
    service, _ = make_service(tmp_path, gemini_client=client)

    result = service.test_connection("gemini", "", "sk-gemini-errada")
    assert result.ok is False
    assert "Chave de API inválida" in result.message
    assert "Traceback" not in result.message


def test_connection_test_gemini_uses_saved_config(tmp_path):
    """TESTAR CONEXÃO sem argumentos usa a configuração vigente (gemini)."""
    client = FakeGeminiClient(lambda kw: gemini_response("pong"), [])
    service, _ = make_service(tmp_path, gemini_client=client)
    service.save("gemini", "", api_key=CHAVE_GEMINI)

    assert service.test_connection().ok is True


# ------------------------------------------------------------------ segurança
def test_gemini_key_never_in_logs_or_settings_json(tmp_path):
    logging.getLogger("lumen").handlers.clear()
    base = Settings(provider="mock", data_dir=tmp_path)
    setup_logging(base)
    logger = logging.getLogger("lumen")
    try:
        class ClientError(Exception):
            def __init__(self):
                super().__init__("401 unauthorized")
                self.code = 401

        client = FakeGeminiClient(lambda kw: (_ for _ in ()).throw(ClientError()), [])
        service, _ = make_service(tmp_path, gemini_client=client)
        service.save("gemini", "", api_key=CHAVE_GEMINI)
        result = service.test_connection()
        assert result.ok is False

        log_text = (tmp_path / "logs" / "lumen.log").read_text(encoding="utf-8")
        assert CHAVE_GEMINI not in log_text
        assert "sk-gemini" not in log_text
        settings_text = (tmp_path / "settings.json").read_text(encoding="utf-8")
        assert CHAVE_GEMINI not in settings_text
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


# --------------------------------------------------------------------- diálogo
@pytest.fixture()
def tk_fakes(monkeypatch):
    tk_module = FakeTkModule()
    ttk_module = FakeTtkModule()
    messagebox = FakeMessagebox(answer=True)
    monkeypatch.setattr(settings_dialog_module, "tk", tk_module)
    monkeypatch.setattr(settings_dialog_module, "ttk", ttk_module)
    monkeypatch.setattr(settings_dialog_module, "messagebox", messagebox)
    return tk_module, ttk_module, messagebox


def wait_for_test_threads(deadline_s: float = 5.0) -> None:
    end = time.time() + deadline_s
    while time.time() < end:
        alive = [t for t in threading.enumerate() if t.name == "lumen-test-connection"]
        if not alive:
            return
        time.sleep(0.01)


def test_dialog_combobox_lists_three_providers(tk_fakes, tmp_path):
    """Combobox exibe mock, openai e gemini."""
    service, _ = make_service(tmp_path)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)
    values = dialog.provider_combo.cget("values")
    for nome in ("mock", "openai", "gemini"):
        assert nome in values


def test_dialog_save_gemini_with_default_model(tk_fakes, tmp_path):
    """Gemini selecionado + modelo vazio + chave → SALVAR funciona."""
    service, agent = make_service(tmp_path)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    dialog.provider_combo.set("gemini")
    dialog.key_entry.insert(0, CHAVE_GEMINI)
    dialog.save()  # modelo vazio → padrão, sem erro

    assert isinstance(agent.provider, GeminiProvider)
    assert agent.provider.model_name == DEFAULT_MODEL
    assert dialog.key_entry.get() == ""
    assert "🟢" in dialog.status_label.cget("text")


def test_dialog_test_connection_gemini(tk_fakes, tmp_path):
    """TESTAR CONEXÃO com gemini (fake) → 🟢, sem travar a janela."""
    client = FakeGeminiClient(lambda kw: gemini_response("pong"), [])
    service, _ = make_service(tmp_path, gemini_client=client)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    dialog.provider_combo.set("gemini")
    dialog.key_entry.insert(0, CHAVE_GEMINI)
    dialog.test_connection()
    wait_for_test_threads()
    dialog._poll_queue()

    status = dialog.status_label.cget("text")
    assert "🟢" in status and "Conexão estabelecida" in status
    assert dialog.test_button.cget("state") != "disabled"


def test_dialog_openai_still_requires_model(tk_fakes, tmp_path):
    """Regressão: openai continua exigindo modelo explícito."""
    service, _ = make_service(tmp_path)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)
    dialog.provider_combo.set("openai")
    dialog.save()
    assert "🔴" in dialog.status_label.cget("text")
    assert "modelo" in dialog.status_label.cget("text").lower()


def test_openai_provider_still_intact_after_gemini_addition(tmp_path):
    """Regressão: fluxo OpenAI segue funcional (client fake)."""
    calls: list = []
    client = FakeClient(lambda kw: ok_response("pong"), calls)
    service, agent = make_service(tmp_path, openai_client=client)
    service.save("openai", "gpt-teste", api_key=CHAVE_OPENAI)
    assert isinstance(agent.provider, OpenAIProvider)
    result = service.test_connection("openai", "gpt-teste", CHAVE_OPENAI)
    assert result.ok is True
    assert [c for c in calls if "max_tokens" in c][0]["max_tokens"] == 1
