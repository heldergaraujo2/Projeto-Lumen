"""Memória de conversa local (persistência em JSON).

Fase 0: histórico linear de mensagens (``role``/``content``/``timestamp``)
salvo em ``data/memory/conversation.json`` com escrita atômica
(arquivo temporário + ``os.replace``) e thread-safe.
"""
from __future__ import annotations

import json
import os
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

#: Papéis válidos de mensagem.
VALID_ROLES = ("user", "assistant", "system")


class MemoryStoreError(RuntimeError):
    """Falha de leitura/escrita da memória."""


def _now_iso() -> str:
    """Timestamp ISO-8601 com fuso horário local."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _normalize_for_search(text: str) -> str:
    """Minúsculas sem acentos e espaços colapsados (para busca da 0.3)."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    without_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(without_accents.split())


@dataclass(frozen=True)
class Message:
    """Mensagem única da conversa."""

    role: str
    content: str
    timestamp: str

    def to_dict(self) -> dict[str, str]:
        """Representação serializável (formato do JSON em disco)."""
        return {"role": self.role, "content": self.content, "timestamp": self.timestamp}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "Message":
        """Reconstrói uma mensagem a partir do dicionário persistido."""
        try:
            role = data["role"]
            content = data["content"]
            timestamp = data.get("timestamp") or _now_iso()
        except (KeyError, TypeError) as exc:
            raise MemoryStoreError(f"Mensagem inválida na memória: {data!r}") from exc
        if role not in VALID_ROLES:
            raise MemoryStoreError(
                f"Role inválida na memória: {role!r}. Use: {', '.join(VALID_ROLES)}."
            )
        return cls(role=role, content=content, timestamp=timestamp)


class MemoryStore:
    """Histórico de conversa persistido em JSON.

    A carga ocorre no construtor; cada inserção salva o arquivo
    imediatamente (simples e seguro para a fase 0).
    """

    def __init__(self, file_path: Path | str) -> None:
        self._path = Path(file_path)
        self._lock = threading.RLock()
        self._messages: list[Message] = []
        self._load()

    # ------------------------------------------------------------ persistência
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MemoryStoreError(
                f"Arquivo de memória corrompido: {self._path} ({exc}). "
                "Corrija ou remova o arquivo para reiniciar a memória."
            ) from exc
        if not isinstance(raw, list):
            raise MemoryStoreError(
                f"Arquivo de memória inválido ({self._path}): esperado uma lista JSON."
            )
        self._messages = [Message.from_dict(item) for item in raw]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [message.to_dict() for message in self._messages]
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp_path, self._path)  # escrita atômica
        except OSError as exc:
            raise MemoryStoreError(f"Falha ao salvar memória em {self._path}: {exc}") from exc

    # ------------------------------------------------------------------ API
    def add_message(self, role: str, content: str, timestamp: str | None = None) -> Message:
        """Adiciona e persiste uma mensagem; devolve o registro criado."""
        if role not in VALID_ROLES:
            raise ValueError(f"Role inválida: {role!r}. Use: {', '.join(VALID_ROLES)}.")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("O conteúdo da mensagem não pode ser vazio.")

        message = Message(role=role, content=content, timestamp=timestamp or _now_iso())
        with self._lock:
            self._messages.append(message)
            self._save()
        return message

    def recent(self, limit: int = 20) -> list[Message]:
        """Últimas ``limit`` mensagens, em ordem cronológica."""
        if limit <= 0:
            return []
        with self._lock:
            return list(self._messages[-limit:])

    def all_messages(self) -> list[Message]:
        """Cópia de todo o histórico."""
        with self._lock:
            return list(self._messages)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._messages)

    def clear(self) -> None:
        """Apaga todo o histórico (inclusive do disco)."""
        with self._lock:
            self._messages.clear()
            self._save()

    def search(self, query: str, limit: int = 10) -> list["Message"]:
        """Busca simples por termos na conversa (0.3).

        Casamento insensível a acentos/caixa; qualquer termo presente no
        conteúdo conta. Ordem cronológica.
        """
        terms = [t for t in _normalize_for_search(query).split() if t]
        if not terms or limit <= 0:
            return []
        with self._lock:
            messages = list(self._messages)
        found = []
        for message in messages:
            content = _normalize_for_search(message.content)
            if any(term in content for term in terms):
                found.append(message)
        return found[-limit:]
