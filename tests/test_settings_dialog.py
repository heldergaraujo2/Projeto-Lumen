"""Testes da tela "Configurações → Inteligência Artificial" (UI fake, sem display).

Exercita o diálogo real (``app.ui.settings_dialog.SettingsDialog``) com um
toolkit Tk falso: abrir, exibir valores, alterar, mostrar/ocultar chave,
salvar, remover chave e testar conexão — de ponta a ponta com o
ConfigService real (provedores simulados, sem rede).
"""
from __future__ import annotations

import json
import threading
import time

import pytest

import app.ui.settings_dialog as settings_dialog_module
from app.ai.mock import MockProvider
from app.ai.openai_provider import OpenAIProvider
from app.config.config_service import ConfigService
from app.config.secrets import API_KEY_NAME, FileSecretStore
from app.config.settings import Settings
from app.config.user_config import UserConfigStore
from app.core.agent import Agent
from app.memory.store import MemoryStore
from app.security.permissions import PermissionManager
from tests.fake_tk import FakeMessagebox, FakeRoot, FakeTtkModule, FakeTkModule

CHAVE = "sk-DIALOG-NAO-REAL-42"


class FakeClient:
    def __init__(self, response="pong"):
        self._response = response
        self.calls: list[dict] = []

    def _create(self, **kwargs):
        self.calls.append(kwargs)

        class _Resp:
            choices = [type("C", (), {"message": type("M", (), {"content": self._response})(),
                                      "finish_reason": "stop"})()]
            model = "gpt-teste"
            usage = None

        return _Resp()

    @property
    def chat(self):
        from types import SimpleNamespace

        return SimpleNamespace(completions=SimpleNamespace(create=self._create))


@pytest.fixture()
def tk_fakes(monkeypatch):
    """Troca o tk/ttk/messagebox do diálogo por fakes controláveis."""
    tk_module = FakeTkModule()
    ttk_module = FakeTtkModule()
    messagebox = FakeMessagebox(answer=True)
    monkeypatch.setattr(settings_dialog_module, "tk", tk_module)
    monkeypatch.setattr(settings_dialog_module, "ttk", ttk_module)
    monkeypatch.setattr(settings_dialog_module, "messagebox", messagebox)
    return tk_module, ttk_module, messagebox


def make_service(tmp_path, client=None):
    base = Settings(provider="mock", data_dir=tmp_path)
    agent = Agent(
        provider=MockProvider(base),
        memory=MemoryStore(tmp_path / "conversation.json"),
        permissions=PermissionManager(),
    )
    service = ConfigService(
        base_settings=base,
        user_store=UserConfigStore(tmp_path / "settings.json"),
        secrets=FileSecretStore(tmp_path),
        agent=agent,
        client_factory=lambda key, timeout: client or FakeClient(),
    )
    return service, agent


def wait_for_test_threads(deadline_s: float = 5.0) -> None:
    end = time.time() + deadline_s
    while time.time() < end:
        alive = [t for t in threading.enumerate() if t.name == "lumen-test-connection"]
        if not alive:
            return
        time.sleep(0.01)


# ------------------------------------------------------------------- abrir/ler
def test_dialog_opens_showing_current_provider(tk_fakes, tmp_path):
    """1/2. Abre e exibe o provider atual (mock)."""
    service, _ = make_service(tmp_path)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    assert dialog.top.window_title == "Configurações — Inteligência Artificial"
    assert dialog.provider_combo.get() == "mock"
    assert dialog.model_entry.get() == ""
    assert dialog.key_entry.get() == ""  # a chave salva nunca é exibida
    assert dialog.key_entry.cget("show") == "•"  # começa oculta


def test_dialog_opens_with_saved_openai_config(tk_fakes, tmp_path):
    service, _ = make_service(tmp_path)
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)

    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)
    assert dialog.provider_combo.get() == "openai"
    assert dialog.model_entry.get() == "gpt-4o-mini"
    assert dialog.key_entry.get() == ""  # nada exposto mesmo com chave salva


# -------------------------------------------------------------- mostrar/ocultar
def test_toggle_key_visibility(tk_fakes, tmp_path):
    """6. 👁 alterna entre ••• e visível temporariamente."""
    service, _ = make_service(tmp_path)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    dialog.key_entry.insert(0, CHAVE)
    dialog.toggle_key_visibility()
    assert dialog.key_entry.cget("show") == ""   # visível
    dialog.toggle_key_visibility()
    assert dialog.key_entry.cget("show") == "•"  # oculta de novo


# --------------------------------------------------------------------- salvar
def test_save_changes_provider_model_and_key(tk_fakes, tmp_path):
    """3/4/5/7. Altera provider/modelo, insere chave e salva de fato."""
    client = FakeClient()
    service, agent = make_service(tmp_path, client=client)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    dialog.provider_combo.set("openai")
    dialog.model_entry.delete(0, "end")
    dialog.model_entry.insert(0, "gpt-4o-mini")
    dialog.key_entry.insert(0, CHAVE)
    dialog.save()

    assert isinstance(agent.provider, OpenAIProvider)      # aplicado ao Agent
    assert agent.provider.model_name == "gpt-4o-mini"
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved == {"provider": "openai", "model": "gpt-4o-mini"}
    cofre = json.loads((tmp_path / ".credentials.json").read_text(encoding="utf-8"))
    assert cofre[API_KEY_NAME] == CHAVE
    assert dialog.key_entry.get() == ""  # campo limpo após salvar
    assert "🟢" in dialog.status_label.cget("text")


def test_save_mock_without_key_works(tk_fakes, tmp_path):
    """18. MockProvider continua funcionando sem API Key."""
    service, agent = make_service(tmp_path)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    dialog.provider_combo.set("mock")
    dialog.model_entry.delete(0, "end")
    dialog.key_entry.delete(0, "end")
    dialog.save()

    assert isinstance(agent.provider, MockProvider)
    assert agent.send_message("Olá Lumen").strip()
    assert "🟢" in dialog.status_label.cget("text")


def test_save_openai_without_model_shows_friendly_error(tk_fakes, tmp_path):
    service, _ = make_service(tmp_path)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    dialog.provider_combo.set("openai")
    dialog.model_entry.delete(0, "end")
    dialog.save()

    assert "🔴" in dialog.status_label.cget("text")
    assert "modelo" in dialog.status_label.cget("text").lower()
    assert not (tmp_path / "settings.json").exists()  # nada persistido


def test_save_without_openai_key_reports_how_to_configure(tk_fakes, tmp_path):
    service, _ = make_service(tmp_path)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    dialog.provider_combo.set("openai")
    dialog.model_entry.insert(0, "gpt-4o-mini")
    dialog.save()  # sem chave e sem .env → erro claro

    status = dialog.status_label.cget("text")
    assert "🔴" in status
    assert "LUMEN_API_KEY" in status or "chave" in status.lower()


# ------------------------------------------------------- recarregar / remover
def test_saved_config_is_reloaded_in_new_dialog(tk_fakes, tmp_path):
    """8. Reabrir a tela reflete a configuração persistida."""
    service, _ = make_service(tmp_path)
    client = FakeClient()
    service2, _ = make_service(tmp_path, client=client)
    service2.save("openai", "gpt-4o-mini", api_key=CHAVE)

    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)
    assert dialog.provider_combo.get() == "openai"
    assert dialog.model_entry.get() == "gpt-4o-mini"


def test_remove_saved_key_via_dialog(tk_fakes, tmp_path, monkeypatch):
    """9. Remover a chave salva pelo diálogo (com confirmação)."""
    tk_module, _ttk, messagebox = tk_fakes
    service, _ = make_service(tmp_path)
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)
    assert service.current_config()["has_stored_key"] is True

    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)
    messagebox.answer = True  # usuário confirma
    dialog._remove_key()

    assert service.current_config()["has_stored_key"] is False
    assert "🟢" in dialog.status_label.cget("text")
    assert len(messagebox.calls) == 1


def test_remove_key_cancelled_keeps_key(tk_fakes, tmp_path):
    tk_module, _ttk, messagebox = tk_fakes
    service, _ = make_service(tmp_path)
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)

    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)
    messagebox.answer = False  # usuário cancela
    dialog._remove_key()
    assert service.current_config()["has_stored_key"] is True


# ---------------------------------------------------------------- teste conexão
def test_connection_button_mock_offline(tk_fakes, tmp_path):
    """10. TESTAR CONEXÃO com mock: offline, sem chave, resultado verde."""
    service, _ = make_service(tmp_path)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    dialog.test_connection()
    wait_for_test_threads()
    dialog._poll_queue()

    status = dialog.status_label.cget("text")
    assert "🟢" in status
    assert "MockProvider funcionando" in status
    assert dialog.test_button.cget("state") != "disabled"


def test_connection_button_success_fake_provider(tk_fakes, tmp_path):
    """11. TESTAR CONEXÃO com provider real simulado."""
    client = FakeClient("pong")
    service, _ = make_service(tmp_path, client=client)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    dialog.provider_combo.set("openai")
    dialog.model_entry.insert(0, "gpt-4o-mini")
    dialog.key_entry.insert(0, CHAVE)
    dialog.test_connection()
    wait_for_test_threads()
    dialog._poll_queue()

    status = dialog.status_label.cget("text")
    assert "🟢" in status and "Conexão estabelecida" in status
    # requisição mínima e barata
    assert client.calls[0]["max_tokens"] == 1
    # a chave nunca vai no payload ao modelo
    assert CHAVE not in json.dumps(client.calls[0], default=str)


def test_connection_button_auth_error_friendly(tk_fakes, tmp_path):
    """12. Falha de autenticação exibida de forma amigável (sem traceback)."""
    class AuthenticationError(Exception): ...

    class FailClient(FakeClient):
        def _create(self, **kwargs):
            self.calls.append(kwargs)
            raise AuthenticationError("401")

    client = FailClient()
    service, _ = make_service(tmp_path, client=client)
    dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)

    dialog.provider_combo.set("openai")
    dialog.model_entry.insert(0, "gpt-4o-mini")
    dialog.key_entry.insert(0, "sk-invalida")
    dialog.test_connection()
    wait_for_test_threads()
    dialog._poll_queue()

    status = dialog.status_label.cget("text")
    assert "🔴" in status
    assert "Traceback" not in status
    assert "Chave de API inválida" in status


def test_dialog_never_displays_saved_key(tk_fakes, tmp_path):
    """A chave salva permanece invisível em qualquer reabertura."""
    client = FakeClient()
    service, _ = make_service(tmp_path, client=client)
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)

    for _ in range(2):
        dialog = settings_dialog_module.SettingsDialog(FakeRoot(), service)
        assert dialog.key_entry.get() == ""
        assert dialog.key_entry.cget("show") == "•"
        hint = dialog.key_hint.cget("text")
        assert CHAVE not in hint
