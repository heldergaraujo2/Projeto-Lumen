"""Offline tests for the OrcaRouter OpenAI-compatible provider."""
from types import SimpleNamespace

from app.ai.orcarouter_provider import BASE_URL, DEFAULT_MODEL, OrcaRouterProvider
from app.ai.provider import available_providers, create_provider
from app.config.settings import Settings


def _response():
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"type":"conversation","message":"Olá"}'),
            finish_reason="stop",
        )],
        model=DEFAULT_MODEL,
        usage=None,
    )


class _FakeClient:
    def __init__(self, calls):
        self.calls = calls
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return _response()


def test_orcarouter_is_registered_and_uses_default_model():
    settings = Settings(provider="orcarouter", api_key="test-secret", model="", data_dir="/tmp/lumen-test")
    calls = []
    provider = create_provider(settings)
    assert isinstance(provider, OrcaRouterProvider)
    assert provider.name in available_providers()
    assert provider.model_name == DEFAULT_MODEL


def test_orcarouter_provider_sends_chat_completions_payload():
    settings = Settings(provider="orcarouter", api_key="test-secret", model=DEFAULT_MODEL, data_dir="/tmp/lumen-test")
    calls = []
    provider = OrcaRouterProvider(
        settings,
        client_factory=lambda api_key, timeout: _FakeClient(calls),
    )
    response = provider.chat("oi", system_prompt="Responda em JSON")
    assert response.content.startswith("{")
    assert calls[0]["model"] == DEFAULT_MODEL
    assert calls[0]["messages"][0] == {"role": "system", "content": "Responda em JSON"}


def test_orcarouter_client_factory_uses_fixed_gateway(monkeypatch):
    import sys
    import types

    captured = {}
    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    OrcaRouterProvider._default_client_factory("test-secret", 17.0)
    assert captured == {
        "api_key": "test-secret",
        "base_url": BASE_URL,
        "timeout": 17.0,
        "max_retries": 0,
    }
