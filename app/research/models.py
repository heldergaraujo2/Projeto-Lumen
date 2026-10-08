"""Modelos da camada de pesquisa (Fase 1).

Dataclasses imutáveis com ``validate()`` explícito, no mesmo estilo de
``app/computer_control/models.py`` e ``app/planner/models.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Teto absoluto de bytes de um snippet devolvido ao chamador.
MAX_SNIPPET_CHARS = 4_000
#: Teto absoluto de bytes do conteúdo bruto (quando solicitado).
MAX_RAW_CONTENT_CHARS = 20_000


@dataclass(frozen=True)
class SearchResult:
    """Um resultado individual de busca.

    ``url`` é validada como ``http(s)://`` — evita que um provedor
    comprometido devolva ``file://`` ou ``javascript:`` e o agente trate
    como fonte confiável.
    """

    title: str
    url: str
    content: str = ""
    score: float = 0.0
    raw_content: str | None = None

    def validate(self) -> None:
        if not isinstance(self.url, str) or not self.url.strip():
            raise ValueError("resultado de busca exige 'url' não vazia")
        if not self.url.startswith(("http://", "https://")):
            raise ValueError(
                f"resultado de busca exige URL http(s) — recebido: {self.url[:40]!r}"
            )
        if self.score < 0 or self.score > 1.0:
            raise ValueError("score deve estar entre 0.0 e 1.0")

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "score": self.score,
        }


@dataclass(frozen=True)
class WebSearchResponse:
    """Resposta completa de uma busca, já normalizada e limitada."""

    query: str
    provider: str
    results: tuple[SearchResult, ...] = ()
    answer: str | None = None
    truncated: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not self.query.strip():
            raise ValueError("resposta de busca exige 'query' não vazia")
        if not self.provider.strip():
            raise ValueError("resposta de busca exige 'provider' não vazio")
        for result in self.results:
            result.validate()

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "provider": self.provider,
            "result_count": len(self.results),
            "truncated": self.truncated,
            "answer": self.answer,
            "results": [r.to_dict() for r in self.results],
            "notes": list(self.notes),
        }

    def as_context_block(self, *, max_chars: int = 12_000) -> str:
        """Formata a resposta como bloco de texto para o planejador.

        Deliberadamente **não** é markdown decorado: é evidência numerada
        que o LLM pode citar (``[1]``, ``[2]``…), o que mantém a rastreia-
        bilidade das fontes no plano gerado na Fase 2.
        """
        lines = [f"Resultados de pesquisa para: {self.query} (via {self.provider})", ""]
        if self.answer:
            lines += [f"Resposta sintetizada pelo provedor: {self.answer}", ""]
        for index, result in enumerate(self.results, start=1):
            lines.append(f"[{index}] {result.title}")
            lines.append(f"    {result.url}")
            if result.content:
                lines.append(f"    {result.content.strip()}")
            lines.append("")
        if self.truncated:
            lines.append("(conteúdo truncado por limite de tamanho)")
        block = "\n".join(lines)
        if len(block) > max_chars:
            return block[:max_chars] + "\n… (bloco de pesquisa truncado)"
        return block


__all__ = [
    "MAX_RAW_CONTENT_CHARS",
    "MAX_SNIPPET_CHARS",
    "SearchResult",
    "WebSearchResponse",
]
