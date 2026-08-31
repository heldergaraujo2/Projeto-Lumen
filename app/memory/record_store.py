"""RecordStore — motor de persistência e busca de um domínio de memória.

Cada domínio (:class:`~app.memory.records.MemoryKind`) tem seu próprio
arquivo JSON (``data/memory/<dominio>.json``), com:

- escrita **atômica** (``.tmp`` + ``os.replace``) e thread-safe (``RLock``);
- IDs sequenciais legíveis por domínio;
- **deduplicação básica** por ``content_hash`` entre registros ``ACTIVE``
  (gravar duas vezes a mesma informação devolve o registro existente);
- **atualização** (``update``) com histórico via ``supersedes``
  (``supersede`` marca o antigo como ``OBSOLETE`` e cria o novo);
- **obsolescência** (``mark_obsolete``) sem apagar histórico;
- **busca por relevância** (título > tags > conteúdo; bônus quando todos
  os termos casam; registros obsoletos pesam 0,2 e só entram se pedidos);
- **redação de segredos** antes de qualquer persistência
  (:mod:`app.memory.sanitization`).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.memory.records import (
    ID_PREFIXES,
    MemoryKind,
    MemoryRecord,
    RecordError,
    RecordStatus,
    compute_hash,
    normalize_text,
)
from app.memory.sanitization import redact_secrets

logger = logging.getLogger("lumen.memory.records")


class RecordStoreError(RuntimeError):
    """Falha de leitura/escrita do domínio de memória."""


class RecordNotFoundError(RecordStoreError):
    """Registro solicitado não existe."""


class DuplicateRecordError(RecordStoreError):
    """Atualização criaria duplicata de um registro ACTIVE existente."""


@dataclass(frozen=True)
class SearchHit:
    """Registro pontuado por relevância."""

    record: MemoryRecord
    score: float


def _terms(query: str) -> list[str]:
    return [t for t in normalize_text(query).split() if t]


class RecordStore:
    """Persistência de registros de UM domínio de memória."""

    def __init__(self, file_path: Path | str, kind: MemoryKind) -> None:
        self._path = Path(file_path)
        self._kind = kind
        self._lock = threading.RLock()
        self._records: list[MemoryRecord] = []
        self._load()

    # ------------------------------------------------------------ persistência
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RecordStoreError(
                f"Arquivo de memória corrompido: {self._path} ({exc}). "
                "Corrija ou remova o arquivo para reiniciar este domínio."
            ) from exc
        if not isinstance(raw, list):
            raise RecordStoreError(
                f"Arquivo de memória inválido ({self._path}): esperado uma lista JSON."
            )
        records = []
        for item in raw:
            try:
                records.append(MemoryRecord.from_dict(item))
            except RecordError as exc:
                raise RecordStoreError(
                    f"Arquivo de memória {self._path} contém registro inválido: {exc}"
                ) from exc
        for record in records:
            if record.kind is not self._kind:
                raise RecordStoreError(
                    f"Arquivo de memória {self._path} contém registro do domínio "
                    f"{record.kind.value}; esperado {self._kind.value}."
                )
        self._records = records

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [record.to_dict() for record in self._records]
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp_path, self._path)  # escrita atômica
        except OSError as exc:
            raise RecordStoreError(f"Falha ao salvar memória em {self._path}: {exc}") from exc

    # -------------------------------------------------------------------- API
    def add(
        self,
        title: str,
        content: str,
        *,
        origin: str = "user",
        tags: tuple[str, ...] | list[str] = (),
        project_id: str | None = None,
        related_ids: tuple[str, ...] | list[str] = (),
        supersedes: str | None = None,
    ) -> MemoryRecord:
        """Adiciona um registro (deduplicado entre ACTIVE) e persiste.

        Segredos são redigidos antes da persistência. Gravar exatamente a
        mesma informação (título+conteúdo normalizados) quando já existe
        um registro ``ACTIVE`` é idempotente: devolve o existente.
        """
        title, _ = redact_secrets((title or "").strip())
        content, had_secret = redact_secrets((content or "").strip())
        if not title:
            raise ValueError("O título do registro não pode ser vazio.")
        if not content:
            raise ValueError("O conteúdo do registro não pode ser vazio.")
        if had_secret:
            logger.info(
                "Registro do domínio %s recebeu segredo no conteúdo; segredo redigido.",
                self._kind.value,
            )

        content_hash = compute_hash(title, content)
        with self._lock:
            for existing in self._records:
                if existing.status is RecordStatus.ACTIVE and existing.content_hash == content_hash:
                    logger.info(
                        "Deduplicação no domínio %s: %s já contém esta informação.",
                        self._kind.value, existing.id,
                    )
                    return existing

            now = datetime.now().astimezone().isoformat(timespec="seconds")
            record = MemoryRecord(
                id=self._next_id(),
                kind=self._kind,
                title=title,
                content=content,
                origin=origin,
                status=RecordStatus.ACTIVE,
                created_at=now,
                updated_at=now,
                tags=tuple(tags),
                project_id=project_id,
                related_ids=tuple(related_ids),
                supersedes=supersedes,
            )
            self._records.append(record)
            self._save()
            return record

    def _next_id(self) -> str:
        prefix = ID_PREFIXES[self._kind]
        numbers = []
        for record in self._records:
            _, _, suffix = record.id.rpartition("-")
            if record.id.startswith(prefix + "-") and suffix.isdigit():
                numbers.append(int(suffix))
        return f"{prefix}-{max(numbers, default=0) + 1:04d}"

    def get(self, record_id: str) -> MemoryRecord:
        """Retorna o registro pelo ID.

        Raises:
            RecordNotFoundError: se não existir.
        """
        with self._lock:
            for record in self._records:
                if record.id == record_id:
                    return record
        raise RecordNotFoundError(
            f"Registro {record_id!r} não encontrado no domínio {self._kind.value}."
        )

    def update(
        self,
        record_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        tags: tuple[str, ...] | list[str] | None = None,
        project_id: str | None = None,
        related_ids: tuple[str, ...] | list[str] | None = None,
        append_related: tuple[str, ...] | list[str] | None = None,
    ) -> MemoryRecord:
        """Atualiza campos de um registro (cria nova versão imutável).

        O registro é imutável: a atualização substitui o objeto na lista
        por uma versão nova com ``updated_at`` bumped e ``content_hash``
        recalculado. Se o novo conteúdo colidir com OUTRO registro
        ``ACTIVE``, levanta :class:`DuplicateRecordError` (sem gravar).
        """
        with self._lock:
            record = self.get(record_id)
            new_title = record.title if title is None else redact_secrets(title.strip())[0]
            new_content = record.content if content is None else redact_secrets(content.strip())[0]
            if not new_title.strip() or not new_content.strip():
                raise ValueError("Título e conteúdo não podem ficar vazios.")

            new_hash = compute_hash(new_title, new_content)
            for other in self._records:
                if (
                    other.id != record.id
                    and other.status is RecordStatus.ACTIVE
                    and other.content_hash == new_hash
                ):
                    raise DuplicateRecordError(
                        f"Atualização de {record_id} colidiria com o registro "
                        f"ativo {other.id} (mesmo título/conteúdo)."
                    )

            new_tags = record.tags if tags is None else tuple(tags)
            new_project = record.project_id if project_id is None else project_id
            if related_ids is None:
                new_related = record.related_ids
                if append_related:
                    new_related = tuple(dict.fromkeys((*new_related, *append_related)))
            else:
                new_related = tuple(related_ids)

            updated = MemoryRecord(
                id=record.id,
                kind=record.kind,
                title=new_title,
                content=new_content,
                origin=record.origin,
                status=record.status,
                created_at=record.created_at,
                updated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                tags=new_tags,
                project_id=new_project,
                related_ids=new_related,
                supersedes=record.supersedes,
                content_hash=new_hash,
            )
            self._records[self._records.index(record)] = updated
            self._save()
            return updated

    def mark_obsolete(self, record_id: str, *, reason: str = "") -> MemoryRecord:
        """Marca o registro como ``OBSOLETE`` (histórico preservado)."""
        with self._lock:
            record = self.get(record_id)
            note = f" [obsoleto: {reason.strip()}]" if reason.strip() else ""
            updated = MemoryRecord(
                id=record.id,
                kind=record.kind,
                title=record.title,
                content=record.content,
                origin=record.origin,
                status=RecordStatus.OBSOLETE,
                created_at=record.created_at,
                updated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                tags=record.tags,
                project_id=record.project_id,
                related_ids=record.related_ids,
                supersedes=record.supersedes,
                content_hash=record.content_hash,
            )
            self._records[self._records.index(record)] = updated
            if note:  # motivo fica no log; o registro permanença limpo
                logger.info("Registro %s marcado obsoleto:%s", record_id, note)
            self._save()
            return updated

    def supersede(
        self,
        record_id: str,
        title: str,
        content: str,
        **kwargs,
    ) -> MemoryRecord:
        """Cria um registro novo que substitui ``record_id``.

        O antigo vira ``OBSOLETE``; o novo nasce com ``supersedes`` e
        ``related_ids`` apontando para o antigo (trilha de atualização).
        """
        with self._lock:
            old = self.get(record_id)
            related = list(kwargs.pop("related_ids", ()) or ())
            if old.id not in related:
                related.append(old.id)
            new_record = self.add(
                title, content, related_ids=related, supersedes=old.id, **kwargs
            )
            if old.status is RecordStatus.ACTIVE:
                self.mark_obsolete(old.id, reason=f"substituído por {new_record.id}")
            return new_record

    # ------------------------------------------------------------------- busca
    def search(
        self,
        query: str,
        limit: int = 10,
        include_obsolete: bool = False,
    ) -> list[SearchHit]:
        """Busca por termos com relevância (título > tags > conteúdo).

        Pontuação por termo: título 3 · tag 2 · conteúdo 1; +1 de bônus
        quando todos os termos casam. Registros ``OBSOLETE`` têm peso
        0,2 e só entram com ``include_obsolete=True``.
        """
        terms = _terms(query)
        if not terms or limit <= 0:
            return []

        hits: list[SearchHit] = []
        with self._lock:
            records = list(self._records)
        for record in records:
            if record.status is RecordStatus.OBSOLETE and not include_obsolete:
                continue
            n_title = normalize_text(record.title)
            n_tags = [normalize_text(t) for t in record.tags]
            n_content = normalize_text(record.content)
            matched = 0
            score = 0.0
            for term in terms:
                if term in n_title:
                    score += 3
                    matched += 1
                elif any(term in tag for tag in n_tags):
                    score += 2
                    matched += 1
                elif term in n_content:
                    score += 1
                    matched += 1
            if matched == 0:
                continue
            if matched == len(terms):
                score += 1
            if record.status is RecordStatus.OBSOLETE:
                score *= 0.2
            hits.append(SearchHit(record=record, score=score))

        hits.sort(key=lambda hit: (-hit.score, hit.record.id))
        return hits[:limit]

    def filter(
        self,
        *,
        status: RecordStatus | None = None,
        project_id: str | None = None,
        tag: str | None = None,
    ) -> list[MemoryRecord]:
        """Lista registros por status/projeto/tag (ordem de criação)."""
        with self._lock:
            records = list(self._records)
        if status is not None:
            records = [r for r in records if r.status is status]
        if project_id is not None:
            records = [r for r in records if r.project_id == project_id]
        if tag is not None:
            wanted = normalize_text(tag)
            records = [r for r in records if wanted in (normalize_text(t) for t in r.tags)]
        return records

    def all(self) -> list[MemoryRecord]:
        with self._lock:
            return list(self._records)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._records)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def kind(self) -> MemoryKind:
        return self._kind
