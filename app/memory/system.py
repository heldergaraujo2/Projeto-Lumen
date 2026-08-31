"""MemorySystem — fachada da memória inteligente da Lumen (0.3).

Une os seis domínios com uma API única:

1. **conversa**  — :class:`~app.memory.store.MemoryStore` (0.1, intacta);
2. **projeto**   — :class:`~app.memory.records.MemoryKind.PROJECT`;
3. **tarefas**   — ``MemoryKind.TASK`` (registro histórico; o
   :class:`~app.tasks.manager.TaskManager` segue sendo o registro
   operacional);
4. **conhecimento** — ``MemoryKind.KNOWLEDGE``;
5. **decisões**  — ``MemoryKind.DECISION``;
6. **erros/soluções** — ``MemoryKind.ISSUE``/``SOLUTION`` (relacionados
   por ``related_ids``).

Fornece também:

- ``recall(query)`` — busca unificada por relevância em todos os
  domínios estruturados;
- ``build_context(query)`` — seleção de contexto **limitada**
  (``LUMEN_MAX_MEMORY_RECORDS``) pronta para o futuro fluxo do Agent
  (0.4+): registros estruturados primeiro, mensagens de conversa
  completando a cota;
- proteção de segredos em TODOS os domínios estruturados (redação antes
  de persistir — :mod:`app.memory.sanitization`).

A memória é LOCAL; nada é enviado a provedor algum por esta camada.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.memory.record_store import (
    RecordNotFoundError,
    RecordStore,
    SearchHit,
)
from app.memory.records import (
    KIND_FILENAMES,
    MemoryKind,
    MemoryRecord,
)
from app.memory.store import MemoryStore

logger = logging.getLogger("lumen.memory.system")

#: Tamanho máximo do excerto de conteúdo no contexto construído.
_EXCERPT_CHARS = 400


class MemorySystemError(RuntimeError):
    """Falha da fachada de memória."""


@dataclass(frozen=True)
class ContextEntry:
    """Item de contexto selecionado para envio futuro ao provider."""

    kind: str                 # domínio estruturado ou "CONVERSATION"
    title: str
    content: str
    score: float
    record_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "id": self.record_id,
            "title": self.title,
            "content": self.content,
            "score": self.score,
        }


class MemorySystem:
    """Fachada dos domínios de memória da Lumen.

    Args:
        data_dir: diretório de dados (memórias ficam em ``data/memory/``).
        max_context_records: limite de registros selecionados por
            ``build_context`` (alinha-se a ``LUMEN_MAX_MEMORY_RECORDS``).
    """

    def __init__(self, data_dir: Path | str, max_context_records: int = 12) -> None:
        if max_context_records < 1:
            raise ValueError("max_context_records deve ser >= 1.")
        memory_dir = Path(data_dir) / "memory"
        self._memory_dir = memory_dir
        self._max_context_records = max_context_records
        self.conversation = MemoryStore(memory_dir / "conversation.json")
        self._stores: dict[MemoryKind, RecordStore] = {
            kind: RecordStore(memory_dir / filename, kind)
            for kind, filename in KIND_FILENAMES.items()
        }

    # ------------------------------------------------------------- propriedades
    @property
    def max_context_records(self) -> int:
        return self._max_context_records

    def store_for(self, kind: MemoryKind) -> RecordStore:
        """Acesso ao store de um domínio (API avançada)."""
        return self._stores[kind]

    def stats(self) -> dict[str, int]:
        """Contagem de registros por domínio (+ mensagens de conversa)."""
        result = {"CONVERSATION": self.conversation.count}
        for kind, store in self._stores.items():
            result[kind.value] = store.count
        return result

    # ------------------------------------------------------------------ escrita
    def remember(
        self,
        kind: MemoryKind,
        title: str,
        content: str,
        *,
        origin: str = "user",
        tags: tuple[str, ...] | list[str] = (),
        project_id: str | None = None,
        related_ids: tuple[str, ...] | list[str] = (),
    ) -> MemoryRecord:
        """Grava um registro no domínio indicado (dedup + redação de segredos)."""
        return self._stores[kind].add(
            title, content, origin=origin, tags=tags,
            project_id=project_id, related_ids=related_ids,
        )

    def update(self, kind: MemoryKind, record_id: str, **kwargs) -> MemoryRecord:
        """Atualiza um registro do domínio (ver ``RecordStore.update``)."""
        return self._stores[kind].update(record_id, **kwargs)

    def mark_obsolete(self, kind: MemoryKind, record_id: str, *, reason: str = "") -> MemoryRecord:
        """Marca um registro como obsoleto (histórico preservado)."""
        return self._stores[kind].mark_obsolete(record_id, reason=reason)

    def supersede(self, kind: MemoryKind, record_id: str, title: str, content: str, **kwargs) -> MemoryRecord:
        """Substitui um registro por uma nova versão (trilha supersedes)."""
        return self._stores[kind].supersede(record_id, title, content, **kwargs)

    def get(self, kind: MemoryKind, record_id: str) -> MemoryRecord:
        return self._stores[kind].get(record_id)

    def relate(self, id_a: str, id_b: str) -> list[MemoryRecord]:
        """Cria relação bidirecional entre dois registros (A↔B), por ID.

        Percorre os domínios e atualiza cada ponta onde o ID existir;
        devolve os registros atualizados. IDs desconhecidos em ambas as
        pontas levanta :class:`RecordNotFoundError`.
        """
        updated: list[MemoryRecord] = []
        for store in self._stores.values():
            for this, other in ((id_a, id_b), (id_b, id_a)):
                try:
                    record = store.get(this)
                except RecordNotFoundError:
                    continue
                updated.append(store.update(record.id, append_related=(other,)))
        if not updated:
            raise RecordNotFoundError(
                f"Nenhum dos IDs {id_a!r}/{id_b!r} existe na memória estruturada."
            )
        return updated

    # ------------------------------------------------------------------- busca
    def recall(
        self,
        query: str,
        *,
        kinds: tuple[MemoryKind, ...] | list[MemoryKind] | None = None,
        limit: int | None = None,
        include_obsolete: bool = False,
    ) -> list[SearchHit]:
        """Busca unificada por relevância nos domínios estruturados."""
        limit = limit or self._max_context_records
        selected = self._stores.items() if kinds is None else ((k, self._stores[k]) for k in kinds)
        hits: list[SearchHit] = []
        for _kind, store in selected:
            hits.extend(store.search(query, limit=limit, include_obsolete=include_obsolete))
        hits.sort(key=lambda hit: (-hit.score, hit.record.id))
        return hits[:limit]

    def build_context(self, query: str, max_records: int | None = None) -> list[ContextEntry]:
        """Seleciona o contexto relevante e **limitado** para um pedido.

        Ordem de preenchimento da cota: registros estruturados por
        relevância; mensagens recentes da conversa que casam com os
        termos completam a cota restante. Este é o gancho que o Agent
        usará a partir da 0.4 — nada é enviado a provedores aqui.
        """
        budget = max_records or self._max_context_records
        entries: list[ContextEntry] = []
        seen_ids: set[str] = set()

        for hit in self.recall(query, limit=budget):
            record = hit.record
            if record.id in seen_ids:
                continue
            seen_ids.add(record.id)
            entries.append(ContextEntry(
                kind=record.kind.value,
                title=record.title,
                content=_excerpt(record.content),
                score=hit.score,
                record_id=record.id,
            ))
            if len(entries) >= budget:
                return entries

        remaining = budget - len(entries)
        if remaining > 0:
            for message in self.conversation.search(query, limit=remaining):
                entries.append(ContextEntry(
                    kind="CONVERSATION",
                    title=f"{message.role} em {message.timestamp}",
                    content=_excerpt(message.content),
                    score=1.0,
                    record_id=None,
                ))
        return entries


def _excerpt(content: str, limit: int = _EXCERPT_CHARS) -> str:
    content = content.strip()
    return content if len(content) <= limit else content[: limit - 1].rstrip() + "…"
