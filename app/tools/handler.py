"""Ponte Executor ↔ ferramentas (Lumen 0.5).

O :class:`ToolTaskHandler` é um :class:`~app.executor.handlers.TaskHandler`
que **despacha cada tarefa para a ferramenta designada** via
:class:`~app.tools.base.ToolRegistry` (porteio de permissões incluído).
Ele vive aqui — na camada de tools — para que o **núcleo do Executor
permaneça agnóstico de ferramentas** (o pacote ``app.executor`` não
importa ``app.tools``; auditoria AST nos testes garante).

Regras:

- a tarefa designa a ferramenta em ``PlannedTask.tool`` com parâmetros
  em ``PlannedTask.parameters`` (o Planner **não** produz esses campos
  nesta versão — planos com ferramentas são montados programaticamente);
- tarefa **sem** ferramenta designada falha de forma honesta/controlada
  (nada é "simulado" aqui — sem execução fantasma);
- permissão negada ⇒ :class:`~app.executor.handlers.HandlerError`
  (tarefa FAILED controlada; a operação **não** roda);
- ferramenta inexistente ⇒ idem;
- resultado ``ok=False`` da ferramenta ⇒ idem, com o erro estruturado;
- quando um ``audit`` é fornecido, bloqueios de permissão também são
  auditados, e cada execução roda sob o contexto tarefa/plano.

:class:`ToolCheckpoints` é uma :class:`~app.executor.checkpoints.CheckpointPolicy`
que exige checkpoint para tarefas cuja ferramenta é potencialmente
destrutiva (ex.: ``FILESYSTEM_DESTRUCTIVE_TOOLS``) — a arquitetura de
consentimento da 0.4.x aplicada às tools reais, **sem UI obrigatória**.
"""
from __future__ import annotations

import json
import logging
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Iterable

from app.executor.checkpoints import CheckpointPolicy
from app.executor.handlers import HandlerError, TaskHandler
from app.planner.models import PlannedTask
from app.security.permissions import PermissionDeniedError
from app.tools.base import ToolError, ToolNotFoundError, ToolRegistry
from app.tools.filesystem import (
    FILESYSTEM_DESTRUCTIVE_TOOLS,
    FilesystemAudit,
    WorkspaceSandbox,
)
from app.tools.snapshot_store import SnapshotManifest, SnapshotStore, _safe_name

logger = logging.getLogger("lumen.tools.handler")


class ToolTaskHandler(TaskHandler):
    """Executa tarefas despachando para ferramentas do ``ToolRegistry``.

    Args:
        registry: registro com porteio de permissões (ex. construído por
            :func:`app.tools.filesystem.build_filesystem_registry`).
        audit: trilha de auditoria opcional (registra também os
            bloqueios de permissão e anexa contexto tarefa/plano).
        plan_id: id do plano de origem (apenas para auditoria).
        sandbox: sandbox do workspace (11K: confinamento do caminho do
            snapshot).
        snapshot_store: store 11K de snapshots "before" (opt-in).
        enable_snapshots: 11K — snapshot "before" das tools destrutivas
            (default **OFF** — bit-a-bit; best-effort, nunca interrompe
            a execução).
    """

    name = "tools"

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        audit: FilesystemAudit | None = None,
        plan_id: str | None = None,
        sandbox: WorkspaceSandbox | None = None,
        snapshot_store: SnapshotStore | None = None,
        enable_snapshots: bool = False,
    ) -> None:
        self._registry = registry
        self._audit = audit
        self._plan_id = plan_id
        # 11K: snapshot "before" de operações destrutivas (opt-in,
        # default OFF — bit-a-bit; best-effort; sem conteúdo no audit).
        self._sandbox = sandbox
        self._snapshot_store = snapshot_store
        self._enable_snapshots = enable_snapshots

    def execute(self, task: PlannedTask) -> str:
        if not task.tool:
            raise HandlerError(
                f"A tarefa {task.id} não designa ferramenta (campo 'tool' "
                "vazio); nada foi executado."
            )
        parameters: dict[str, Any] = dict(task.parameters or {})
        requested = parameters.get("path") or parameters.get("cwd")
        context = (
            self._audit.scoped(task_id=task.id, plan_id=self._plan_id)
            if self._audit is not None
            else nullcontext()
        )
        try:
            with context:
                # 11K: snapshot "before" (best-effort; NUNCA interrompe a
                # execução) para tools destrutivas — depois do checkpoint
                # aprovado (pausa é anterior ao handler) e antes da tool.
                self._maybe_snapshot_before(task, parameters)
                raw = self._registry.execute(task.tool, **parameters)
        except PermissionDeniedError as exc:
            if self._audit is not None:
                self._audit.record(
                    tool=task.tool,
                    operation="permission_gate",
                    requested_path=requested if isinstance(requested, str) else None,
                    success=False,
                    error=f"Permissão negada: {exc}",
                )
            raise HandlerError(
                f"Ferramenta {task.tool!r} bloqueada: {exc}"
            ) from exc
        except ToolNotFoundError as exc:
            raise HandlerError(
                f"Tarefa {task.id}: ferramenta não registrada: {task.tool!r}."
            ) from exc
        except ToolError as exc:
            raise HandlerError(f"Ferramenta {task.tool!r} falhou: {exc}") from exc

        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):  # ferramenta não estruturada
            payload = {"ok": True, "data": {"result": raw}, "error": None}
        if not payload.get("ok"):
            error = payload.get("error") or f"a ferramenta {task.tool!r} falhou"
            raise HandlerError(f"Ferramenta {task.tool!r}: {error}")
        return raw

    # -------------------------------------------------------- 11K (snapshot)
    def _maybe_snapshot_before(self, task: PlannedTask,
                               parameters: dict[str, Any]) -> None:
        """11K: snapshot "before" de tool destrutiva (best-effort).

        Só roda com a feature ON (``enable_snapshots`` + store + sandbox
        fornecidos) e a task usando ``FILESYSTEM_DESTRUCTIVE_TOOLS``.
        **Nunca levanta**: qualquer falha é logada + auditada
        (``operation="snapshot_before"``, ``success=False``) e a
        execução continua — o snapshot jamais altera o desfecho da
        operação. A auditoria carrega **somente metadados** (sem
        conteúdo).
        """
        if not self._enable_snapshots:
            return
        if self._snapshot_store is None or self._sandbox is None:
            return
        if task.tool not in FILESYSTEM_DESTRUCTIVE_TOOLS:
            return
        requested_path = parameters.get("path")
        if not isinstance(requested_path, str) or not requested_path.strip():
            return  # sem caminho utilizável: sem snapshot (falha honesta)
        try:
            resolved = self._sandbox.resolve(requested_path)
        except Exception as exc:  # fora do workspace etc.: auditor + segue
            logger.warning(
                "11K: snapshot_before falhou no resolve (não fatal): %s", exc,
            )
            self._audit_snapshot(
                task, requested_path, None, success=False,
                error=f"resolve falhou: {exc}",
            )
            return
        try:
            manifest = self._snapshot_store.create_snapshot(
                self._plan_id or "", task.id, task.tool,
                requested_path, resolved,
            )
        except Exception as exc:  # defensivo: o store é best-effort
            logger.warning("11K: snapshot_before falhou (não fatal): %s", exc)
            self._audit_snapshot(
                task, requested_path, resolved, success=False,
                error=f"snapshot falhou: {exc}",
            )
            return
        self._audit_snapshot(
            task, requested_path, resolved, success=True, manifest=manifest,
            snapshot_dir=(
                f"{_safe_name(self._plan_id or '')}/{_safe_name(task.id)}"
            ),
        )

    def _audit_snapshot(
        self,
        task: PlannedTask,
        requested_path: str,
        resolved: Path | None,
        *,
        success: bool,
        error: str | None = None,
        manifest: SnapshotManifest | None = None,
        snapshot_dir: str | None = None,
    ) -> None:
        """Registra ``snapshot_before`` na auditoria (somente metadados).

        O próprio registro é best-effort: falha ao auditar não quebra a
        execução (apenas loga).
        """
        if self._audit is None:
            return
        try:
            self._audit.record(
                tool=task.tool,
                operation="snapshot_before",
                requested_path=requested_path,
                resolved_path=str(resolved) if resolved is not None else None,
                success=success,
                error=error,
                snapshot_manifest=(
                    manifest.to_dict() if manifest is not None else None
                ),
                snapshot_dir=snapshot_dir,
            )
        except Exception:
            logger.exception(
                "11K: falha ao registrar auditoria snapshot_before "
                "(não fatal).",
            )


class ToolCheckpoints(CheckpointPolicy):
    """Exige checkpoint para tarefas que usam ferramentas listadas.

    Uso típico (operações destrutivas de filesystem)::

        policy = ToolCheckpoints(FILESYSTEM_DESTRUCTIVE_TOOLS)
        executor = PlanExecutor(plan, handler, checkpoints=policy)

    A execução pausa (``PENDING_APPROVAL``) antes da tarefa; aprovar
    executa, recusar falha o plano de forma controlada — consentimento
    sem UI obrigatória (API interna da 0.4.x).
    """

    def __init__(self, required_tools: Iterable[str]) -> None:
        self._required_tools = frozenset(required_tools)

    @property
    def required_tools(self) -> frozenset[str]:
        return self._required_tools

    def requires_checkpoint(self, task: PlannedTask) -> bool:
        return task.tool is not None and task.tool in self._required_tools
