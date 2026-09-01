"""11K — SnapshotStore: snapshots mínimos "before" de operações destrutivas.

Módulo **puro** (sem wiring em ToolsController/handler — a integração vem
depois): cria o snapshot (cópia de bytes) do arquivo que existe **antes**
de uma operação destrutiva de filesystem, com manifest JSON contendo
**apenas metadados** — o conteúdo do arquivo nunca sai de
``root_dir`` (nada de conteúdo em manifest/auditoria/relatório).

Princípios normativos (spec 11K §4):

- **não concede permissões** — é leitura/cópia de bytes de um caminho já
  validado pela camada de sandbox/permissões (o store não revalida nem
  resolve);
- **best-effort** — falha operacional **nunca** levanta: é registrada em
  ``skipped_reason`` (``"not_found"``, ``"too_large"``,
  ``"error:<tipo>"``) e a operação prossegue;
- **escrita atômica** do manifest (``.tmp`` + ``os.replace``) — padrão do
  projeto (stores workspaces/terminal/record);
- **sem execução escondida** — apenas stdlib (json/os/re); sem
  subprocess/terminal/shell.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("lumen.tools.snapshot_store")

#: Caracteres permitidos em nomes de diretório (mesma regra do export de
#: relatório 11I — ``:``/``/`` etc. viram ``_``; ``#`` é preservado).
#: (hífen no final da classe — nunca como range)
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._#-]")

#: Versão do schema do manifest (evolução de formato).
MANIFEST_VERSION = 1

MANIFEST_FILENAME = "manifest.json"
BACKUP_FILENAME = "before.bin"

#: Limite default de tamanho de snapshot (1 MiB — coerente com o limite
#: de leitura do ``read_file`` e a recusa do ``edit_file``).
DEFAULT_MAX_SNAPSHOT_BYTES = 1_000_000


def _safe_name(value: str) -> str:
    """Substitui caracteres fora de ``[A-Za-z0-9._#-]`` por ``_``."""
    return _UNSAFE_NAME_CHARS.sub("_", str(value))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SnapshotManifest:
    """Manifest imutável de UM snapshot — **somente metadados** (sem
    conteúdo de arquivo).

    ``resolved_path`` é mantido como string **para debug apenas** — no
    restore a autoridade é a resolução do sandbox, nunca este campo.
    """

    version: int
    created_at: str                    # ISO8601 UTC
    plan_id: str
    task_id: str
    tool: str
    requested_path: str                # relativo ao workspace (referência)
    resolved_path: str                 # debug apenas (não é autoridade)
    existed_before: bool
    bytes_before: int | None = None
    backup_relpath: str | None = None  # relativa a root_dir (snapshots_dir)
    skipped_reason: str | None = None  # "not_found" | "too_large" | "error:<tipo>" | None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotManifest":
        """Parser validado (schema ``version``); inválido ⇒ ``ValueError``."""
        if not isinstance(data, dict):
            raise ValueError("manifest não é um objeto JSON")
        if data.get("version") != MANIFEST_VERSION:
            raise ValueError(
                f"versão de manifest não suportada: {data.get('version')!r}"
            )
        return cls(
            version=int(data["version"]),
            created_at=str(data.get("created_at") or ""),
            plan_id=str(data.get("plan_id") or ""),
            task_id=str(data.get("task_id") or ""),
            tool=str(data.get("tool") or ""),
            requested_path=str(data.get("requested_path") or ""),
            resolved_path=str(data.get("resolved_path") or ""),
            existed_before=bool(data.get("existed_before")),
            bytes_before=(
                int(data["bytes_before"])
                if data.get("bytes_before") is not None else None
            ),
            backup_relpath=(
                str(data["backup_relpath"])
                if data.get("backup_relpath") is not None else None
            ),
            skipped_reason=(
                str(data["skipped_reason"])
                if data.get("skipped_reason") is not None else None
            ),
        )


class SnapshotStore:
    """Persistência de snapshots "before" em ``root_dir/<plan>/<task>/``.

    Layout::

        root_dir/
        └── <safe_plan_id>/
            └── <task_id>/
                ├── manifest.json   # metadados (escrita atômica)
                └── before.bin      # cópia de bytes (quando há backup)

    **Best-effort**: :meth:`create_snapshot` nunca levanta em falha
    operacional — registra ``skipped_reason`` (a operação da tool segue).
    """

    def __init__(self, root_dir: Path, *, max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES) -> None:
        if max_snapshot_bytes < 1:
            raise ValueError("max_snapshot_bytes deve ser >= 1.")
        self._root = Path(root_dir)
        self._max_bytes = int(max_snapshot_bytes)

    @property
    def root_dir(self) -> Path:
        return self._root

    @property
    def max_snapshot_bytes(self) -> int:
        return self._max_bytes

    # ------------------------------------------------------------- público
    def create_snapshot(
        self,
        plan_id: str,
        task_id: str,
        tool: str,
        requested_path: str,
        resolved_path: Path,
    ) -> SnapshotManifest:
        """Cria o snapshot "before" de ``resolved_path`` (best-effort).

        Regras:

        - arquivo **existe** e ``size <= max_snapshot_bytes`` ⇒ cópia de
          bytes em ``before.bin`` + ``backup_relpath``;
        - arquivo **não existe** ⇒ ``existed_before=False`` +
          ``skipped_reason="not_found"`` (sem cópia — o rollback é
          deletar o que foi criado);
        - ``size > max_snapshot_bytes`` ⇒ ``skipped_reason="too_large"``
          (sem cópia);
        - **qualquer exceção** ⇒ ``skipped_reason="error:<tipo>"`` —
          **nunca levanta** (o módulo nunca bloqueia a operação).
        """
        task_dir = self._root / _safe_name(plan_id) / _safe_name(task_id)
        try:
            task_dir.mkdir(parents=True, exist_ok=True)
            return self._capture(
                plan_id, task_id, tool, str(requested_path),
                Path(resolved_path), task_dir,
            )
        except Exception as exc:  # best-effort: nunca bloqueia a operação
            logger.warning(
                "Snapshot falhou (não fatal) para %s/%s: %s",
                plan_id, task_id, exc,
            )
            fallback = SnapshotManifest(
                version=MANIFEST_VERSION,
                created_at=_utc_now_iso(),
                plan_id=str(plan_id),
                task_id=str(task_id),
                tool=str(tool),
                requested_path=str(requested_path),
                resolved_path=str(resolved_path),
                existed_before=False,
                bytes_before=None,
                backup_relpath=None,
                skipped_reason=f"error:{type(exc).__name__}",
            )
            try:  # persistência do manifest de erro (também best-effort)
                self._write_manifest(task_dir, fallback)
            except Exception:
                logger.warning(
                    "Snapshot: manifest de erro não persistido (não fatal) "
                    "para %s/%s.", plan_id, task_id,
                )
            return fallback

    def load_manifest(self, plan_id: str, task_id: str) -> SnapshotManifest | None:
        """Lê o manifest do (plan, task); ``None`` se ausente/corrompido.

        Leitura tolerante (padrão ``read_audit_tail``): qualquer problema
        de I/O/JSON/schema devolve ``None`` — nunca levanta.
        """
        manifest_path = (
            self._root / _safe_name(plan_id) / _safe_name(task_id) / MANIFEST_FILENAME
        )
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return SnapshotManifest.from_dict(data)
        except (OSError, ValueError, TypeError, KeyError):
            return None

    # ------------------------------------------------------------- interno
    def _capture(
        self,
        plan_id: str,
        task_id: str,
        tool: str,
        requested_path: str,
        resolved_path: Path,
        task_dir: Path,
    ) -> SnapshotManifest:
        """Captura "antes" + grava manifest (o best-effort é o try externo)."""
        backup_relpath: str | None = None
        skipped_reason: str | None = None
        existed_before = False
        bytes_before: int | None = None

        if resolved_path.exists():
            existed_before = True
            bytes_before = resolved_path.stat().st_size
            if bytes_before > self._max_bytes:
                skipped_reason = "too_large"
            else:
                # Cópia sem shutil (guard AST anti-futuro de app/tools):
                # tamanho já limitado por max_snapshot_bytes.
                (task_dir / BACKUP_FILENAME).write_bytes(
                    resolved_path.read_bytes()
                )
                backup_relpath = (
                    f"{_safe_name(plan_id)}/{_safe_name(task_id)}/{BACKUP_FILENAME}"
                )
        else:
            skipped_reason = "not_found"

        manifest = SnapshotManifest(
            version=MANIFEST_VERSION,
            created_at=_utc_now_iso(),
            plan_id=plan_id,
            task_id=task_id,
            tool=tool,
            requested_path=requested_path,
            resolved_path=str(resolved_path),
            existed_before=existed_before,
            bytes_before=bytes_before,
            backup_relpath=backup_relpath,
            skipped_reason=skipped_reason,
        )
        self._write_manifest(task_dir, manifest)
        return manifest

    def _write_manifest(self, task_dir: Path, manifest: SnapshotManifest) -> None:
        """Grava ``manifest.json`` **atomicamente** (``.tmp`` + ``os.replace``)."""
        target = task_dir / MANIFEST_FILENAME
        tmp = task_dir / (MANIFEST_FILENAME + ".tmp")
        tmp.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, target)
