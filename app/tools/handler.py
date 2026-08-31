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
from contextlib import nullcontext
from typing import Any, Iterable

from app.executor.checkpoints import CheckpointPolicy
from app.executor.handlers import HandlerError, TaskHandler
from app.planner.models import PlannedTask
from app.security.permissions import PermissionDeniedError
from app.tools.base import ToolError, ToolNotFoundError, ToolRegistry
from app.tools.filesystem import FilesystemAudit


class ToolTaskHandler(TaskHandler):
    """Executa tarefas despachando para ferramentas do ``ToolRegistry``.

    Args:
        registry: registro com porteio de permissões (ex. construído por
            :func:`app.tools.filesystem.build_filesystem_registry`).
        audit: trilha de auditoria opcional (registra também os
            bloqueios de permissão e anexa contexto tarefa/plano).
        plan_id: id do plano de origem (apenas para auditoria).
    """

    name = "tools"

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        audit: FilesystemAudit | None = None,
        plan_id: str | None = None,
    ) -> None:
        self._registry = registry
        self._audit = audit
        self._plan_id = plan_id

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
