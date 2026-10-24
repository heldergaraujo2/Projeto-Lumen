from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from app.ai.ollama_provider import DEFAULT_BASE_URL, DEFAULT_MODEL, OllamaProvider
from app.ai.provider import InvalidModelError, ProviderError, ProviderNetworkError
from app.config.settings import Settings


def make_settings(**kwargs):
    values = {"provider": "ollama", "model": "", "request_timeout": 5.0, "max_retries": 0}
    values.update(kwargs)
    return Settings(**values)


def test_defaults_are_local_first():
    provider = OllamaProvider(make_settings())
    assert provider.model_name == DEFAULT_MODEL
    assert provider.base_url == DEFAULT_BASE_URL


def test_chat_normalizes_stream_and_usage():
    events = [
        b'{"model":"qwen2.5-coder:7b-instruct-q8_0","message":{"role":"assistant","content":"Ol\\u00e1 "},"done":false}\n',
        b'{"model":"qwen2.5-coder:7b-instruct-q8_0","message":{"role":"assistant","content":"Lumen"},"done":true,"done_reason":"stop","prompt_eval_count":4,"eval_count":6}\n',
    ]

    def transport(method, url, body, timeout):
        assert method == "POST"
        assert url == DEFAULT_BASE_URL + "/api/chat"
        assert timeout == 5.0
        payload = json.loads(body.decode())
        assert payload["model"] == DEFAULT_MODEL
        assert payload["stream"] is True
        assert payload["think"] is False
        assert "format" not in payload
        assert payload["messages"][-1]["content"] == "Olá"
        yield from events

    provider = OllamaProvider(make_settings(), transport=transport)
    deltas = []
    response = provider.chat(
        "Olá", [{"role": "user", "content": "antes"}],
        system_prompt="Você é a Lumen.", on_delta=deltas.append, max_tokens=32,
    )
    assert response.content == "Olá Lumen"
    assert response.model == DEFAULT_MODEL
    assert response.usage.input_tokens == 4
    assert response.usage.output_tokens == 6
    assert response.usage.total_tokens == 10
    assert deltas == ["Olá ", "Lumen"]


def test_thinking_mode_is_configurable():
    def transport(method, url, body, timeout):
        payload = json.loads(body.decode())
        assert payload["think"] is True
        yield b'{"model":"qwen3:8b","message":{"role":"assistant","content":"resposta"},"done":true,"done_reason":"stop"}\n'

    provider = OllamaProvider(make_settings(ollama_think=True), transport=transport)
    assert provider.chat("Olá").content == "resposta"


def test_health_check_and_list_models():
    payload = b'{"models":[{"name":"qwen2.5-coder:7b-instruct-q8_0"},{"name":"llama3:8b"}]}'
    provider = OllamaProvider(make_settings(), transport=lambda *args: iter([payload]))
    assert provider.health_check() is True
    assert provider.list_models() == ("qwen2.5-coder:7b-instruct-q8_0", "llama3:8b")


def test_api_model_not_found_is_typed():
    def transport(method, url, body, timeout):
        raise HTTPError(url, 404, "not found", {}, BytesIO(b'{"error":"model not found"}'))
        yield b""

    provider = OllamaProvider(make_settings(), transport=transport)
    with pytest.raises(InvalidModelError):
        provider.chat("Olá")


def test_network_failure_is_typed():
    def transport(*args):
        raise OSError("connection refused")
        yield b""

    provider = OllamaProvider(make_settings(), transport=transport)
    with pytest.raises(ProviderNetworkError):
        provider.chat("Olá")


def test_empty_stream_is_rejected():
    provider = OllamaProvider(make_settings(), transport=lambda *args: iter([b'{"done":true}']))
    with pytest.raises(ProviderError):
        provider.chat("Olá")


def test_invalid_max_tokens_is_rejected():
    provider = OllamaProvider(make_settings(), transport=lambda *args: iter([]))
    with pytest.raises(ValueError):
        provider.chat("Olá", max_tokens=0)


def test_chat_requests_json_format_only_when_enabled():
    def transport(method, url, body, timeout):
        payload = json.loads(body.decode())
        assert payload.get("format") == "json"
        event = {
            "model": "qwen2.5-coder:7b-instruct-q8_0",
            "message": {"role": "assistant", "content": json.dumps({"type": "conversation"})},
            "done": True,
        }
        yield (json.dumps(event) + "\n").encode("utf-8")

    provider = OllamaProvider(make_settings(), transport=transport)
    response = provider.chat("Planeje", json_format=True)
    assert json.loads(response.content) == {"type": "conversation"}


def test_chat_sends_structured_json_schema_without_rebuilding_messages():
    schema = {
        "type": "object",
        "required": ["type"],
        "properties": {"type": {"const": "conversation"}},
    }
    previous = [
        {"role": "user", "content": "mensagem anterior"},
        {"role": "assistant", "content": "resposta anterior"},
    ]

    def transport(method, url, body, timeout):
        payload = json.loads(body.decode("utf-8"))
        assert payload["format"] == schema
        assert payload["messages"] == [
            {"role": "system", "content": "PROMPT COMPLETO"},
            *previous,
            {"role": "user", "content": "mensagem atual"},
        ]
        event = {
            "model": "qwen2.5-coder:7b",
            "message": {
                "role": "assistant",
                "content": '{"type":"conversation"}',
            },
            "done": True,
        }
        yield (json.dumps(event) + "\n").encode("utf-8")

    provider = OllamaProvider(make_settings(model="qwen2.5-coder:7b"), transport=transport)
    response = provider.chat(
        "mensagem atual", previous, system_prompt="PROMPT COMPLETO",
        json_schema=schema,
    )
    assert response.content == '{"type":"conversation"}'


def test_json_schema_must_be_an_object():
    provider = OllamaProvider(make_settings(), transport=lambda *args: iter([]))
    with pytest.raises(ValueError, match="json_schema"):
        provider.chat("Oi", json_schema=["not", "an", "object"])
