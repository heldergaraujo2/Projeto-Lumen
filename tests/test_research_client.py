"""Testes da camada de pesquisa web (Fase 1) — sem rede real.

Todo o transporte HTTP é injetado (``transport=``), então nenhum teste
toca a internet. As respostas usadas como fixture seguem o formato
documentado de cada provedor.
"""
from __future__ import annotations

import json

import pytest

from app.research.client import (
    BRAVE_KEY_ENV_VARS,
    MAX_RESPONSE_BYTES,
    MAX_RESULTS_CEILING,
    TAVILY_KEY_ENV_VARS,
    BraveSearchProvider,
    SearchProviderError,
    SearchResponseTooLargeError,
    SearchUnavailableError,
    TavilySearchProvider,
    create_search_provider,
    redact_secret,
)
from app.research.models import MAX_SNIPPET_CHARS, SearchResult, WebSearchResponse


# --------------------------------------------------------------------- helpers
class RecordingTransport:
    """Transporte fake: grava a chamada e devolve uma resposta programada."""

    def __init__(self, status: int = 200, payload: bytes = b"{}"):
        self.status = status
        self.payload = payload
        self.calls: list[dict] = []

    def __call__(self, method, url, body, headers, timeout):
        self.calls.append(
            {"method": method, "url": url, "body": body, "headers": dict(headers), "timeout": timeout}
        )
        return self.status, self.payload

    @property
    def last(self) -> dict:
        return self.calls[-1]

    def last_json(self) -> dict:
        return json.loads(self.last["body"].decode("utf-8"))


def tavily_payload(*results, answer=None) -> bytes:
    body = {
        "query": "unreal blueprint inventory",
        "results": list(results),
        "response_time": 1.23,
    }
    if answer is not None:
        body["answer"] = answer
    return json.dumps(body).encode("utf-8")


SAMPLE_RESULT = {
    "title": "Creating Inventory Systems in Unreal Engine 5",
    "url": "https://dev.epicgames.com/community/learning/tutorials/inventory",
    "content": "Use a component-based approach with UDataAsset for item definitions.",
    "score": 0.93,
}


# ------------------------------------------------------------------ Tavily
def test_tavily_sends_bearer_token_and_not_key_in_body():
    """A Tavily descontinuou `api_key` no corpo: a chave vai no header."""
    transport = RecordingTransport(payload=tavily_payload(SAMPLE_RESULT))
    provider = TavilySearchProvider(api_key="tvly-SECRET123", transport=transport)

    response = provider.search("unreal blueprint inventory")

    assert transport.last["headers"]["Authorization"] == "Bearer tvly-SECRET123"
    assert "api_key" not in transport.last_json()
    assert transport.last["method"] == "POST"
    assert transport.last["url"] == "https://api.tavily.com/search"
    assert response.provider == "tavily"
    assert len(response.results) == 1
    assert response.results[0].url == SAMPLE_RESULT["url"]
    assert response.results[0].score == pytest.approx(0.93)


def test_tavily_never_leaks_key_in_result_or_error():
    transport = RecordingTransport(
        status=401, payload=b'{"detail":"invalid key tvly-SECRET123"}'
    )
    provider = TavilySearchProvider(api_key="tvly-SECRET123", transport=transport)

    with pytest.raises(SearchProviderError) as excinfo:
        provider.search("anything")

    assert "tvly-SECRET123" not in str(excinfo.value)
    assert "REDACTED" in str(excinfo.value)


def test_tavily_requires_key_unless_keyless_opt_in():
    provider = TavilySearchProvider(api_key="", transport=RecordingTransport())
    with pytest.raises(SearchUnavailableError, match="sem chave"):
        provider.search("q")
    assert provider.has_key is False


def test_tavily_keyless_mode_sets_access_mode_header():
    transport = RecordingTransport(payload=tavily_payload(SAMPLE_RESULT))
    provider = TavilySearchProvider(api_key="", allow_keyless=True, transport=transport)

    response = provider.search("q")

    assert transport.last["headers"]["X-Tavily-Access-Mode"] == "keyless"
    assert "Authorization" not in transport.last["headers"]
    assert any("keyless" in note for note in response.notes)


def test_tavily_clamps_max_results_to_ceiling():
    transport = RecordingTransport(payload=tavily_payload())
    provider = TavilySearchProvider(api_key="k", transport=transport)

    provider.search("q", max_results=500)

    assert transport.last_json()["max_results"] == MAX_RESULTS_CEILING


def test_tavily_rejects_non_positive_max_results():
    provider = TavilySearchProvider(api_key="k", transport=RecordingTransport())
    with pytest.raises(ValueError, match="max_results"):
        provider.search("q", max_results=0)


def test_tavily_rejects_empty_query():
    provider = TavilySearchProvider(api_key="k", transport=RecordingTransport())
    with pytest.raises(ValueError, match="query"):
        provider.search("   ")


def test_tavily_discards_non_http_urls():
    """Um provedor comprometido não pode injetar file:// ou javascript:."""
    transport = RecordingTransport(
        payload=tavily_payload(
            {"title": "evil", "url": "file:///etc/passwd", "content": "x", "score": 0.5},
            {"title": "evil2", "url": "javascript:alert(1)", "content": "x", "score": 0.5},
            SAMPLE_RESULT,
        )
    )
    provider = TavilySearchProvider(api_key="k", transport=transport)

    response = provider.search("q")

    assert len(response.results) == 1
    assert response.results[0].url == SAMPLE_RESULT["url"]
    assert any("descartado" in note for note in response.notes)


def test_tavily_truncates_oversized_snippets():
    transport = RecordingTransport(
        payload=tavily_payload({**SAMPLE_RESULT, "content": "x" * 50_000})
    )
    provider = TavilySearchProvider(api_key="k", transport=transport)

    response = provider.search("q")

    assert len(response.results[0].content) == MAX_SNIPPET_CHARS


def test_tavily_rejects_oversized_response_body():
    transport = RecordingTransport(payload=b"x" * (MAX_RESPONSE_BYTES + 10))
    provider = TavilySearchProvider(api_key="k", transport=transport)

    with pytest.raises(SearchResponseTooLargeError):
        provider.search("q")


def test_tavily_raises_on_malformed_json():
    transport = RecordingTransport(payload=b"<html>502 Bad Gateway</html>")
    provider = TavilySearchProvider(api_key="k", transport=transport)

    with pytest.raises(SearchProviderError, match="JSON"):
        provider.search("q")


def test_tavily_raises_on_http_error_status():
    transport = RecordingTransport(status=429, payload=b'{"detail":"rate limited"}')
    provider = TavilySearchProvider(api_key="k", transport=transport)

    with pytest.raises(SearchProviderError, match="429"):
        provider.search("q")


def test_tavily_rejects_unknown_search_depth():
    with pytest.raises(ValueError, match="search_depth"):
        TavilySearchProvider(api_key="k", search_depth="turbo")


def test_tavily_includes_answer_when_requested():
    transport = RecordingTransport(payload=tavily_payload(SAMPLE_RESULT, answer="Use UDataAsset."))
    provider = TavilySearchProvider(api_key="k", transport=transport, include_answer=True)

    response = provider.search("q")

    assert response.answer == "Use UDataAsset."


def test_tavily_handles_results_not_a_list():
    transport = RecordingTransport(payload=json.dumps({"results": "nope"}).encode())
    provider = TavilySearchProvider(api_key="k", transport=transport)

    with pytest.raises(SearchProviderError, match="lista"):
        provider.search("q")


# ------------------------------------------------------------------- Brave
def test_brave_sends_subscription_token_header():
    payload = json.dumps(
        {"web": {"results": [{"title": "T", "url": "https://example.com/a", "description": "D"}]}}
    ).encode()
    transport = RecordingTransport(payload=payload)
    provider = BraveSearchProvider(api_key="brave-KEY", transport=transport)

    response = provider.search("unreal inventory", max_results=3)

    assert transport.last["headers"]["X-Subscription-Token"] == "brave-KEY"
    assert transport.last["method"] == "GET"
    assert "q=unreal" in transport.last["url"]
    assert "count=3" in transport.last["url"]
    assert response.provider == "brave"
    assert response.results[0].score == pytest.approx(1.0)


def test_brave_requires_key():
    provider = BraveSearchProvider(api_key="", transport=RecordingTransport())
    with pytest.raises(SearchUnavailableError, match="Brave"):
        provider.search("q")


def test_brave_scores_decay_with_rank():
    payload = json.dumps(
        {
            "web": {
                "results": [
                    {"title": "A", "url": "https://a.test", "description": "d"},
                    {"title": "B", "url": "https://b.test", "description": "d"},
                ]
            }
        }
    ).encode()
    provider = BraveSearchProvider(api_key="k", transport=RecordingTransport(payload=payload))

    response = provider.search("q")

    assert response.results[0].score > response.results[1].score


# ------------------------------------------------------------------ factory
def test_factory_uses_tavily_when_key_present(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-x")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("LUMEN_SEARCH_PROVIDER", raising=False)
    assert isinstance(create_search_provider(), TavilySearchProvider)


def test_factory_uses_brave_when_only_brave_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("LUMEN_TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("BRAVE_API_KEY", "brave-x")
    monkeypatch.delenv("LUMEN_SEARCH_PROVIDER", raising=False)
    assert isinstance(create_search_provider(), BraveSearchProvider)


def test_factory_raises_with_actionable_message_without_any_key(monkeypatch):
    for name in (*TAVILY_KEY_ENV_VARS, *BRAVE_KEY_ENV_VARS, "LUMEN_SEARCH_PROVIDER"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(SearchUnavailableError) as excinfo:
        create_search_provider()

    assert "TAVILY_API_KEY" in str(excinfo.value)
    assert "BRAVE_API_KEY" in str(excinfo.value)


def test_factory_honours_explicit_provider(monkeypatch):
    monkeypatch.setenv("LUMEN_SEARCH_PROVIDER", "brave")
    monkeypatch.setenv("BRAVE_API_KEY", "b")
    assert isinstance(create_search_provider(), BraveSearchProvider)


def test_factory_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("LUMEN_SEARCH_PROVIDER", "duckduckgo")
    with pytest.raises(SearchUnavailableError, match="desconhecido"):
        create_search_provider()


def test_accepts_lumen_prefixed_env_var(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("LUMEN_TAVILY_API_KEY", "tvly-prefixed")
    provider = create_search_provider(transport=RecordingTransport(payload=tavily_payload()))
    assert provider.has_key is True


# --------------------------------------------------------------------- misc
def test_redact_secret_removes_occurrences():
    assert redact_secret("key=abc123", "abc123") == "key=***REDACTED***"
    assert redact_secret("nothing", None) == "nothing"
    assert redact_secret("nothing", "") == "nothing"


def test_timeout_out_of_range_is_rejected():
    with pytest.raises(ValueError, match="timeout"):
        TavilySearchProvider(api_key="k", timeout=0)
    with pytest.raises(ValueError, match="timeout"):
        TavilySearchProvider(api_key="k", timeout=9999)


def test_timeout_is_forwarded_to_transport():
    transport = RecordingTransport(payload=tavily_payload())
    provider = TavilySearchProvider(api_key="k", transport=transport, timeout=12.5)

    provider.search("q")

    assert transport.last["timeout"] == pytest.approx(12.5)


def test_search_result_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="http"):
        SearchResult(title="t", url="ftp://x", content="", score=0.5).validate()


def test_search_result_rejects_out_of_range_score():
    with pytest.raises(ValueError, match="score"):
        SearchResult(title="t", url="https://x.test", content="", score=1.5).validate()


def test_response_context_block_numbers_sources():
    response = WebSearchResponse(
        query="q",
        provider="tavily",
        results=(
            SearchResult(title="First", url="https://a.test", content="alpha", score=0.9),
            SearchResult(title="Second", url="https://b.test", content="beta", score=0.8),
        ),
    )
    block = response.as_context_block()
    assert "[1] First" in block
    assert "[2] Second" in block
    assert "https://a.test" in block


def test_response_context_block_truncates():
    response = WebSearchResponse(
        query="q",
        provider="tavily",
        results=tuple(
            SearchResult(title=f"T{i}", url=f"https://a{i}.test", content="x" * 500, score=0.5)
            for i in range(50)
        ),
    )
    block = response.as_context_block(max_chars=1_000)
    assert len(block) < 1_200
    assert "truncado" in block


def test_search_factory_loads_key_from_env_file_without_logging_it(tmp_path, monkeypatch):
    import app.research.client as module
    env_file = tmp_path / ".env"
    env_file.write_text("LUMEN_SEARCH_PROVIDER=tavily\nTAVILY_API_KEY=tvly-FAKE-FILE\n", encoding="utf-8")
    monkeypatch.setattr(module, "ENV_FILE", env_file)
    for name in ("LUMEN_SEARCH_PROVIDER", *TAVILY_KEY_ENV_VARS, *BRAVE_KEY_ENV_VARS):
        monkeypatch.delenv(name, raising=False)
    transport = RecordingTransport(payload=tavily_payload(SAMPLE_RESULT))
    provider = module.create_search_provider(transport=transport)
    provider.search("teste")
    assert transport.last["headers"]["Authorization"] == "Bearer tvly-FAKE-FILE"
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-FAKE-ENV")
    module.create_search_provider(transport=transport).search("teste")
    assert transport.last["headers"]["Authorization"] == "Bearer tvly-FAKE-ENV"


def test_malformed_env_file_never_logs_api_key(tmp_path, caplog, monkeypatch):
    import app.research.client as module
    env_file = tmp_path / ".env"
    env_file.write_text("TAVILY_API_KEY=tvly-FAKE-SECRET\nNO_EQUALS tvly-FAKE-SECRET\n=tvly-FAKE-SECRET\n", encoding="utf-8")
    monkeypatch.setattr(module, "ENV_FILE", env_file)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    module._resolve_key(TAVILY_KEY_ENV_VARS)
    assert "tvly-FAKE-SECRET" not in caplog.text
