"""Testes do ConfigService — salvar/aplicar/testar conexão de ponta a ponta.

Nenhuma rede: o provedor openai usa um client factory falso injetado.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.mock import MockProvider
from app.ai.openai_provider import OpenAIProvider
from app.config.config_service import ConfigService, InvalidAIConfig
from app.config.secrets import API_KEY_NAME, FileSecretStore
from app.config.settings import Settings, setup_logging
from app.config.user_config import UserConfigStore
from app.core.agent import Agent
from app.memory.store import MemoryStore
from app.security.permissions import PermissionManager

CHAVE = "sk-TESTE-NAO-REAL-987"


# ------------------------------------------------------------------ fixtures
class FakeClient:
    def __init__(self, script, calls: list):
        self._script = script
        self._calls = calls

    def _create(self, **kwargs):
        self._calls.append(kwargs)
        return self._script(kwargs)

    @property
    def chat(self):
        return SimpleNamespace(completions=SimpleNamespace(create=self._create))


def ok_response(content="pong"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content),
                                 finish_reason="stop")],
        model="gpt-teste",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def make_service(tmp_path, base=None, script=None, calls=None):
    calls = calls if calls is not None else []
    base = base or Settings(provider="mock", data_dir=tmp_path)

    def factory(api_key, timeout):
        calls.append({"__factory__": (api_key, timeout)})
        return FakeClient(script or (lambda kwargs: ok_response()), calls)

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
        client_factory=factory,
    )
    return service, agent, calls


# --------------------------------------------------------------------- salvar
def test_save_applies_new_provider_to_agent_without_restart(tmp_path):
    """17. O Agent realmente passa a usar a configuração salva."""
    service, agent, _ = make_service(tmp_path)
    assert isinstance(agent.provider, MockProvider)

    service.save("openai", "gpt-4o-mini", api_key=CHAVE)
    assert isinstance(agent.provider, OpenAIProvider)
    assert agent.provider.model_name == "gpt-4o-mini"

    # 18: voltar para mock funciona sem chave
    service.save("mock", "")
    assert isinstance(agent.provider, MockProvider)
    # e a próxima mensagem usa o novo provider
    reply = agent.send_message("Olá Lumen")
    assert reply.strip()


def test_save_persists_non_secret_settings_and_key_separately(tmp_path):
    service, _, _ = make_service(tmp_path)
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)

    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved == {"provider": "openai", "model": "gpt-4o-mini"}
    assert CHAVE not in (tmp_path / "settings.json").read_text(encoding="utf-8")

    cofre = json.loads((tmp_path / ".credentials.json").read_text(encoding="utf-8"))
    assert cofre == {API_KEY_NAME: CHAVE}


def test_save_keeps_existing_key_when_field_left_blank(tmp_path):
    service, _, _ = make_service(tmp_path)
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)
    service.save("openai", "gpt-4o-mini", api_key="")  # em branco = manter

    cofre = json.loads((tmp_path / ".credentials.json").read_text(encoding="utf-8"))
    assert cofre[API_KEY_NAME] == CHAVE
    assert isinstance(service._agent.provider, OpenAIProvider)


def test_save_rejects_unknown_provider_and_persists_nothing(tmp_path):
    service, _, _ = make_service(tmp_path)
    with pytest.raises(InvalidAIConfig) as exc:
        service.save("hal9000", "modelo")
    assert "mock" in str(exc.value) and "openai" in str(exc.value)
    assert not (tmp_path / "settings.json").exists()


def test_save_openai_without_key_raises_and_persists_nothing(tmp_path):
    service, _, _ = make_service(tmp_path)
    with pytest.raises(InvalidAIConfig) as exc:
        service.save("openai", "gpt-4o-mini", api_key=None)
    assert "LUMEN_API_KEY" in str(exc.value) or "chave" in str(exc.value).lower()
    assert not (tmp_path / "settings.json").exists()
    assert isinstance(service._agent.provider, MockProvider)  # Agent intacto


def test_save_openai_without_model_raises(tmp_path):
    service, _, _ = make_service(tmp_path)
    with pytest.raises(InvalidAIConfig) as exc:
        service.save("openai", "", api_key=CHAVE)
    assert "LUMEN_MODEL" in str(exc.value)
    assert not (tmp_path / "settings.json").exists()


# -------------------------------------------------------------- current/reset
def test_current_config_reports_key_source(tmp_path):
    service, _, _ = make_service(tmp_path)
    assert service.current_config()["key_source"] == "nenhuma"

    service.save("openai", "gpt-4o-mini", api_key=CHAVE)
    current = service.current_config()
    assert current["provider"] == "openai"
    assert current["model"] == "gpt-4o-mini"
    assert current["has_stored_key"] is True
    assert current["key_source"] == "cofre"


def test_remove_api_key_falls_back_to_env(tmp_path):
    base = Settings(provider="openai", api_key="sk-do-env", model="m",
                    data_dir=tmp_path)
    service, agent, _ = make_service(tmp_path, base=base)
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)
    assert service.current_config()["key_source"] == "cofre"

    message = service.remove_api_key()
    assert "removida" in message.lower()
    assert service.current_config()["key_source"] == ".env"  # fallback .env
    assert isinstance(agent.provider, OpenAIProvider)  # segue válido


def test_remove_api_key_warns_when_provider_left_keyless(tmp_path):
    service, _, _ = make_service(tmp_path)
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)
    message = service.remove_api_key()
    assert "sem chave" in message


# --------------------------------------------------------------- teste conexão
def test_connection_with_mock_offline(tmp_path):
    """10. Teste de conexão em modo mock, sem internet e sem chave."""
    service, _, _ = make_service(tmp_path)
    result = service.test_connection("mock", "", None)
    assert result.ok is True
    assert "MockProvider" in result.message


def test_connection_success_with_fake_client(tmp_path):
    """11. Sucesso com provider real simulado (client fake)."""
    calls: list = []
    service, _, _ = make_service(tmp_path, script=lambda kw: ok_response("pong"), calls=calls)
    result = service.test_connection("openai", "gpt-4o-mini", CHAVE)

    assert result.ok is True
    assert "Conexão estabelecida" in result.message
    assert "gpt-teste" in result.message
    create_kwargs = [c for c in calls if "__factory__" not in c][0]
    assert create_kwargs["max_tokens"] == 1  # requisição mínima, barata
    assert create_kwargs["messages"] == [{"role": "user", "content": "ping"}]
    assert CHAVE not in json.dumps(create_kwargs, default=str)  # chave fora do payload


def test_connection_uses_saved_config_when_no_args(tmp_path):
    service, _, _ = make_service(tmp_path)
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)
    result = service.test_connection()  # sem argumentos → configuração vigente
    assert result.ok is True


def test_connection_auth_error_friendly(tmp_path):
    """12. Autenticação inválida → mensagem amigável."""
    class AuthenticationError(Exception): ...

    service, _, _ = make_service(
        tmp_path, script=lambda kw: (_ for _ in ()).throw(AuthenticationError("401"))
    )
    result = service.test_connection("openai", "gpt-4o-mini", "sk-errada")
    assert result.ok is False
    assert "Chave de API inválida" in result.message or "invalid" in result.message.lower()


def test_connection_invalid_model_friendly(tmp_path):
    """13. Modelo inválido → mensagem amigável."""
    class NotFoundError(Exception):
        status_code = 404

    service, _, _ = make_service(
        tmp_path, script=lambda kw: (_ for _ in ()).throw(NotFoundError())
    )
    result = service.test_connection("openai", "modelo-fantasma", CHAVE)
    assert result.ok is False
    assert "modelo" in result.message.lower()


def test_connection_timeout_friendly_and_no_retry(tmp_path):
    """14. Timeout → amigável; teste de conexão não repete (max_retries=0)."""
    class APITimeoutError(Exception): ...

    calls: list = []
    def script(kwargs):
        calls.append(1)
        raise APITimeoutError("demorou")

    service, _, _ = make_service(tmp_path, script=script)
    result = service.test_connection("openai", "gpt-4o-mini", CHAVE)
    assert result.ok is False
    assert "tempo limite" in result.message.lower() or "excedeu" in result.message.lower()
    assert len(calls) == 1


def test_connection_invalid_provider_friendly(tmp_path):
    service, _, _ = make_service(tmp_path)
    result = service.test_connection("fantasma", "", None)
    assert result.ok is False
    assert "Provedor inválido" in result.message


def test_failed_connection_test_does_not_alter_saved_config(tmp_path):
    """8. Teste de conexão com falha NÃO altera a configuração salva."""
    class AuthenticationError(Exception): ...

    service, agent, _ = make_service(
        tmp_path, script=lambda kw: (_ for _ in ()).throw(AuthenticationError("401"))
    )
    service.save("mock", "")  # configuração vigente: mock

    result = service.test_connection("openai", "gpt-4o-mini", "sk-errada")
    assert result.ok is False

    # Nada mudou: vigente continua mock; Agent segue no mock; arquivo intacto.
    assert service.current_config()["provider"] == "mock"
    assert isinstance(agent.provider, MockProvider)
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved == {"provider": "mock"}


def test_connection_missing_dependency_friendly(tmp_path):
    from app.ai.provider import ProviderDependencyError

    def factory(api_key, timeout):
        raise ProviderDependencyError("Dependência 'openai' não instalada.")

    base = Settings(provider="mock", data_dir=tmp_path)
    agent = Agent(MockProvider(base), MemoryStore(tmp_path / "c.json"), PermissionManager())
    service = ConfigService(
        base_settings=base,
        user_store=UserConfigStore(tmp_path / "settings.json"),
        secrets=FileSecretStore(tmp_path),
        agent=agent,
        client_factory=factory,
    )
    result = service.test_connection("openai", "gpt-4o-mini", CHAVE)
    assert result.ok is False
    assert "instalada" in result.message or "pip install" in result.message


# --------------------------------------------------- integração com build_app
def test_build_app_uses_saved_config_on_startup(tmp_path):
    """8/17. Configuração salva sobrevive reinício e chega ao Agent."""
    import main as lumen_main

    base = Settings(provider="mock", data_dir=tmp_path)
    agent1, service1 = lumen_main.build_app(base)
    assert isinstance(agent1.provider, MockProvider)

    service1.save("openai", "gpt-4o-mini", api_key=CHAVE)

    # Nova "execução" com a mesma pasta de dados: GUI vence o .env (mock).
    agent2, service2 = lumen_main.build_app(Settings(provider="mock", data_dir=tmp_path))
    assert isinstance(agent2.provider, OpenAIProvider)
    assert agent2.provider.model_name == "gpt-4o-mini"
    assert service2.current_config()["key_source"] == "cofre"


def test_build_app_starts_without_any_config(tmp_path, monkeypatch):
    """19. Aplicação inicia sem configuração real (mock, sem chave, sem .env).

    O cofre de credenciais é isolado em arquivo dentro do diretório
    temporário: numa máquina real (ex.: Windows com Credential Manager
    disponível) pode já existir a credencial da Lumen gravada pelo
    usuário no uso diário — ela não faz parte desta simulação e não deve
    ser aceita como configuração válida do teste (nem derrubá-lo).
    """
    import main as lumen_main

    monkeypatch.setattr(
        lumen_main,
        "create_secret_store",
        lambda data_dir: FileSecretStore(data_dir),
    )

    agent, service = lumen_main.build_app(Settings(data_dir=tmp_path))
    assert isinstance(agent.provider, MockProvider)
    config = service.current_config()
    assert config["provider"] == "mock"      # nenhuma API real ativa
    assert config["key_source"] == "nenhuma"  # sem chave em NENHUMA fonte
    assert config["has_stored_key"] is False
    assert agent.send_message("Olá Lumen").strip()


def test_thread_safe_provider_swap_during_use(tmp_path):
    """Troca de provider enquanto o Agent conversa não corrompe nada."""
    service, agent, _ = make_service(tmp_path)

    def conversar():
        for _ in range(5):
            try:
                agent.send_message("oi")
            except Exception:
                pass

    thread = threading.Thread(target=conversar, daemon=True)
    thread.start()
    service.save("mock", "")
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)
    thread.join(timeout=5)
    assert isinstance(agent.provider, OpenAIProvider)


# ------------------------------------------------------------------ segurança
def test_api_key_never_in_logs(tmp_path):
    """15. API Key nunca aparece nos logs (nem em erros)."""
    class AuthenticationError(Exception): ...

    base = Settings(provider="mock", data_dir=tmp_path, log_level="INFO")
    setup_logging(base)
    logger = logging.getLogger("lumen")
    try:
        service, _, _ = make_service(
            tmp_path,
            base=base,
            script=lambda kw: (_ for _ in ()).throw(AuthenticationError("401")),
        )
        service.save("openai", "gpt-4o-mini", api_key=CHAVE)
        result = service.test_connection()
        assert result.ok is False
        log_text = (tmp_path / "logs" / "lumen.log").read_text(encoding="utf-8")
        assert CHAVE not in log_text
        assert "sk-TESTE" not in log_text
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


def test_api_key_absent_from_common_files(tmp_path, pytestconfig=None):
    """16. Chave só existe no cofre — nunca em arquivos comuns."""
    service, agent, _ = make_service(tmp_path)
    service.save("openai", "gpt-4o-mini", api_key=CHAVE)
    agent.send_message("olá")  # garante conversation.json em disco

    project_root = Path(__file__).resolve().parents[1]
    common_files = [
        tmp_path / "settings.json",
        tmp_path / "conversation.json",
        project_root / "README.md",
        project_root / ".env.example",
        project_root / "requirements.txt",
        project_root / "app" / "config" / "config_service.py",
        project_root / "app" / "ui" / "settings_dialog.py",
    ]
    for path in common_files:
        assert CHAVE not in path.read_text(encoding="utf-8"), f"chave vazou em {path}"

    # Único lugar com a chave: o cofre (fallback documentado em dev/testes).
    cofre = tmp_path / ".credentials.json"
    assert CHAVE in cofre.read_text(encoding="utf-8")
