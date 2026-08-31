"""Testes de integração offline da expansão de providers (0.3.x).

Fluxo completo **sem rede**: ConfigService → Provider (groq/together, com
client fake injetado) → Agent → memória de conversa. Valida também a
descoberta dinâmica dos providers pela tela de configurações, a segurança
da API Key e a introspecção dos SDKs reais (quando instalados).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.groq_provider import GroqProvider
from app.ai.provider import available_providers
from app.ai.together_provider import TogetherProvider
from app.ai import GROQ_DEFAULT_MODEL, TOGETHER_DEFAULT_MODEL
from app.config.config_service import ConfigService
from app.config.secrets import FileSecretStore
from app.config.settings import Settings
from app.config.user_config import UserConfigStore
from app.core.agent import Agent
from app.memory.store import MemoryStore
from app.security.permissions import PermissionManager
from app.ai.mock import MockProvider

CHAVE_GROQ = "gsk-TESTE-NAO-REAL-123"
CHAVE_TOGETHER = "tgp-TESTE-NAO-REAL-456"


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


def ok_response(content="pong", model="modelo-teste"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content),
                                 finish_reason="stop")],
        model=model,
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def make_service(tmp_path, script=None, calls=None, provider="groq"):
    calls = calls if calls is not None else []
    base = Settings(provider="mock", data_dir=tmp_path)

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


# ------------------------------------------------------------- descoberta/UI
def test_settings_dialog_discovers_providers_dynamically():
    """A combobox usa available_providers() — novos providers aparecem sozinhos."""
    values = list(available_providers())
    assert values == sorted(values)
    for name in ("mock", "openai", "gemini", "groq", "together"):
        assert name in values


def test_invalid_provider_message_lists_all_five():
    service, _, _ = make_service(Path("/tmp/lumen-expand"))
    result = service.test_connection(provider="claude-mágico")
    assert not result.ok
    for name in ("mock", "openai", "gemini", "groq", "together"):
        assert name in result.message


# ------------------------------------------------- ConfigService → Provider
def test_save_groq_applies_provider_and_default_model(tmp_path):
    service, agent, calls = make_service(tmp_path)
    service.save("groq", "", api_key=CHAVE_GROQ)

    assert isinstance(agent.provider, GroqProvider)
    assert agent.provider.model_name == GROQ_DEFAULT_MODEL
    # user_store gravado SEM segredo; chave foi para o cofre
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert "api_key" not in json.dumps(saved)
    assert (tmp_path / ".credentials.json").exists()


def test_save_together_applies_provider_and_default_model(tmp_path):
    service, agent, _ = make_service(tmp_path)
    service.save("together", "", api_key=CHAVE_TOGETHER)
    assert isinstance(agent.provider, TogetherProvider)
    assert agent.provider.model_name == TOGETHER_DEFAULT_MODEL


def test_save_invalid_provider_rejected_before_persisting(tmp_path):
    service, _, _ = make_service(tmp_path)
    with pytest.raises(Exception):
        service.save("sanpascual", "", api_key="x")
    assert not (tmp_path / "settings.json").exists() or "sanpascual" not in \
        (tmp_path / "settings.json").read_text(encoding="utf-8")


# ---------------------------------------------------------- TESTAR CONEXÃO
def test_connection_groq_ok_without_max_tokens_probe(tmp_path):
    """Sonda não limita max_tokens (gpt-oss raciocina; limite daria falso negativo)."""
    calls: list = []
    service, _, _ = make_service(tmp_path, calls=calls)
    result = service.test_connection("groq", "", api_key=CHAVE_GROQ)
    assert result.ok, result.message
    create_kwargs = [c for c in calls if "__factory__" not in c][0]
    assert "max_tokens" not in create_kwargs
    assert create_kwargs["messages"][-1]["content"] == "ping"


def test_connection_together_ok(tmp_path):
    calls: list = []
    service, _, _ = make_service(tmp_path, calls=calls)
    result = service.test_connection("together", "", api_key=CHAVE_TOGETHER)
    assert result.ok, result.message
    create_kwargs = [c for c in calls if "__factory__" not in c][0]
    assert create_kwargs["model"] == TOGETHER_DEFAULT_MODEL
    assert "max_tokens" not in create_kwargs


def test_connection_auth_failure_is_friendly(tmp_path):
    class AuthenticationError(Exception):
        status_code = 401

    def script(kwargs):
        raise AuthenticationError("401")

    service, _, _ = make_service(tmp_path, script=script)
    result = service.test_connection("groq", "", api_key="gsk-errada")
    assert not result.ok
    assert "chave" in result.message.lower()
    assert "Traceback" not in result.message


def test_connection_model_not_found(tmp_path):
    class NotFoundErr(Exception):
        status_code = 404

    def script(kwargs):
        raise NotFoundErr("model not found")

    service, _, _ = make_service(tmp_path, script=script)
    result = service.test_connection("together", "modelo-inexistente", api_key=CHAVE_TOGETHER)
    assert not result.ok
    assert "modelo" in result.message.lower()


def test_connection_empty_response(tmp_path):
    service, _, _ = make_service(tmp_path, script=lambda kwargs: ok_response(content="  "))
    result = service.test_connection("groq", "", api_key=CHAVE_GROQ)
    assert not result.ok
    assert "vazio" in result.message.lower()


# ------------------------------------------- Provider → Agent → memória 0.3
def test_agent_chat_end_to_end_with_groq_and_memory(tmp_path):
    """Conversa via Agent com provider groq grava a memória local de conversa."""
    def script(kwargs):
        if kwargs.get("stream"):  # Agent conversa com streaming (on_delta)
            return iter([
                SimpleNamespace(choices=[SimpleNamespace(
                    delta=SimpleNamespace(content="Olá"), finish_reason=None)]),
                SimpleNamespace(choices=[SimpleNamespace(
                    delta=SimpleNamespace(content=", tudo bem?"), finish_reason="stop")]),
            ])
        return ok_response()

    service, agent, _ = make_service(tmp_path, script=script)
    service.save("groq", "", api_key=CHAVE_GROQ)

    received: list = []
    reply = agent.send_message("Olá Lumen", on_delta=received.append)
    assert reply.strip()
    assert received  # streaming chegou ao chamador

    conversation = json.loads(
        (tmp_path / "conversation.json").read_text(encoding="utf-8"))
    roles = [m["role"] for m in conversation]
    assert roles[-2:] == ["user", "assistant"]


def test_memory_structured_files_untouched_by_providers(tmp_path):
    """Providers não escrevem na memória estruturada 0.3 — ela segue local."""
    service, agent, _ = make_service(tmp_path)
    service.save("together", "", api_key=CHAVE_TOGETHER)
    agent.send_message("Oi")

    memory_dir = tmp_path / "memory"
    if memory_dir.exists():  # nenhum provider deve ter criado domínios
        assert list(memory_dir.glob("*.json")) == []


def test_runtime_swap_between_providers(tmp_path):
    """Troca groq → together → mock em runtime, sem reiniciar o Agent."""
    service, agent, _ = make_service(tmp_path)
    service.save("groq", "", api_key=CHAVE_GROQ)
    assert agent.send_message("com groq").strip()
    assert isinstance(agent.provider, GroqProvider)

    service.save("together", "", api_key=CHAVE_TOGETHER)
    assert isinstance(agent.provider, TogetherProvider)
    assert agent.send_message("com together").strip()

    service.save("mock", "")
    assert isinstance(agent.provider, MockProvider)


# ------------------------------------------------------------------ segurança
def test_api_key_never_in_payload_nor_plain_files(tmp_path):
    calls: list = []
    service, _, _ = make_service(tmp_path, calls=calls)
    service.save("groq", "", api_key=CHAVE_GROQ)

    # Key só na factory (construção do client); nunca no payload das chamadas
    for call in calls:
        if "__factory__" in call:
            continue
        assert CHAVE_GROQ not in json.dumps(call, default=str)
    # E nunca em arquivos comuns
    settings_json = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert CHAVE_GROQ not in settings_json


def test_api_key_never_in_logs(tmp_path, caplog):
    calls: list = []
    service, _, _ = make_service(tmp_path, calls=calls)
    with caplog.at_level(logging.DEBUG, logger="lumen"):
        service.save("together", "", api_key=CHAVE_TOGETHER)
        result = service.test_connection("together", "", api_key=CHAVE_TOGETHER)
        assert result.ok
    assert CHAVE_TOGETHER not in caplog.text


# --------------------------------------------- introspecção dos SDKs reais
def test_introspection_groq_sdk():
    """Com o SDK real instalado: assinaturas usadas pela factory existem."""
    pytest.importorskip("groq")
    import inspect

    import groq

    sig = inspect.signature(groq.Groq.__init__)
    for param in ("api_key", "timeout", "max_retries"):
        assert param in sig.parameters, f"Groq.__init__ deveria aceitar {param}"
    client = groq.Groq(api_key="x", timeout=5.0, max_retries=0)
    create_params = inspect.signature(client.chat.completions.create).parameters
    for param in ("model", "messages", "stream", "max_tokens", "timeout"):
        assert param in create_params, f"create deveria aceitar {param}"


def test_introspection_together_sdk():
    """Com o SDK real instalado: assinaturas usadas pela factory existem."""
    pytest.importorskip("together")
    import inspect

    import together

    sig = inspect.signature(together.Together.__init__)
    for param in ("api_key", "timeout", "max_retries"):
        assert param in sig.parameters, f"Together.__init__ deveria aceitar {param}"
    client = together.Together(api_key="x", timeout=5.0, max_retries=0)
    create_params = inspect.signature(client.chat.completions.create).parameters
    for param in ("model", "messages", "stream", "max_tokens", "timeout"):
        assert param in create_params, f"create deveria aceitar {param}"
