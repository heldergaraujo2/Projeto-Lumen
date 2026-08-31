"""Testes do TogetherProvider — 100% offline, com client fake injetado.

Nenhum teste aqui toca a rede ou a API real da Together AI: o SDK é
substituído por um ``client_factory`` falso que registra as chamadas e
devolve respostas scriptadas.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.openai_provider import OpenAIProvider
from app.ai.provider import (
    InvalidModelError,
    MissingApiKeyError,
    ProviderAuthError,
    ProviderDependencyError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    UnexpectedProviderError,
    available_providers,
    create_provider,
)
from app.ai.together_provider import DEFAULT_MODEL, TogetherProvider
from app.ai.types import AIResponse, ResponseType, Usage
from app.config.settings import Settings

# Exceções "com cara de SDK" — o mapeamento é por nome/status_code, então
# os testes não precisam do pacote together instalado.
class APIConnectionError(Exception): ...
class APITimeoutError(Exception): ...
class AuthenticationError(Exception): ...
class RateLimitError(Exception): ...
class BadRequestError(Exception):
    def __init__(self, msg="Invalid model specified"): super().__init__(msg); self.status_code = 400
class NotFoundError(Exception):
    def __init__(self): super().__init__("model not found"); self.status_code = 404
class InternalServerError(Exception):
    def __init__(self): super().__init__("boom"); self.status_code = 500


def plain_response(content="resposta", model=DEFAULT_MODEL, finish="stop", with_usage=True):
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15) if with_usage else None
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)],
        model=model,
        usage=usage,
    )


def stream_chunk(text=None, finish=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=text), finish_reason=finish)])


class FakeClient:
    """Client falso: `script(kwargs)` devolve resposta ou levanta exceção."""

    def __init__(self, script, calls: list):
        self._script = script
        self._calls = calls

    def _create(self, **kwargs):
        self._calls.append(kwargs)
        return self._script(kwargs)

    @property
    def chat(self):
        return SimpleNamespace(completions=SimpleNamespace(create=self._create))


def make_provider(script, calls, **overrides):
    """Constrói o provedor com settings e client fake (retry sem espera)."""
    values = dict(provider="together", api_key="tgp-teste", model="",
                  data_dir="/tmp/lumen-teste", max_retries=2, request_timeout=60.0)
    values.update(overrides)
    settings = Settings(**values)

    def factory(api_key, timeout):
        calls.append({"__factory__": (api_key, timeout)})
        return FakeClient(script, calls)

    return TogetherProvider(settings, client_factory=factory, retry_backoff=0.0)


def create_calls(calls):
    return [c for c in calls if "__factory__" not in c]


# --------------------------------------------------------------- inicialização
def test_provider_initializes_without_network_call():
    """Init não dispara nenhuma chamada real (factory não é invocada)."""
    calls: list = []
    provider = make_provider(lambda kwargs: plain_response(), calls)
    assert provider.name == "together"
    assert calls == []


def test_missing_api_key_raises_with_instructions():
    with pytest.raises(MissingApiKeyError) as exc:
        make_provider(lambda kwargs: plain_response(), [], api_key="")
    assert "together" in str(exc.value)
    assert ".env" in str(exc.value)


def test_default_model_is_real_llama4():
    """Modelo é opcional no together: vazio usa Llama 4 Scout real."""
    provider = make_provider(lambda kwargs: plain_response(), [])
    assert provider.model_name == DEFAULT_MODEL
    assert DEFAULT_MODEL.startswith("meta-llama/Llama-4-")
    assert "Scout" in DEFAULT_MODEL


def test_explicit_model_respected():
    provider = make_provider(
        lambda kwargs: plain_response(), [],
        model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8")
    assert provider.model_name == "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"


def test_factory_creates_together_provider():
    settings = Settings(provider="together", api_key="tgp-x", model="",
                        data_dir="/tmp/lumen-teste")
    provider = create_provider(settings)
    assert isinstance(provider, TogetherProvider)
    assert isinstance(provider, OpenAIProvider)  # núcleo reutilizado, sem duplicação


def test_registry_lists_new_providers():
    assert set(available_providers()) >= {"mock", "openai", "gemini", "groq", "together"}


# ------------------------------------------------------------------- mensagens
def test_message_payload_structure():
    """System prompt + histórico (sem timestamps) + mensagem atual."""
    captured: list = []

    def script(kwargs):
        captured.append(kwargs)
        return plain_response()

    provider = make_provider(script, [])
    context = [
        {"role": "user", "content": "primeira", "timestamp": "2026-01-01T10:00:00-03:00"},
        {"role": "assistant", "content": "segunda", "timestamp": "2026-01-01T10:00:01-03:00"},
        {"role": "system", "content": " deve ser filtrado do histórico"},
    ]
    provider.chat("atual", context, system_prompt="PROMPT-SISTEMA")

    kwargs = captured[0]
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["messages"] == [
        {"role": "system", "content": "PROMPT-SISTEMA"},
        {"role": "user", "content": "primeira"},
        {"role": "assistant", "content": "segunda"},
        {"role": "user", "content": "atual"},
    ]
    assert "stream" not in kwargs


def test_response_is_normalized():
    provider = make_provider(
        lambda kwargs: plain_response("olá do modelo", model=DEFAULT_MODEL), [])
    response = provider.chat("oi", [])
    assert isinstance(response, AIResponse)
    assert response.content == "olá do modelo"
    assert response.model == DEFAULT_MODEL
    assert response.finish_reason == "stop"
    assert response.response_type is ResponseType.FINAL_RESPONSE
    assert response.usage == Usage(input_tokens=10, output_tokens=5, total_tokens=15)


def test_usage_absent_when_provider_omits_it():
    provider = make_provider(lambda kwargs: plain_response(with_usage=False), [])
    assert provider.chat("oi", []).usage is None


def test_generate_delegates_to_chat():
    provider = make_provider(lambda kwargs: plain_response("texto direto"), [])
    assert provider.generate("oi", []) == "texto direto"


# ------------------------------------------------------------------- streaming
def test_streaming_delivers_deltas_and_full_content():
    def script(kwargs):
        assert kwargs["stream"] is True
        return iter([stream_chunk("Ol"), stream_chunk("á!"), stream_chunk(None, finish="stop")])

    received: list = []
    provider = make_provider(script, [])
    response = provider.chat("oi", [], on_delta=received.append)

    assert received == ["Ol", "á!"]
    assert response.content == "Olá!"
    assert response.finish_reason == "stop"


def test_streaming_failure_after_delta_does_not_retry():
    attempts: list = []

    def script(kwargs):
        attempts.append(1)

        def gen():
            yield stream_chunk("parcial")
            raise APIConnectionError("caiu no meio")

        return gen()

    received: list = []
    provider = make_provider(script, [])
    with pytest.raises(ProviderNetworkError):
        provider.chat("oi", [], on_delta=received.append)
    assert len(attempts) == 1


# ------------------------------------------------------------- timeout/retry
def test_timeout_forwarded_to_client_and_request():
    calls: list = []
    provider = make_provider(lambda kwargs: plain_response(), calls, request_timeout=12.5)
    provider.chat("oi", [])
    factory_call = [c for c in calls if "__factory__" in c][0]["__factory__"]
    assert factory_call == ("tgp-teste", 12.5)
    assert create_calls(calls)[0]["timeout"] == 12.5


def test_retry_on_transient_errors_then_success():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise RateLimitError("429")
        return plain_response("funcionou")

    provider = make_provider(script, [])
    assert provider.chat("oi", []).content == "funcionou"
    assert attempts["n"] == 3


def test_retry_has_limit():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise APIConnectionError("sempre fora")

    provider = make_provider(script, [])
    with pytest.raises(ProviderNetworkError):
        provider.chat("oi", [])
    assert attempts["n"] == 3


def test_no_retry_on_auth_error():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise AuthenticationError("401")

    provider = make_provider(script, [])
    with pytest.raises(ProviderAuthError):
        provider.chat("oi", [])
    assert attempts["n"] == 1


def test_max_tokens_forwarded_when_requested():
    captured: list = []

    def script(kwargs):
        captured.append(kwargs)
        return plain_response()

    provider = make_provider(script, [])
    provider.chat("ping", [], max_tokens=1)
    assert create_calls(captured)[0]["max_tokens"] == 1


def test_missing_dependency_is_reported():
    from app.ai.provider import ProviderDependencyError as DepError

    def factory(api_key, timeout):
        raise DepError("Dependência 'together' não instalada.")

    settings = Settings(provider="together", api_key="tgp-x", model="",
                        data_dir="/tmp/lumen-teste")
    provider = TogetherProvider(settings, client_factory=factory)
    with pytest.raises(ProviderDependencyError):
        provider.chat("oi", [])


# ---------------------------------------------------------------- mapeamento
@pytest.mark.parametrize("exc,expected", [
    (AuthenticationError("401"), ProviderAuthError),
    (RateLimitError("429"), ProviderRateLimitError),
    (NotFoundError(), InvalidModelError),
    (InternalServerError(), ProviderServerError),
    (APITimeoutError("timeout"), ProviderTimeoutError),
    (APIConnectionError("sem rede"), ProviderNetworkError),
    (BadRequestError(), InvalidModelError),  # BadRequest citando model
])
def test_error_mapping(exc, expected):
    provider = make_provider(lambda kwargs: (_ for _ in ()).throw(exc), [])
    with pytest.raises(expected):
        provider.chat("oi", [])


def test_unknown_error_is_unexpected():
    provider = make_provider(lambda kwargs: (_ for _ in ()).throw(ValueError("estranho")), [])
    with pytest.raises(UnexpectedProviderError):
        provider.chat("oi", [])
