"""Testes offline das ferramentas e provedores Web."""
from __future__ import annotations

import json
import socket
from email.message import Message

import pytest

from app.security.permissions import PermissionDeniedError, PermissionLevel, PermissionManager
from app.tools.base import ToolRegistry
from app.web.provider import (
    SafeHttpClient,
    StandardWebFetchProvider,
    WebFetchResponse,
    WebProviderError,
    WebSearchResponse,
    WebSource,
)
from app.web.security import WebSecurityError, WebSecurityPolicy
from app.web.tools import WebFetchTool, WebResearchTool, WebSearchTool


class FakeSearch:
    def search(self, request):
        return WebSearchResponse(
            request.query,
            (WebSource("Fonte", "https://example.com", "trecho"),),
        )


class FakeFetch:
    def fetch(self, url):
        return WebFetchResponse(
            url, url, "Example", "text/html", "conteúdo público", False
        )


class FakeResponse:
    def __init__(self, url, body=b"", content_type="text/plain", charset="utf-8"):
        self._url = url
        self._body = body
        self.headers = Message()
        self.headers["Content-Type"] = (
            f"{content_type}; charset={charset}" if charset else content_type
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def geturl(self):
        return self._url

    def read(self, size=-1):
        return self._body if size < 0 else self._body[:size]


class FakeOpener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if not self.outcomes:
            raise AssertionError("nenhuma resposta configurada para o opener")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _http_redirect(url, location, code=302):
    headers = Message()
    headers["Location"] = location
    return __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
        url, code, f"redirect {code}", headers, None
    )


def _client(*outcomes, max_bytes=1_000_000, max_redirects=5, timeout_s=20.0):
    policy = WebSecurityPolicy(max_redirects=max_redirects)
    client = SafeHttpClient(
        policy=policy,
        max_bytes=max_bytes,
        timeout_s=timeout_s,
    )
    opener = FakeOpener(*outcomes)
    client._opener = opener
    return client, opener


def test_web_tools_require_explicit_permission():
    permissions = PermissionManager()
    registry = ToolRegistry(permissions)
    registry.register(WebSearchTool(provider=FakeSearch()))
    with pytest.raises(PermissionDeniedError):
        registry.execute("web_search", query="teste")


def test_web_search_returns_structured_sources():
    permissions = PermissionManager([PermissionLevel.CHAT, PermissionLevel.WEB_ACCESS])
    registry = ToolRegistry(permissions)
    registry.register(WebSearchTool(provider=FakeSearch()))
    result = json.loads(registry.execute("web_search", query="teste", max_results=1))
    assert result["ok"] is True
    assert result["data"]["sources"][0]["url"] == "https://example.com"


class PartialFailureSearch:
    def search(self, request):
        return WebSearchResponse(
            request.query,
            (
                WebSource("Fonte OK 1", "https://example.com/one", "primeira"),
                WebSource("Fonte com falha", "https://example.com/fail", "segunda"),
                WebSource("Fonte OK 2", "https://example.com/two", "terceira"),
            ),
        )


class PartialFailureFetch:
    def fetch(self, url):
        if url.endswith("/fail"):
            raise WebProviderError("falha simulada ao buscar fonte")
        return WebFetchResponse(
            url, url, "Example", "text/html", f"conteúdo de {url}", False
        )


def test_web_research_searches_and_fetches_sources():
    permissions = PermissionManager([PermissionLevel.CHAT, PermissionLevel.WEB_ACCESS])
    registry = ToolRegistry(permissions)
    registry.register(
        WebResearchTool(search_provider=FakeSearch(), fetch_provider=FakeFetch())
    )
    result = json.loads(
        registry.execute("web_research", query="teste", max_results=5, max_sources=1)
    )
    assert result["ok"] is True
    source = result["data"]["sources"][0]
    assert source["url"] == "https://example.com"
    assert source["text"] == "conteúdo público"
    assert result["data"]["source_count"] == 1


def test_web_research_continues_when_one_source_fetch_fails():
    permissions = PermissionManager([PermissionLevel.CHAT, PermissionLevel.WEB_ACCESS])
    registry = ToolRegistry(permissions)
    registry.register(
        WebResearchTool(
            search_provider=PartialFailureSearch(),
            fetch_provider=PartialFailureFetch(),
        )
    )

    result = json.loads(
        registry.execute("web_research", query="teste", max_results=5, max_sources=3)
    )

    assert result["ok"] is True
    sources = result["data"]["sources"]
    assert result["data"]["source_count"] == 3
    assert sources[0]["text"] == "conteúdo de https://example.com/one"
    assert sources[1]["url"] == "https://example.com/fail"
    assert sources[1]["fetch_error"] == "falha simulada ao buscar fonte"
    assert "text" not in sources[1]
    assert sources[2]["text"] == "conteúdo de https://example.com/two"


class CompleteFailureSearch:
    def search(self, request):
        raise WebProviderError("falha total simulada na pesquisa")


def test_web_research_returns_controlled_error_when_search_provider_fails():
    permissions = PermissionManager([PermissionLevel.CHAT, PermissionLevel.WEB_ACCESS])
    registry = ToolRegistry(permissions)
    registry.register(
        WebResearchTool(
            search_provider=CompleteFailureSearch(),
            fetch_provider=FakeFetch(),
        )
    )

    result = json.loads(
        registry.execute("web_research", query="teste", max_results=5, max_sources=3)
    )

    assert result["ok"] is False
    assert result["error"] == "falha total simulada na pesquisa"


def test_web_research_requires_explicit_permission():
    permissions = PermissionManager()
    registry = ToolRegistry(permissions)
    registry.register(
        WebResearchTool(search_provider=FakeSearch(), fetch_provider=FakeFetch())
    )
    with pytest.raises(PermissionDeniedError):
        registry.execute("web_research", query="teste")


def test_web_research_invalid_limits_are_controlled():
    tool = WebResearchTool(search_provider=FakeSearch(), fetch_provider=FakeFetch())
    for kwargs in (
        {"query": "", "max_results": 5, "max_sources": 1},
        {"query": "teste", "max_results": 0, "max_sources": 1},
        {"query": "teste", "max_results": 5, "max_sources": 0},
        {"query": "teste", "max_results": 21, "max_sources": 6},
    ):
        result = tool.run(**kwargs)
        assert not result.ok
        assert result.error


def test_web_fetch_returns_text_without_execution():
    permissions = PermissionManager([PermissionLevel.CHAT, PermissionLevel.WEB_ACCESS])
    registry = ToolRegistry(permissions)
    registry.register(WebFetchTool(provider=FakeFetch()))
    result = json.loads(registry.execute("web_fetch", url="https://example.com"))
    assert result["ok"] is True
    assert result["data"]["text"] == "conteúdo público"


@pytest.mark.parametrize(
    ("query", "max_results"),
    ((123, 5), ("teste", True), ("teste", 0), ("teste", 21)),
)
def test_web_search_invalid_input_returns_controlled_error(query, max_results):
    tool = WebSearchTool(provider=FakeSearch())
    result = tool.run(query=query, max_results=max_results)
    assert not result.ok
    assert result.error


def test_web_search_invalid_input_does_not_leak_query_to_audit():
    class Audit:
        def __init__(self):
            self.events = []

        def record(self, **kwargs):
            self.events.append(kwargs)

    audit = Audit()
    tool = WebSearchTool(provider=FakeSearch(), audit=audit)
    result = tool.run(query=123, max_results=5)
    assert not result.ok
    assert audit.events[0]["query_length"] is None
    assert "123" not in str(audit.events[0])


@pytest.mark.parametrize("url", (123, None, ""))
def test_web_fetch_invalid_input_returns_controlled_error(url):
    tool = WebFetchTool(provider=FakeFetch())
    result = tool.run(url=url)
    assert not result.ok
    assert result.error


def test_web_fetch_invalid_input_does_not_leak_url_to_audit():
    class Audit:
        def __init__(self):
            self.events = []

        def record(self, **kwargs):
            self.events.append(kwargs)

    audit = Audit()
    tool = WebFetchTool(provider=FakeFetch(), audit=audit)
    result = tool.run(url=123)
    assert not result.ok
    assert audit.events[0]["requested_path"] == "host:<invalid>"
    assert "123" not in str(audit.events[0])


@pytest.mark.parametrize(
    "url",
    (
        "file:///etc/passwd",
        "ftp://example.com/resource",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "ws://example.com/socket",
    ),
)
def test_web_security_rejects_prohibited_protocols(url):
    policy = WebSecurityPolicy()
    with pytest.raises(WebSecurityError, match="Esquema não permitido"):
        policy.validate_url(url, resolve_dns=False)


def test_planner_url_validation_blocks_private_destinations():
    from app.planner.catalog import build_catalog, validate_task_tool

    catalog = build_catalog(include_terminal=False)
    assert "web_search" in catalog and "web_fetch" in catalog
    assert validate_task_tool("web_fetch", {"url": "http://127.0.0.1/"}, catalog)
    assert validate_task_tool("web_fetch", {"url": "file:///secret"}, catalog)


def test_security_special_ranges_stay_blocked_when_private_networks_allowed():
    policy = WebSecurityPolicy(allow_private_networks=True)
    with pytest.raises(WebSecurityError):
        policy.validate_url("http://127.0.0.1/", resolve_dns=False)
    with pytest.raises(WebSecurityError):
        policy.validate_url("http://169.254.169.254/", resolve_dns=False)


def test_fetch_tool_rejects_unsafe_url_before_provider():
    class ExplodingProvider:
        def fetch(self, url):
            raise AssertionError("provider não deveria ser chamado")

    tool = WebFetchTool(provider=ExplodingProvider())
    result = tool.run("http://127.0.0.1/")
    assert not result.ok
    assert "não permitido" in (result.error or "") or "local" in (result.error or "")


def test_safe_http_client_follows_valid_redirect_and_validates_each_hop():
    first = _http_redirect("https://1.1.1.1/start", "https://1.0.0.1/final")
    final = FakeResponse("https://1.0.0.1/final", b"ok")
    client, opener = _client(first, final)

    result = client.get("https://1.1.1.1/start")

    assert result.final_url == "https://1.0.0.1/final"
    assert result.body == b"ok"
    assert [request.full_url for request, _ in opener.requests] == [
        "https://1.1.1.1/start",
        "https://1.0.0.1/final",
    ]


def test_safe_http_client_blocks_redirect_to_private_destination():
    first = _http_redirect("https://1.1.1.1/start", "http://127.0.0.1/private")
    client, opener = _client(first)

    with pytest.raises(WebSecurityError):
        client.get("https://1.1.1.1/start")

    assert len(opener.requests) == 1


def test_safe_http_client_blocks_redirect_when_maximum_is_exceeded():
    redirects = [
        _http_redirect(
            f"https://1.1.1.{index}/start",
            f"https://1.0.0.{index}/next",
        )
        for index in range(1, 4)
    ]
    client, opener = _client(*redirects, max_redirects=2)

    with pytest.raises(WebProviderError, match="máximo de redirects"):
        client.get("https://1.1.1.1/start")

    assert len(opener.requests) == 3


def test_safe_http_client_rejects_redirect_without_location():
    headers = Message()
    error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
        "https://1.1.1.1/start", 302, "redirect", headers, None
    )
    client, _ = _client(error)

    with pytest.raises(WebProviderError, match="sem Location"):
        client.get("https://1.1.1.1/start")


def test_safe_http_client_truncates_response_at_max_bytes():
    client, _ = _client(
        FakeResponse("https://1.1.1.1/data", b"abcdefghij"),
        max_bytes=5,
    )

    result = client.get("https://1.1.1.1/data")

    assert result.body == b"abcde"
    assert result.truncated is True


def test_safe_http_client_marks_response_not_truncated_at_exact_limit():
    client, _ = _client(
        FakeResponse("https://1.1.1.1/data", b"abcde"),
        max_bytes=5,
    )

    result = client.get("https://1.1.1.1/data")

    assert result.body == b"abcde"
    assert result.truncated is False


@pytest.mark.parametrize("content_type", ("application/pdf", "application/octet-stream"))
def test_standard_web_fetch_rejects_non_text_content_types(content_type):
    client, _ = _client(
        FakeResponse("https://1.1.1.1/file", b"binary", content_type=content_type)
    )
    provider = StandardWebFetchProvider(
        policy=WebSecurityPolicy(),
        client=client,
    )

    with pytest.raises(WebProviderError, match="Tipo de conteúdo"):
        provider.fetch("https://1.1.1.1/file")


def test_standard_web_fetch_accepts_html_and_strips_non_visible_content():
    body = b"""
    <html><head><title>Pagina</title><style>.x{display:none}</style></head>
    <body>Visivel<script>alert('x')</script><noscript>fallback</noscript>
    <svg><text>vector</text></svg></body></html>
    """
    client, _ = _client(
        FakeResponse("https://1.1.1.1/page", body, content_type="text/html")
    )
    provider = StandardWebFetchProvider(
        policy=WebSecurityPolicy(),
        client=client,
    )

    result = provider.fetch("https://1.1.1.1/page")

    assert "Visivel" in result.text
    assert "alert" not in result.text
    assert "fallback" not in result.text
    assert "vector" not in result.text


def test_safe_http_client_converts_timeout_to_controlled_provider_error():
    client, _ = _client(socket.timeout("tempo esgotado"))

    with pytest.raises(WebProviderError, match="Falha de conexão Web"):
        client.get("https://1.1.1.1/slow")


@pytest.mark.parametrize("status", (400, 404, 500, 503))
def test_safe_http_client_converts_http_errors_to_controlled_provider_error(status):
    headers = Message()
    error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
        "https://1.1.1.1/error", status, "http error", headers, None
    )
    client, _ = _client(error)

    with pytest.raises(WebProviderError, match=f"HTTP {status}"):
        client.get("https://1.1.1.1/error")


class FakeSearchClient:
    def __init__(self, body):
        self.body = body

    def get_text(self, url):
        return self.body


def test_duckduckgo_lite_parser_extracts_real_urls_and_snippets():
    from app.web.provider import DuckDuckGoSearchProvider

    html = """
    <a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage%26x%3D1" class="result-link">Example title</a>
    <div class="result-snippet">Example snippet</div>
    """
    provider = DuckDuckGoSearchProvider(
        policy=WebSecurityPolicy(),
        client=FakeSearchClient(html),
    )
    result = provider.search(__import__("app.web.provider", fromlist=["WebSearchRequest"]).WebSearchRequest("teste", 5))

    assert len(result.sources) == 1
    assert result.sources[0].title == "Example title"
    assert result.sources[0].url == "https://example.com/page&x=1"


def test_duckduckgo_lite_skips_private_redirect_targets():
    from app.web.provider import DuckDuckGoSearchProvider

    html = """
    <a href="//duckduckgo.com/l/?uddg=http%3A%2F%2F127.0.0.1%2Fprivate" class="result-link">Private</a>
    """
    provider = DuckDuckGoSearchProvider(
        policy=WebSecurityPolicy(),
        client=FakeSearchClient(html),
    )
    result = provider.search(__import__("app.web.provider", fromlist=["WebSearchRequest"]).WebSearchRequest("teste", 5))

    assert result.sources == ()


class EmptySearch:
    def search(self, request):
        return WebSearchResponse(request.query, ())


def test_web_research_handles_empty_search_results():
    permissions = PermissionManager([PermissionLevel.CHAT, PermissionLevel.WEB_ACCESS])
    registry = ToolRegistry(permissions)
    registry.register(
        WebResearchTool(search_provider=EmptySearch(), fetch_provider=FakeFetch())
    )

    result = json.loads(
        registry.execute("web_research", query="teste", max_results=5, max_sources=3)
    )

    assert result["ok"] is True
    assert result["data"]["sources"] == []
    assert result["data"]["source_count"] == 0
