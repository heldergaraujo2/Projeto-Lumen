"""Provedores HTTP/Web da Lumen.

Implementação stdlib, sem dependência de um fornecedor específico.
A busca usa DuckDuckGo HTML por padrão; o contrato permite substituir o
provedor futuramente. Toda URL é validada antes de cada conexão e em cada
redirect. Respostas são limitadas por bytes e tempo.
"""
from __future__ import annotations
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
import gzip
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlsplit

from app.web.security import WebSecurityError, WebSecurityPolicy

@dataclass(frozen=True)
class WebSource:
    title: str
    url: str
    snippet: str = ""

@dataclass(frozen=True)
class WebSearchRequest:
    query: str
    max_results: int = 5

@dataclass(frozen=True)
class WebSearchResponse:
    query: str
    sources: tuple[WebSource, ...]

@dataclass(frozen=True)
class WebFetchResponse:
    url: str
    final_url: str
    title: str
    content_type: str
    text: str
    truncated: bool

class WebProviderError(RuntimeError):
    """Falha controlada do provedor Web."""

class WebSearchProvider:
    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        raise NotImplementedError

class WebFetchProvider:
    def fetch(self, url: str) -> WebFetchResponse:
        raise NotImplementedError

class _SearchParser(HTMLParser):
    def __init__(self, limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.limit=limit; self.items=[]; self._link=None; self._text=[]
        self._snippet=None; self._snippet_text=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "a" and "result-link" in classes:
            self._link=attrs.get("href"); self._text=[]
        if "result-snippet" in classes:
            self._snippet=True; self._snippet_text=[]
    def handle_data(self,data):
        if self._link is not None: self._text.append(data)
        if self._snippet: self._snippet_text.append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self._link is not None:
            title=" ".join("".join(self._text).split())
            href=self._link
            if title and href and len(self.items)<self.limit:
                self.items.append([title,href,""])
            self._link=None; self._text=[]
        if self._snippet and tag in {"div", "td", "span"}:
            snippet=" ".join("".join(self._snippet_text).split())
            if snippet and self.items:
                self.items[-1][2]=snippet
            self._snippet=False; self._snippet_text=[]

class _TextParser(HTMLParser):
    SKIP={"script","style","noscript","svg"}
    def __init__(self): super().__init__(convert_charrefs=True); self.parts=[]; self._skip=0
    def handle_starttag(self,tag,attrs):
        if tag in self.SKIP: self._skip+=1
    def handle_endtag(self,tag):
        if tag in self.SKIP and self._skip: self._skip-=1
    def handle_data(self,data):
        if not self._skip:
            value=" ".join(data.split())
            if value: self.parts.append(value)

class DuckDuckGoSearchProvider(WebSearchProvider):
    def __init__(self, *, policy: WebSecurityPolicy, client: "SafeHttpClient|None"=None):
        self.policy=policy; self.client=client or SafeHttpClient(policy=policy)
    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        q=request.query.strip()
        if not q: raise WebProviderError("Consulta vazia.")
        if not 1<=request.max_results<=20: raise WebProviderError("max_results deve estar entre 1 e 20.")
        endpoint="https://lite.duckduckgo.com/lite/?q="+quote_plus(q)
        try:
            body=self.client.get_text(endpoint)
            parser=_SearchParser(request.max_results); parser.feed(body)
        except (WebSecurityError, WebProviderError) as exc: raise
        except Exception as exc: raise WebProviderError(f"Falha na busca Web: {exc}") from exc
        sources=[]
        for title, href, snippet in parser.items:
            normalized_href = _normalize_search_url(href)
            absolute=urljoin(endpoint, normalized_href)
            absolute = _normalize_search_url(absolute)
            parsed=urlsplit(absolute)
            if parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com"} and parsed.path == "/l/":
                target = parse_qs(parsed.query).get("uddg", [None])[0]
                if target:
                    absolute = unquote(target)
            try:
                safe=self.policy.validate_url(absolute)
            except WebSecurityError:
                continue
            sources.append(WebSource(title=title,url=safe,snippet=snippet))
        return WebSearchResponse(query=q,sources=tuple(sources))

class StandardWebFetchProvider(WebFetchProvider):
    def __init__(self, *, policy: WebSecurityPolicy, client: "SafeHttpClient|None"=None):
        self.policy=policy; self.client=client or SafeHttpClient(policy=policy)
    def fetch(self,url:str)->WebFetchResponse:
        result=self.client.get(url)
        content_type=result.content_type.lower()
        if "text/html" not in content_type and not content_type.startswith("text/"):
            raise WebProviderError(f"Tipo de conteúdo não suportado: {content_type or '<desconhecido>'}.")
        parser=_TextParser(); parser.feed(result.body.decode(result.charset,errors="replace"))
        text=" ".join(parser.parts)
        return WebFetchResponse(url=result.requested_url,final_url=result.final_url,title="",content_type=content_type,text=text,truncated=result.truncated)

@dataclass(frozen=True)
class _HttpResult:
    requested_url:str; final_url:str; content_type:str; charset:str; body:bytes; truncated:bool

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None

class SafeHttpClient:
    def __init__(self, *, policy:WebSecurityPolicy, timeout_s:float=20.0, max_bytes:int=1_000_000, user_agent:str="Lumen-Web/1.0"):
        if timeout_s<=0 or max_bytes<=0: raise ValueError("limites HTTP devem ser positivos")
        self.policy=policy; self.timeout_s=timeout_s; self.max_bytes=max_bytes; self.user_agent=user_agent
        self._opener=urllib.request.build_opener(_NoRedirect)
    def get_text(self,url:str)->str:
        return self.get(url).body.decode("utf-8",errors="replace").strip()
    def get(self,url:str)->_HttpResult:
        current=self.policy.validate_url(url)
        for _ in range(self.policy.max_redirects+1):
            request=urllib.request.Request(
                current,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
                    "Accept-Encoding": "identity",
                },
                method="GET",
            )
            try:
                with self._opener.open(request,timeout=self.timeout_s) as response:
                    final=response.geturl()
                    safe_final=self.policy.validate_url(final)
                    content_type=response.headers.get_content_type()
                    charset=response.headers.get_content_charset() or "utf-8"
                    raw_body = response.read(self.max_bytes + 1)
                    body, decompressed_truncated = _decode_response_body(
                        raw_body,
                        response.headers.get("Content-Encoding", ""),
                        self.max_bytes,
                    )
                    truncated = len(raw_body) > self.max_bytes or decompressed_truncated
                    return _HttpResult(
                        url, safe_final, content_type, charset,
                        body, truncated,
                    )
            except urllib.error.HTTPError as exc:
                if exc.code in (301,302,303,307,308):
                    location=exc.headers.get("Location")
                    if not location: raise WebProviderError("Redirect sem Location.") from exc
                    current=self.policy.validate_url(urljoin(current,location))
                    continue
                raise WebProviderError(f"HTTP {exc.code}.") from exc
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
                raise WebProviderError(f"Falha de conexão Web: {exc}") from exc
        raise WebProviderError("Número máximo de redirects excedido.")


def _normalize_search_url(value: str) -> str:
    """Extrai uma URL HTTP/HTTPS quando o mecanismo a devolve como Markdown."""
    text = value.strip()
    match = re.fullmatch(r"\[[^\]]+\]\((https?://[^)]+)\)", text)
    return match.group(1) if match else text


def _decode_response_body(
    body: bytes, content_encoding: str, max_bytes: int
) -> tuple[bytes, bool]:
    """Decodifica respostas comprimidas com limite de saída."""
    encoding = (content_encoding or "").strip().lower()
    if not encoding or encoding == "identity":
        return body[:max_bytes], len(body) > max_bytes

    try:
        if encoding in {"gzip", "x-gzip"}:
            with gzip.GzipFile(fileobj=BytesIO(body)) as decoder:
                decoded = decoder.read(max_bytes + 1)
            return decoded[:max_bytes], len(decoded) > max_bytes
        if encoding == "deflate":
            import zlib
            decoder = zlib.decompressobj()
            decoded = decoder.decompress(body, max_bytes + 1)
            return decoded[:max_bytes], len(decoded) > max_bytes or bool(decoder.unconsumed_tail)
    except Exception as exc:
        raise WebProviderError(
            f"Resposta Web comprimida inválida ({encoding})."
        ) from exc

    return body[:max_bytes], len(body) > max_bytes