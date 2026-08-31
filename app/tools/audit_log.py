"""Persistência da trilha de auditoria em JSONL (0.5.x).

Mecanismo simples e seguro: um arquivo ``audit.jsonl`` em ``data/``, uma
linha JSON por tentativa de operação (append atomicamente ordenado por
lock; UTF-8). **Conteúdo de arquivos nunca é registrado** — o sink
recebe exatamente os dicts do :class:`~app.tools.filesystem.AuditRecord`
(metadados apenas). Dados de auditoria ficam separados do conteúdo dos
arquivos do usuário por construção.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumen.tools.audit")


class JsonlAuditSink:
    """Sink de auditoria: appending JSONL (thread-safe).

    Falhas de I/O **não** derrubam operações — o
    :class:`~app.tools.filesystem.FilesystemAudit` já encapsula o sink
    em try/except (registro permanece em memória).
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def __call__(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def read_audit_tail(path: Path, limit: int = 100) -> list[dict[str, Any]]:
    """Lê os últimos ``limit`` registros do JSONL (mais antigos primeiro).

    Linhas corrompidas são puladas (aviso no log) — a visualização nunca
    quebra por uma linha ruim. Arquivo ausente ⇒ lista vazia.
    """
    if limit <= 0:
        raise ValueError("limit deve ser positivo.")
    path = Path(path)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("Falha ao ler a trilha de auditoria %s: %s", path, exc)
        return []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            logger.warning(
                "Linha %d da auditoria ignorada (JSON inválido): %s", number, path
            )
    return records[-limit:]
