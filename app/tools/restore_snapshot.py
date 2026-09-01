"""11K — ``restore_snapshot``: rollback manual mínimo a partir de snapshot.

Tool de restauração de um arquivo a partir do snapshot "before" 11K
(criado por :mod:`app.tools.snapshot_store` / wiring do handler).
**Nesta etapa a tool NÃO está registrada em registry/catalog** — a
integração (registro + checkpoint + UI) vem em comando próprio.

Princípios normativos (spec 11K §4/§7):

- **restaurar é WRITE** (e DELETE quando "desfazer" um arquivo criado) —
  a tool é **destrutiva** (pertence a ``FILESYSTEM_DESTRUCTIVE_TOOLS``
  quando registrada) ⇒ **checkpoint obrigatório**;
- **sem execução escondida**: somente leitura/escrita local de bytes
  (stdlib) — **sem subprocess/terminal/shell**;
- **sem confiança em ``manifest.resolved_path``** (é debug apenas): o
  alvo é **sempre re-resolvido** via ``sandbox.resolve(
  manifest.requested_path)`` — confinamento no workspace;
- **política do workspace vale**: ``check_operation("write", …)`` para
  restore-escrita e ``check_operation("delete", …)`` para
  restore-exclusão — violação ⇒ ``ok=False`` (nunca mutação);
- **sem vazamento de conteúdo na auditoria**: apenas metadados
  (snapshot, ação, tamanhos, caminhos) — nunca bytes do arquivo.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult
from app.tools.filesystem import (
    OPERATION_DELETE,
    OPERATION_WRITE,
    FilesystemAudit,
    FilesystemError,
    WorkspaceSandbox,
)
from app.tools.snapshot_store import SnapshotStore

logger = logging.getLogger("lumen.tools.restore_snapshot")

#: Ações registradas no resultado/auditoria (metadados).
ACTION_RESTORE_WRITE = "restore_write"      # sobrescrever com o backup
ACTION_UNDO_CREATE = "undo_create"          # deletar o que foi criado
ACTION_ALREADY_GONE = "already_gone"        # idempotente: alvo já ausente


class RestoreSnapshotTool(StructuredTool):
    """Restaura um arquivo a partir de um snapshot 11K "before".

    Parâmetros (task):

    - ``snapshot_plan_id`` (string, obrigatória): plano dono do snapshot.
    - ``snapshot_task_id`` (string, obrigatória): task dona do snapshot.

    Matriz de comportamento (spec 11K §7):

    =====================  =============================================
    Manifest               Ação
    =====================  =============================================
    ``existed_before=True`` (write/edit/delete)
                          sobrescreve o alvo com o ``before.bin``
                          (exige ``backup_relpath`` + backup presente)
    ``existed_before=False`` (create)
                          **deleta** o alvo (undo do create); se o alvo
                          já não existir ⇒ ``ok=True`` (idempotente)
    manifest inexistente   ``ok=False`` (``"snapshot_not_found"``)
    =====================  =============================================

    Segurança: alvo resolvido via sandbox (``manifest.resolved_path``
    **não** é usado como autoridade) + ``check_operation`` antes de
    qualquer mutação; backup validado para permanecer dentro de
    ``snapshots_dir`` (anti-traversal).
    """

    name = "restore_snapshot"
    description = (
        "Restaura um arquivo a partir de um snapshot 11K 'before' "
        "(rollback manual: devolve o conteúdo anterior à operação ou "
        "deleta o arquivo que foi criado)."
    )
    required_permission = PermissionLevel.WRITE
    operation = OPERATION_WRITE  # primária (undo_create usa DELETE)

    def __init__(
        self,
        sandbox: WorkspaceSandbox,
        snapshots_dir: Path,
        audit: FilesystemAudit | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._store = SnapshotStore(Path(snapshots_dir))
        self._audit = audit

    # ------------------------------------------------------------- contrato
    def run(self, **kwargs: Any) -> ToolResult:
        plan_id = kwargs.get("snapshot_plan_id")
        task_id = kwargs.get("snapshot_task_id")
        if not isinstance(plan_id, str) or not plan_id.strip():
            return self._finish(
                None, None, None, None, ok=False,
                error="snapshot_not_found: snapshot_plan_id (string) "
                      "é obrigatório.",
                action="invalid_input",
            )
        if not isinstance(task_id, str) or not task_id.strip():
            return self._finish(
                plan_id, None, None, None, ok=False,
                error="snapshot_not_found: snapshot_task_id (string) "
                      "é obrigatório.",
                action="invalid_input",
            )

        manifest = self._store.load_manifest(plan_id, task_id)
        if manifest is None:
            return self._finish(
                plan_id, task_id, None, None, ok=False,
                error="snapshot_not_found: snapshot não encontrado.",
                action="snapshot_not_found",
            )

        requested_path = manifest.requested_path
        # Confinamento: SEMPRE re-resolver (resolved_path do manifest é
        # debug apenas — nunca autoridade, spec 11K §5).
        try:
            resolved = self._sandbox.resolve(requested_path)
        except FilesystemError as exc:
            logger.warning(
                "restore_snapshot bloqueado (resolve): %s", exc,
            )
            return self._finish(
                plan_id, task_id, requested_path, None, ok=False,
                error=f"alvo fora do workspace: {exc}",
                action="blocked",
            )

        if manifest.existed_before:
            return self._restore_write(plan_id, task_id, manifest, resolved)
        return self._undo_create(plan_id, task_id, manifest, resolved)

    # ---------------------------------------------------------- ações (MVP)
    def _restore_write(self, plan_id: str, task_id: str, manifest: Any,
                       resolved: Path) -> ToolResult:
        """``existed_before=True``: sobrescreve o alvo com o backup."""
        if not manifest.backup_relpath:
            return self._finish(
                plan_id, task_id, manifest.requested_path, resolved,
                ok=False,
                error="no_backup: o snapshot não tem backup "
                      "(o arquivo anterior não foi copiado).",
                action="no_backup",
            )
        backup = self._safe_backup_path(manifest.backup_relpath)
        if backup is None:
            return self._finish(
                plan_id, task_id, manifest.requested_path, resolved,
                ok=False,
                error="backup_invalid: backup_relpath fora do snapshots_dir.",
                action="backup_invalid",
            )
        if not backup.is_file():
            return self._finish(
                plan_id, task_id, manifest.requested_path, resolved,
                ok=False,
                error="backup_missing: arquivo de backup ausente.",
                action="backup_missing",
            )
        try:
            self._sandbox.check_operation(OPERATION_WRITE, resolved)
        except FilesystemError as exc:
            logger.warning("restore_snapshot bloqueado (política): %s", exc)
            return self._finish(
                plan_id, task_id, manifest.requested_path, resolved,
                ok=False, error=f"escrita bloqueada pela política: {exc}",
                action="blocked",
            )
        try:
            backup_bytes = backup.read_bytes()
            resolved.write_bytes(backup_bytes)
        except OSError as exc:
            logger.error("restore_snapshot falhou em %s: %s", resolved, exc)
            return self._finish(
                plan_id, task_id, manifest.requested_path, resolved,
                ok=False, error=f"erro de filesystem: {exc}",
                action="restore_error",
            )
        return self._finish(
            plan_id, task_id, manifest.requested_path, resolved, ok=True,
            error=None, action=ACTION_RESTORE_WRITE,
            bytes_restored=len(backup_bytes),
        )

    def _undo_create(self, plan_id: str, task_id: str, manifest: Any,
                     resolved: Path) -> ToolResult:
        """``existed_before=False``: deleta o alvo (undo do create)."""
        if not resolved.exists():
            # Idempotente: o alvo já não existe — nada a desfazer.
            return self._finish(
                plan_id, task_id, manifest.requested_path, resolved,
                ok=True, error=None, action=ACTION_ALREADY_GONE,
            )
        if resolved.is_dir():
            return self._finish(
                plan_id, task_id, manifest.requested_path, resolved,
                ok=False,
                error="not_a_file: o alvo é um diretório (snapshots 11K "
                      "são de arquivo único).",
                action="not_a_file",
            )
        try:
            self._sandbox.check_operation(OPERATION_DELETE, resolved)
        except FilesystemError as exc:
            logger.warning("restore_snapshot bloqueado (política): %s", exc)
            return self._finish(
                plan_id, task_id, manifest.requested_path, resolved,
                ok=False, error=f"exclusão bloqueada pela política: {exc}",
                action="blocked",
            )
        try:
            resolved.unlink()
        except OSError as exc:
            logger.error("restore_snapshot falhou em %s: %s", resolved, exc)
            return self._finish(
                plan_id, task_id, manifest.requested_path, resolved,
                ok=False, error=f"erro de filesystem: {exc}",
                action="restore_error",
            )
        return self._finish(
            plan_id, task_id, manifest.requested_path, resolved, ok=True,
            error=None, action=ACTION_UNDO_CREATE,
        )

    # ------------------------------------------------------------- interno
    def _safe_backup_path(self, relpath: str) -> Path | None:
        """Resolve ``backup_relpath`` **dentro** de ``snapshots_dir``.

        Anti-traversal: caminho resolvido deve permanecer dentro da raiz
        (``..``/absoluto ⇒ ``None``).
        """
        root = self._store.root_dir
        try:
            root_resolved = root.resolve()
            candidate = (root / relpath)
            candidate_resolved = candidate.resolve()
            candidate_resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            return None
        return candidate

    def _finish(self, plan_id: str | None, task_id: str | None,
                requested_path: str | None, resolved: Path | None,
                *, ok: bool, error: str | None, action: str,
                **detail: Any) -> ToolResult:
        """Resultado estruturado + auditoria (somente metadados)."""
        if self._audit is not None:
            try:
                self._audit.record(
                    tool=self.name,
                    operation=action,
                    requested_path=requested_path,
                    resolved_path=str(resolved) if resolved is not None else None,
                    success=ok,
                    error=error,
                    snapshot_plan_id=plan_id,
                    snapshot_task_id=task_id,
                    **detail,
                )
            except Exception:
                logger.exception(
                    "restore_snapshot: falha ao auditar (não fatal).",
                )
        data: dict[str, Any] = {
            "action": action,
            "snapshot_plan_id": plan_id,
            "snapshot_task_id": task_id,
            "requested_path": requested_path,
            "resolved_path": str(resolved) if resolved is not None else None,
        }
        data.update(detail)
        return ToolResult(ok=ok, data=data, error=error)
