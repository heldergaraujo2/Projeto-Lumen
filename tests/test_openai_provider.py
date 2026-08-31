"""Testes do OpenAIProvider — 100% offline, com client fake injetado.

Nenhum teste aqui toca a rede ou a API real: o SDK é substituído por um
``client_factory`` falso que registra as chamadas e devolve respostas
scriptadas.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.openai_provider import OpenAIProvider
from app.ai.provider import (
    InvalidModelError,
    MissingApiKeyError,
    ModelNotConfiguredError,
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

# Exceções "com cara de SDK" — o mapeamento é por nome/status_code, então
# os testes não precisam do pacote openai instalado.
class APIConnectionError(Exception): ...
class APITimeoutError(Exception): ...
class AuthenticationError(Exception): ...
class RateLimitError(Exception): ...
class NotFoundError(Exception):
    def __init__(self): super().__init__("model not found"); self.status_code = 404
class InternalServerError(Exception):
    def __init__(self): super().__init__("boom"); self.status_code = 500


def plain_response(content="resposta", model="gpt-teste", finish="stop", with_usage=True):
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
    values = dict(provider="openai", api_key="sk-teste", model="gpt-teste",
                  data_dir="/tmp/lumen-teste", max_retries=2, request_timeout=60.0)
    values.update(overrides)
    settings = Settings(**values)

    def factory(api_key, timeout):
        calls.append({"__factory__": (api_key, timeout)})
        return FakeClient(script, calls)

    return OpenAIProvider(settings, client_factory=factory, retry_backoff=0.0)


def create_calls(calls):
    return [c for c in calls if "__factory__" not in c]


# --------------------------------------------------------------- inicialização
def test_provider_initializes_without_network_call():
    """2. Init não dispara nenhuma chamada real (factory não é invocada)."""
    calls: list = []
    provider = make_provider(lambda kwargs: plain_response(), calls)
    assert provider.name == "openai"
    assert provider.model_name == "gpt-teste"
    assert calls == []  # nada aconteceu além da configuração


def test_missing_api_key_raises_with_instructions():
    """3. API Key ausente gera erro apropriado e explica como configurar."""
    with pytest.raises(MissingApiKeyError) as exc:
        make_provider(lambda kwargs: plain_response(), [], api_key="")
    assert "LUMEN_API_KEY" in str(exc.value)
    assert ".env" in str(exc.value)


def test_missing_model_raises_with_instructions():
    with pytest.raises(ModelNotConfiguredError) as exc:
        make_provider(lambda kwargs: plain_response(), [], model="")
    assert "LUMEN_MODEL" in str(exc.value)
    assert "gpt-" in str(exc.value)  # exemplo de modelo válido na mensagem


def test_factory_creates_openai_provider():
    settings = Settings(provider="openai", api_key="sk-x", model="gpt-teste",
                        data_dir="/tmp/lumen-teste")
    provider = create_provider(settings)
    assert isinstance(provider, OpenAIProvider)


def test_invalid_provider_still_rejected():
    """4. Provider inválido gera erro apropriado (fábrica)."""
    settings = Settings(provider="claude-mágico", data_dir="/tmp/lumen-teste")
    with pytest.raises(ProviderError) as exc:
        create_provider(settings)
    assert "mock" in str(exc.value) and "openai" in str(exc.value)


# ------------------------------------------------------------------- mensagens
def test_message_payload_structure():
    """6/7. Modelo configurável + system prompt + histórico + mensagem atual."""
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
    assert kwargs["model"] == "gpt-teste"
    assert kwargs["messages"] == [
        {"role": "system", "content": "PROMPT-SISTEMA"},
        {"role": "user", "content": "primeira"},      # timestamp removido
        {"role": "assistant", "content": "segunda"},  # role system filtrada
        {"role": "user", "content": "atual"},
    ]
    assert "stream" not in kwargs


def test_response_is_normalized():
    """12. Resposta do modelo é normalizada em AIResponse."""
    provider = make_provider(lambda kwargs: plain_response("olá do modelo", model="gpt-teste"),
                             [])
    response = provider.chat("oi", [])
    assert isinstance(response, AIResponse)
    assert response.content == "olá do modelo"
    assert response.model == "gpt-teste"
    assert response.finish_reason == "stop"
    assert response.response_type is ResponseType.FINAL_RESPONSE
    assert response.tool_calls == ()
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
    """Sem retry quando já houve streaming visível (evitaria duplicar texto)."""
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
    assert received == ["parcial"]
    assert len(attempts) == 1  # não repetiu: texto já havia sido exibido


# ------------------------------------------------------------- timeout/retry
def test_timeout_forwarded_to_client_and_request():
    """9. Timeout configurado é repassado ao client e à requisição."""
    calls: list = []
    provider = make_provider(lambda kwargs: plain_response(), calls, request_timeout=12.5)
    provider.chat("oi", [])
    factory_call = [c for c in calls if "__factory__" in c][0]["__factory__"]
    assert factory_call == ("sk-teste", 12.5)
    assert create_calls(calls)[0]["timeout"] == 12.5


def test_retry_on_transient_errors_then_success():
    """10. Retry apenas para erros temporários — com limite."""
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise APIConnectionError("rede instável")
        return plain_response("funcionou")

    provider = make_provider(script, [])
    assert provider.chat("oi", []).content == "funcionou"
    assert attempts["n"] == 3  # 1 tentativa + 2 retries


def test_retry_has_limit():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise APIConnectionError("sempre fora")

    provider = make_provider(script, [])
    with pytest.raises(ProviderNetworkError):
        provider.chat("oi", [])
    assert attempts["n"] == 3  # 1 + LUMEN_MAX_RETRIES=2, nunca infinito


def test_no_retry_on_auth_error():
    """10. Erro de autenticação NÃO é repetido."""
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise AuthenticationError("chave inválida")

    provider = make_provider(script, [])
    with pytest.raises(ProviderAuthError):
        provider.chat("oi", [])
    assert attempts["n"] == 1


def test_no_retry_on_invalid_model():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise NotFoundError()

    provider = make_provider(script, [])
    with pytest.raises(InvalidModelError):
        provider.chat("oi", [])
    assert attempts["n"] == 1


def test_rate_limit_is_retryable_and_mapped():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise RateLimitError("429")

    provider = make_provider(script, [])
    with pytest.raises(ProviderRateLimitError):
        provider.chat("oi", [])
    assert attempts["n"] == 3


def test_timeout_error_is_retryable_and_mapped():
    attempts = {"n": 0}

    def script(kwargs):
        attempts["n"] += 1
        raise APITimeoutError("demorou")

    provider = make_provider(script, [])
    with pytest.raises(ProviderTimeoutError) as exc:
        provider.chat("oi", [])
    assert "60" in str(exc.value) or "limite" in str(exc.value)
    assert attempts["n"] == 3


# --------------------------------------------------- mapeamento por status_code
@pytest.mark.parametrize("exc,esperado", [
    (AuthenticationError("x"), ProviderAuthError),
    (RateLimitError("x"), ProviderRateLimitError),
    (NotFoundError(), InvalidModelError),
    (InternalServerError(), ProviderServerError),
])
def test_mapping_by_exception_name(exc, esperado):
    provider = make_provider(lambda kwargs: (_ for _ in ()).throw(exc), [])
    with pytest.raises(esperado):
        provider.chat("oi", [])


def test_mapping_by_status_code():
    """11. Erros convertidos para a taxonomia interna (via status HTTP)."""
    for status, esperado in [(401, ProviderAuthError), (429, ProviderRateLimitError),
                             (500, ProviderServerError)]:
        class HTTPError(Exception):
            def __init__(self): super().__init__("http"); self.status_code = status

        provider = make_provider(lambda kwargs: (_ for _ in ()).throw(HTTPError()), [])
        with pytest.raises(esperado):
            provider.chat("oi", [])


def test_unexpected_error_is_wrapped():
    class WeirdError(Exception): ...

    provider = make_provider(lambda kwargs: (_ for _ in ()).throw(WeirdError("???")), [])
    with pytest.raises(ProviderError) as exc:
        provider.chat("oi", [])
    assert type(exc.value).__name__ == "UnexpectedProviderError"
    assert "WeirdError" in str(exc.value)


def test_max_tokens_fallback_for_models_that_reject_it():
    """Modelos novos (ex.: série o) rejeitam max_tokens: repete sem o parâmetro."""
    class BadRequestError(Exception):
        def __init__(self):
            super().__init__(
                "Unsupported parameter: 'max_tokens' is not supported with this "
                "model. Use 'max_completion_tokens' instead."
            )

    calls: list = []

    def script(kwargs):
        calls.append(kwargs)
        if "max_tokens" in kwargs:
            raise BadRequestError()
        return plain_response("ok")

    provider = make_provider(script, [])
    response = provider.chat("ping", [], max_tokens=1)

    assert response.content == "ok"
    assert len(calls) == 2
    assert calls[0]["max_tokens"] == 1
    assert "max_tokens" not in calls[1]


def test_missing_dependency_is_reported():
    """SDK ausente vira erro claro (não ImportError cru)."""
    from app.ai.provider import ProviderDependencyError as DepError

    def factory(api_key, timeout):
        raise DepError("Dependência 'openai' não instalada.")

    settings = Settings(provider="openai", api_key="sk-x", model="gpt-teste",
                        data_dir="/tmp/lumen-teste")
    provider = OpenAIProvider(settings, client_factory=factory)
    with pytest.raises(ProviderDependencyError):
        provider.chat("oi", [])
