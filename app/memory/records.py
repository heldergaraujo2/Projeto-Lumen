"""Modelo de registros de memória da Lumen (0.3).

Um :class:`MemoryRecord` é a unidade de informação dos domínios de
memória estruturada (projeto, tarefa, conhecimento, decisão, erro,
solução). Características exigidas pela 0.3:

- ``id`` único e legível por domínio (``PRJ-0001``, ``KN-0001``, …);
- ``created_at``/``updated_at`` (ISO-8601 com fuso);
- ``origin`` (origem da informação: usuário, agente, manual…);
- ``related_ids`` (relacionamento entre registros, inclusive entre
  domínios — ex.: erro ``ERR-0001`` ↔ solução ``SOL-0001``);
- ``supersedes`` (trilha de atualização: registro novo que substitui um
  antigo, que por sua vez vira ``OBSOLETE``);
- ``content_hash`` (deduplicação básica: título+conteúdo normalizados);
- ``status`` (``ACTIVE`` | ``OBSOLETE``).
"""
from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MemoryKind(str, Enum):
    """Domínios de memória estruturada (a conversa fica no MemoryStore 0.1)."""

    PROJECT = "PROJECT"        # informações sobre projetos do usuário
    TASK = "TASK"              # tarefas realizadas/pendentes (registro histórico)
    KNOWLEDGE = "KNOWLEDGE"    # conhecimento aprendido no desenvolvimento
    DECISION = "DECISION"      # decisões tomadas (e por quê)
    ISSUE = "ISSUE"            # erros/problemas encontrados
    SOLUTION = "SOLUTION"      # correções/soluções aplicadas


class RecordStatus(str, Enum):
    ACTIVE = "ACTIVE"
    OBSOLETE = "OBSOLETE"


#: Prefixo de ID por domínio (legível e único entre domínios).
ID_PREFIXES: dict[MemoryKind, str] = {
    MemoryKind.PROJECT: "PRJ",
    MemoryKind.TASK: "TASK",
    MemoryKind.KNOWLEDGE: "KN",
    MemoryKind.DECISION: "DEC",
    MemoryKind.ISSUE: "ERR",
    MemoryKind.SOLUTION: "SOL",
}

#: Nome do arquivo JSON por domínio (em ``data/memory/``).
KIND_FILENAMES: dict[MemoryKind, str] = {
    MemoryKind.PROJECT: "projects.json",
    MemoryKind.TASK: "task_records.json",
    MemoryKind.KNOWLEDGE: "knowledge.json",
    MemoryKind.DECISION: "decisions.json",
    MemoryKind.ISSUE: "issues.json",
    MemoryKind.SOLUTION: "solutions.json",
}


class RecordError(RuntimeError):
    """Registro de memória inválido."""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_text(text: str) -> str:
    """Normalização para hash/dedup e busca: minúsculas, sem acentos,
    espaços colapsados."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", text.lower())
    without_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(without_accents.split())


def compute_hash(title: str, content: str) -> str:
    """Hash estável (sha256) de título+conteúdo normalizados."""
    payload = normalize_text(title) + "\x00" + normalize_text(content)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryRecord:
    """Unidade de informação da memória estruturada."""

    id: str
    kind: MemoryKind
    title: str
    content: str
    origin: str = "user"
    status: RecordStatus = RecordStatus.ACTIVE
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    tags: tuple[str, ...] = ()
    project_id: str | None = None
    related_ids: tuple[str, ...] = ()
    supersedes: str | None = None
    content_hash: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise RecordError("Registro de memória sem id.")
        if not self.title.strip():
            raise RecordError(f"Registro {self.id}: título vazio.")
        if not self.content.strip():
            raise RecordError(f"Registro {self.id}: conteúdo vazio.")
        if not self.content_hash:
            object.__setattr__(
                self, "content_hash", compute_hash(self.title, self.content)
            )

    # ------------------------------------------------------------ serialização
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "title": self.title,
            "content": self.content,
            "origin": self.origin,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": list(self.tags),
            "project_id": self.project_id,
            "related_ids": list(self.related_ids),
            "supersedes": self.supersedes,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecord":
        try:
            record_id = data["id"]
            kind = MemoryKind(data["kind"])
            title = data["title"]
            content = data["content"]
            status = RecordStatus(data.get("status", RecordStatus.ACTIVE.value))
        except (KeyError, TypeError, ValueError) as exc:
            raise RecordError(f"Registro de memória inválido: {data!r}") from exc
        return cls(
            id=record_id,
            kind=kind,
            title=title,
            content=content,
            origin=data.get("origin") or "user",
            status=status,
            created_at=data.get("created_at") or _now_iso(),
            updated_at=data.get("updated_at") or _now_iso(),
            tags=tuple(data.get("tags") or ()),
            project_id=data.get("project_id"),
            related_ids=tuple(data.get("related_ids") or ()),
            supersedes=data.get("supersedes"),
            content_hash=data.get("content_hash") or "",
        )
