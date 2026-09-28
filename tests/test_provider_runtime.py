from __future__ import annotations

import pytest

from app.ai.provider import AIProvider, ProviderAuthError, ProviderNetworkError, ProviderTimeoutError
from app.ai.provider_runtime import ProviderRuntime, RuntimeProviderSpec, RuntimeRequest
from app.ai.types import AIResponse
from app.evolution.intelligence_stack import StackLayer


class FakeProvider(AIProvider):
    def __init__(self, name: str, responses: list[object]):
        self.name = name
        self.responses = list(responses)

    @property
    def model_name(self):
        return f"{self.name}-model"

    def generate(self, message, context=None):
        return str(message)

    def chat(self, message, context=None, **kwargs):
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return AIResponse(content=str(value), model=self.model_name)


def spec(pid, provider, *, local=False, cost=0.0, reliability=1.0, context=8192, enabled=True):
    return RuntimeProviderSpec(
        pid, provider, frozenset({StackLayer.REASONING, StackLayer.CODING}),
        reliability, cost, context, local, enabled,
    )


def req(**kwargs):
    return RuntimeRequest("REQ-000001", frozenset({StackLayer.REASONING}), **kwargs)


def test_requires_explicit_authorization():
    runtime = ProviderRuntime((spec("local", FakeProvider("local", ["ok"]), local=True),))
    with pytest.raises(PermissionError):
        runtime.execute_chat(req(), "hello")


def test_local_provider_can_execute_when_authorized():
    runtime = ProviderRuntime((spec("ollama", FakeProvider("ollama", ["local ok"]), local=True),))
    result = runtime.execute_chat(req(), "hello", authorized=True)
    assert result.provider_id == "ollama"
    assert result.response.content == "local ok"
    assert result.attempts[0].success is True


def test_falls_back_after_network_failure():
    local = FakeProvider("local", [ProviderNetworkError("offline")])
    remote = FakeProvider("remote", ["remote ok"])
    runtime = ProviderRuntime((
        spec("ollama", local, local=True, cost=0.0),
        spec("groq", remote, local=False, cost=0.2),
    ))
    result = runtime.execute_chat(req(preferred_provider_ids=("ollama", "groq")), "hello", authorized=True)
    assert result.provider_id == "groq"
    assert [a.provider_id for a in result.attempts] == ["ollama", "groq"]


def test_retries_timeout_within_bound():
    local = FakeProvider("local", [ProviderTimeoutError("t1"), "ok"])
    runtime = ProviderRuntime((spec("ollama", local, local=True),), max_retries_per_provider=1)
    result = runtime.execute_chat(req(), "hello", authorized=True)
    assert result.provider_id == "ollama"
    assert len(result.attempts) == 2


def test_auth_failure_does_not_retry_same_provider():
    provider = FakeProvider("cloud", [ProviderAuthError("bad key"), "should not happen"])
    runtime = ProviderRuntime((spec("cloud", provider),), max_retries_per_provider=2)
    with pytest.raises(Exception):
        runtime.execute_chat(req(), "hello", authorized=True)
    assert len(provider.responses) == 1


def test_auth_failure_can_fallback_to_compatible_provider():
    bad = FakeProvider("cloud", [ProviderAuthError("bad key")])
    local = FakeProvider("local", ["safe local"])
    runtime = ProviderRuntime((
        spec("cloud", bad, local=False, cost=0.2),
        spec("ollama", local, local=True, cost=0.0),
    ))
    result = runtime.execute_chat(req(preferred_provider_ids=("cloud", "ollama")), "hello", authorized=True)
    assert result.provider_id == "ollama"


def test_incompatible_provider_is_not_called():
    bad = FakeProvider("bad", ["should not execute"])
    good = FakeProvider("good", ["ok"])
    runtime = ProviderRuntime((
        spec("bad", bad, context=128),
        spec("good", good, context=8192),
    ))
    result = runtime.execute_chat(req(min_context_window=4096), "hello", authorized=True)
    assert result.provider_id == "good"
    assert bad.responses == ["should not execute"]


def test_cost_limit_is_enforced():
    expensive = FakeProvider("expensive", ["bad"])
    local = FakeProvider("local", ["ok"])
    runtime = ProviderRuntime((
        spec("expensive", expensive, cost=10.0),
        spec("ollama", local, local=True, cost=0.0),
    ))
    result = runtime.execute_chat(req(max_cost_per_unit=1.0), "hello", authorized=True)
    assert result.provider_id == "ollama"


def test_disabled_provider_is_not_called():
    disabled = FakeProvider("disabled", ["bad"])
    good = FakeProvider("good", ["ok"])
    runtime = ProviderRuntime((
        spec("disabled", disabled, enabled=False),
        spec("good", good),
    ))
    result = runtime.execute_chat(req(), "hello", authorized=True)
    assert result.provider_id == "good"


def test_provider_authorization_hook_can_deny_one_provider():
    first = FakeProvider("first", ["bad"])
    second = FakeProvider("second", ["ok"])
    runtime = ProviderRuntime(
        (spec("first", first), spec("second", second)),
        authorization=lambda request, pid: pid != "first",
    )
    result = runtime.execute_chat(req(preferred_provider_ids=("first", "second")), "hello", authorized=True)
    assert result.provider_id == "second"
    assert result.attempts[0].error_type == "authorization_denied"


def test_no_compatible_provider_is_fail_closed():
    runtime = ProviderRuntime((spec("local", FakeProvider("local", ["bad"]), local=True, context=128),))
    with pytest.raises(LookupError):
        runtime.execute_chat(req(min_context_window=4096), "hello", authorized=True)


def test_non_retryable_provider_error_falls_back_once():
    class BoomProvider(FakeProvider):
        def chat(self, *args, **kwargs):
            raise ValueError("unexpected")
    runtime = ProviderRuntime((
        spec("boom", BoomProvider("boom", [])),
        spec("good", FakeProvider("good", ["ok"])),
    ))
    with pytest.raises(ValueError):
        runtime.execute_chat(req(preferred_provider_ids=("boom", "good")), "hello", authorized=True)


def test_empty_response_falls_back():
    empty = FakeProvider("empty", [""])
    good = FakeProvider("good", ["ok"])
    runtime = ProviderRuntime((
        spec("empty", empty),
        spec("good", good),
    ))
    result = runtime.execute_chat(req(preferred_provider_ids=("empty", "good")), "hello", authorized=True)
    assert result.provider_id == "good"


def test_context_and_system_prompt_are_forwarded():
    seen = {}
    class Inspect(FakeProvider):
        def chat(self, message, context=None, **kwargs):
            seen["message"] = message
            seen["context"] = context
            seen.update(kwargs)
            return AIResponse(content="ok", model=self.model_name)
    runtime = ProviderRuntime((spec("local", Inspect("local", []), local=True),))
    runtime.execute_chat(req(), "hello", [{"role":"user","content":"previous"}], system_prompt="system", max_tokens=99, authorized=True)
    assert seen["context"][0]["content"] == "previous"
    assert seen["system_prompt"] == "system"
    assert seen["max_tokens"] == 99


def test_duplicate_provider_rejected():
    p=FakeProvider("x", ["ok"])
    with pytest.raises(ValueError):
        ProviderRuntime((spec("x", p), spec("x", p)))


def test_runtime_request_validation():
    with pytest.raises(ValueError):
        RuntimeRequest("", frozenset({StackLayer.REASONING})).validate()
