"""Optional Mem0 semantic index backed by local Ollama and Qdrant.

The existing JSON RecordStore remains the source of truth. Mem0 only returns
record IDs for semantic ranking; callers re-read each result from RecordStore
and reject missing/obsolete records. Nothing is sent to Mem0 Platform.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumen.memory.mem0")


def _enabled_from_env() -> bool:
    return os.getenv("LUMEN_MEM0_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


class Mem0SemanticIndex:
    """Lazy, fail-open semantic index; disabled unless explicitly opted in."""

    def __init__(self, data_dir: Path | str, *, client_factory=None) -> None:
        self._data_dir = Path(data_dir)
        self._client_factory = client_factory
        self._client = None
        self._lock = threading.RLock()
        self._enabled = _enabled_from_env()
        self._failed = False

    @property
    def enabled(self) -> bool:
        return self._enabled and not self._failed

    def _make_client(self):
        if self._client_factory is not None:
            return self._client_factory(self._config())
        from mem0 import Memory

        return Memory.from_config(self._config())

    def _config(self) -> dict[str, Any]:
        ollama_url = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        llm_model = (
            os.getenv("LUMEN_MEM0_LLM_MODEL")
            or os.getenv("OLLAMA_MODEL")
            or "qwen3:8b"
        )
        embed_model = os.getenv("LUMEN_MEM0_EMBED_MODEL", "nomic-embed-text:latest")
        embedding_dims = int(os.getenv("LUMEN_MEM0_EMBEDDING_DIMS", "768"))
        qdrant_dir = self._data_dir / "qdrant"
        history_db = self._data_dir / "history.db"
        return {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "lumen_semantic_memories",
                    "path": str(qdrant_dir),
                    "embedding_model_dims": embedding_dims,
                    "on_disk": True,
                },
            },
            "llm": {
                "provider": "ollama",
                "config": {
                    "model": llm_model,
                    "temperature": 0,
                    "ollama_base_url": ollama_url,
                },
            },
            "embedder": {
                "provider": "ollama",
                "config": {
                    "model": embed_model,
                    "embedding_dims": embedding_dims,
                    "ollama_base_url": ollama_url,
                },
            },
            "history_db_path": str(history_db),
            "version": "v1.1",
        }

    def _get_client(self):
        with self._lock:
            if not self.enabled:
                return None
            if self._client is None:
                try:
                    self._data_dir.mkdir(parents=True, exist_ok=True)
                    self._client = self._make_client()
                except Exception as exc:
                    self._failed = True
                    logger.warning(
                        "Mem0 local indisponível (%s); memória JSON continua ativa.",
                        type(exc).__name__,
                    )
                    return None
            return self._client

    def add_record(self, record) -> bool:
        """Index a structured record without making Mem0 the source of truth."""
        client = self._get_client()
        if client is None:
            return False
        text = f"{record.title}\n{record.content}".strip()
        if not text:
            return False
        metadata = {
            "lumen_record_id": record.id,
            "lumen_kind": record.kind.value,
        }
        if getattr(record, "project_id", None):
            metadata["project_id"] = record.project_id
        try:
            client.add(
                text,
                user_id=os.getenv("LUMEN_MEM0_USER_ID", "lumen-local"),
                metadata=metadata,
            )
            return True
        except Exception as exc:
            self._fail(exc, "indexação")
            return False

    def search(self, query: str, limit: int = 10) -> list[tuple[str, str, float]]:
        """Return (record_id, kind, score); never return generated memory text."""
        client = self._get_client()
        if client is None or not isinstance(query, str) or not query.strip() or limit < 1:
            return []
        try:
            response = client.search(
                query,
                user_id=os.getenv("LUMEN_MEM0_USER_ID", "lumen-local"),
                limit=limit,
            )
            if isinstance(response, dict):
                results = response.get("results", [])
            elif isinstance(response, list):
                results = response
            else:
                results = []
            found: list[tuple[str, str, float]] = []
            seen: set[tuple[str, str]] = set()
            for item in results:
                if not isinstance(item, dict):
                    continue
                metadata = item.get("metadata")
                if not isinstance(metadata, dict):
                    continue
                record_id = metadata.get("lumen_record_id")
                kind = metadata.get("lumen_kind")
                if not isinstance(record_id, str) or not isinstance(kind, str):
                    continue
                key = (record_id, kind)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    score = float(item.get("score", 0.0))
                except (TypeError, ValueError):
                    score = 0.0
                found.append((record_id, kind, score))
                if len(found) >= limit:
                    break
            return found
        except Exception as exc:
            self._fail(exc, "busca semântica")
            return []

    def _fail(self, exc: Exception, operation: str) -> None:
        with self._lock:
            self._failed = True
            self._client = None
        logger.warning(
            "Mem0 falhou durante %s (%s); memória JSON continua ativa.",
            operation,
            type(exc).__name__,
        )
