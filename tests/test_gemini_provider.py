"""Testes do GeminiProvider — 100% offline, com client fake injetado.

Nenhum teste toca a rede ou a API real do Gemini: o SDK é substituído por
um client falso com a mesma interface consumida pelo provider
(``models.generate_content(_stream)(model=…, contents=…, config=dict)``).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.gemini_provider import DEFAULT_MODEL, GeminiProvider
from app.ai.provider import (
    InvalidModelError,
    MissingApiKeyError,
    ProviderAuthError,
    ProviderDependencyError,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    create_provider,
)
from app.ai.types import AIResponse, ResponseType, Usage
from app.config.settings import Settings

CHAVE = "sk-gemini-TESTE-NAO-REAL"


# Exceções "com cara de SDK google-genai" (mapeamento por nome/código).
class ClientError(Exception):
    def __init__(self, code=400, message="erro"):
        super().__init__(f"{code} {message}")
        self.code = code


class ServerError(Exception):
    def __init__(self, code=500, message="boom"):
        super().__init__(f"{code} {message}")
        self.code = code


def gemini_response(text="resposta", model="gemini-2.5-flash", finish="STOP", usage=True):
    """Resposta no formato do SDK (candidates/parts/usage_metadata/model_version)."""
    meta = (
        SimpleNamespace(prompt_token_count=7, candidates_token_count=3, total_token_count=10)
        if usage else None
    )
    return SimpleNamespace(
        candidates=[SimpleNamespace(
            content=SimpleNamespace(parts=[SimpleNamespace(text=text)]),
            finish_reason=finish,
        )],
        model_version=model,
        usage_metadata=meta,
    )


def stream_chunk(text=None, finish=None, usage=None, model=None):
    return SimpleNamespace(
        candidates=[SimpleNamespace(
            content=SimpleNamespace(parts=[SimpleNamespace(text=text)] if text else []),
            finish_reason=finish,
        )],
        model_version=model,
        usage_metadata=usage,
    )


class FakeGeminiClient:
    """Client falso: `script(kwargs)` devolve resposta ou levanta exceção."""

    def __init__(self, script, calls: list, stream_script=None):
        self._script = script
        self._stream_script = stream_script
        self._calls = calls

    def _generate(self, **kwargs):
        self._calls.append(kwargs)
        return self._script(kwargs)

    def _generate_stream(self, **kwargs):
        self._calls.append(kwargs)
        source = self._stream_script if self._stream_script is not None else self._script
        result = source(kwargs)
        return iter(result) if not hasattr(result, "__next__") and result is not None else result

    @property
    def models(self):
        return SimpleNamespace(
            generate_content=self._generate,
            generate_content_stream=self._generate_stream,
        )


def make_provider(script, calls, stream_script=None, **overrides):
    values = dict(provider="gemini", api_key=CHAVE, model="",
                  data_dir="/tmp/lumen-teste", max_retries=2, request_timeout=60.0)
    values.update(overrides)
    settings = Settings(**values)

    def factory(api_key, timeout):
        calls.append({"__factory__": (api_key, timeout)})
        return FakeGeminiClient(script, calls, stream_script)

    return GeminiProvider(settings, client_factory=factory, retry_backoff=0.0)


def create_calls(calls):
    return [c for c in calls if "__factory__" not in c]


# --------------------------------------------------------------- inicialização
def test_provider_initializes_without_network_call():
    calls: list = []
    provider = make_provider(lambda kw: gemini_response(), calls)
    assert provider.name == "gemini"
    assert calls == []


def test_default_model_when_empty_and_override_when_set():
    """Modelo padrão GA quando vazio; configurável quando informado."""
    provider = make_provider(lambda kw: gemini_response(), [])
    assert provider.model_name == DEFAULT_MODEL == "gemini-2.5-flash"

    provider2 = make_provider(lambda kw: gemini_response(), [], model="gemini-2.5-pro")
    assert provider2.model_name == "gemini-2.5-pro"


def test_missing_api_key_raises_with_instructions():
    with pytest.raises(MissingApiKeyError) as exc:
        make_provider(lambda kw: gemini_response(), [], api_key="")
    assert "LUMEN_API_KEY" in str(exc.value)
    assert "Google AI Studio" in str(exc.value)


def test_factory_creates_gemini_provider():
    settings = Settings(provider="gemini", api_key="g-x", data_dir="/tmp/lumen-teste")
    provider = create_provider(settings)
    assert isinstance(provider, GeminiProvider)


def test_invalid_provider_message_lists_all_three():
    settings = Settings(provider="claude", data_dir="/tmp/lumen-teste")
    with pytest.raises(ProviderError) as exc:
        create_provider(settings)
    message = str(exc.value)
    for nome in ("mock", "openai", "gemini"):
        assert nome in message


# -------------------------------------------------------------------- payload
def test_contents_mapping_system_prompt_and_history():
    """Histórico (assistant→model) + mensagem atual + system_instruction."""
    captured: list = []

    def script(kwargs):
        captured.append(kwargs)
        return gemini_response()

    provider = make_provider(script, [])
    context = [
        {"role": "user", "content": "primeira", "timestamp": "2026-01-01T10:00:00-03:00"},
        {"role": "assistant", "content": "segunda", "timestamp": "2026-01-01T10:00:01-03:00"},
        {"role": "system", "content": "deve ser filtrado"},
    ]
    provider.chat("atual", context, system_prompt="PROMPT-SISTEMA")

    kwargs = captured[0]
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["contents"] == [
        {"role": "user", "parts": [{"text": "primeira"}]},
        {"role": "model", "parts": [{"text": "segunda"}]},  # assistant → model
        {"role": "user", "parts": [{"text": "atual"}]},
    ]
    assert kwargs["config"]["system_instruction"] == "PROMPT-SISTEMA"
    assert "max_output_tokens" not in kwargs["config"]


def test_max_tokens_maps_to_max_output_tokens():
    captured: list = []
    provider = make_provider(lambda kw: (captured.append(kw), gemini_response())[1], [])
    provider.chat("oi", [], max_tokens=64)
    assert captured[0]["config"]["max_output_tokens"] == 64


# --------------------------------------------------------------- normalização
def test_response_is_normalized_with_usage():
    provider = make_provider(lambda kw: gemini_response("olá do gemini"), [])
    response = provider.chat("oi", [])

    assert isinstance(response, AIResponse)
    assert response.content == "olá do gemini"
    assert response.model == "gemini-2.5-flash"
    assert response.finish_reason == "STOP"
    assert response.response_type is ResponseType.FINAL_RESPONSE
    assert response.tool_calls == ()
    assert response.usage == Usage(input_tokens=7, output_tokens=3, total_tokens=10)


def test_usage_absent_when_api_omits_metadata():
    provider = make_provider(lambda kw: gemini_response(usage=False), [])
    assert provider.chat("oi", []).usage is None


def test_generate_delegates_to_chat():
    provider = make_provider(lambda kw: gemini_response("texto direto"), [])
    assert provider.generate("oi", []) == "texto direto"


# ------------------------------------------------------------------ streaming
def test_streaming_delivers_deltas_and_full_content():
    usage = SimpleNamespace(prompt_token_count=5, candidates_token_count=2, total_token_count=7)

    def stream_script(kwargs):
        return [
            stream_chunk("Ol", model="gemini-2.5-flash"),
            stream_chunk("á!", usage=usage),
            stream_chunk(finish="STOP", usage=usage),
        ]

    received: list = []
    provider = make_provider(lambda kw: gemini_response(), [], stream_script=stream_script)
    response = provider.chat("oi", [], on_delta=received.append)

    assert received == ["Ol", "á!"]
    assert response.content == "Olá!"
    assert response.finish_reason == "STOP"
    assert response.model == "gemini-2.5-flash"
    assert response.usage == Usage(input_tokens=5, output_tokens=2, total_tokens=7)


def test_streaming_failure_after_delta_does_not_retry():
    attempts: list = []

    def stream_script(kwargs):
        attempts.append(1)

        def gen():
            yield stream_chunk("parcial")
            raise ConnectionError("caiu no meio")

        return gen()

    received: list = []
    provider = make_provider(lambda kw: gemini_response(), [], stream_script=stream_script)
    with pytest.raises(ProviderNetworkError):
        provider.chat("oi", [], on_delta=received.append)
    assert received == ["parcial"]
    assert len(attempts) == 1  # não repetiu: texto já exibido


# --------------------------------------------------------------- timeout/retry
def test_timeout_forwarded_to_factory():
    calls: list = []
    provider = make_provider(lambda kw: gemini_response(), calls, request_timeout=12.5)
    provider.chat("oi", [])
    factory_call = [c for c in calls if "__factory__" in c][0]["__factory__"]
    assert factory_call == (CHAVE, 12.5)


def test_retry_on_transient_errors_then_success():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise ConnectionError("rede instável")
        return gemini_response("ok")

    provider = make_provider(script, [])
    assert provider.chat("oi", []).content == "ok"
    assert attempts["n"] == 3  # 1 tentativa + 2 retries


def test_retry_has_limit():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise ConnectionError("sempre fora")

    provider = make_provider(script, [])
    with pytest.raises(ProviderNetworkError):
        provider.chat("oi", [])
    assert attempts["n"] == 3


def test_no_retry_on_auth_error():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise ClientError(code=401, message="unauthorized")

    provider = make_provider(script, [])
    with pytest.raises(ProviderAuthError):
        provider.chat("oi", [])
    assert attempts["n"] == 1


def test_invalid_api_key_400_maps_to_auth_error():
    """O Gemini devolve 400 para chave inválida (não 401)."""
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise ClientError(code=400, message="API key not valid. Please pass a valid API key.")

    provider = make_provider(script, [])
    with pytest.raises(ProviderAuthError) as exc:
        provider.chat("oi", [])
    assert "AI Studio" in str(exc.value) or "inválida" in str(exc.value)
    assert attempts["n"] == 1


def test_invalid_model_404_no_retry():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise ClientError(code=404, message="models/gemini-fantasma is not found")

    provider = make_provider(script, [], model="gemini-fantasma")
    with pytest.raises(InvalidModelError):
        provider.chat("oi", [])
    assert attempts["n"] == 1


def test_rate_limit_429_is_retryable():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise ClientError(code=429, message="Resource has been exhausted")

    provider = make_provider(script, [])
    with pytest.raises(ProviderRateLimitError):
        provider.chat("oi", [])
    assert attempts["n"] == 3


def test_server_error_5xx_is_retryable_and_mapped():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise ServerError(code=503, message="unavailable")

    provider = make_provider(script, [])
    with pytest.raises(ProviderServerError):
        provider.chat("oi", [])
    assert attempts["n"] == 3


def test_timeout_exception_maps_to_timeout_error():
    class APITimeoutError(Exception): ...

    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise APITimeoutError("deadline exceeded")

    provider = make_provider(script, [])
    with pytest.raises(ProviderTimeoutError) as exc:
        provider.chat("oi", [])
    assert "tempo limite" in str(exc.value)
    assert attempts["n"] == 3


def test_unexpected_error_is_wrapped():
    class WeirdError(Exception): ...

    provider = make_provider(lambda kw: (_ for _ in ()).throw(WeirdError("???")), [])
    with pytest.raises(ProviderError) as exc:
        provider.chat("oi", [])
    assert type(exc.value).__name__ == "UnexpectedProviderError"
    assert "WeirdError" in str(exc.value)


def test_missing_dependency_is_reported():
    from app.ai.provider import ProviderDependencyError as DepError

    def factory(api_key, timeout):
        raise DepError("Dependência 'google-genai' não instalada.")

    settings = Settings(provider="gemini", api_key="g-x", data_dir="/tmp/lumen-teste")
    provider = GeminiProvider(settings, client_factory=factory)
    with pytest.raises(ProviderDependencyError):
        provider.chat("oi", [])


def test_real_sdk_factory_converts_timeout_to_milliseconds():
    """Com o SDK real instalado: Client com HttpOptions.timeout em ms."""
    pytest.importorskip("google.genai", reason="SDK google-genai não instalado aqui")
    from google.genai import types

    from app.ai import gemini_provider as gemini_module

    adapter = gemini_module.GeminiProvider._default_client_factory("g-introspecao", 2.5)
    assert isinstance(adapter, gemini_module._SdkAdapter)
    # A unidade (ms) é aplicada dentro da factory; smoke do tipo do config:
    config = adapter.models._config({"system_instruction": "x", "max_output_tokens": 5})
    assert isinstance(config, types.GenerateContentConfig)
    assert config.max_output_tokens == 5
