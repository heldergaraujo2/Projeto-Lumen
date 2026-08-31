"""Estruturas de dados do Planner (Lumen 0.4 — fundação).

Um plano é **apenas dados**: objetivo, análise necessária e tarefas
ordenadas com dependências. Nada aqui executa, lê ou altera o computador
— execução é responsabilidade de versões futuras (executor + tools).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanStatus(str, Enum):
    """Ciclo de vida de um plano.

    - ``PLANNING``: em construção (estado transitório; planos devolvidos
      por :meth:`Planner.create_plan` já saem em um estado final).
    - ``READY``: plano válido, pronto para a execução.
    - ``RUNNING``: em execução pelo Executor (0.4.x).
    - ``BLOCKED``: uma pré-condição do ambiente impede planejar
      (ex.: provedor sem API key/modelo/SDK) — motivo em ``error``.
    - ``FAILED``: a IA devolveu um plano inválido/interpretável, o
      provedor falhou, **ou** a execução foi interrompida por uma tarefa
      que falhou — motivo em ``error``.
    - ``COMPLETED``: todas as tarefas foram executadas com sucesso.
    """

    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class PlannedTaskStatus(str, Enum):
    """Estado de uma tarefa planejada.

    O Planner sempre produz tarefas ``PENDING`` (ele não executa). Os
    estados de execução são atribuídos pelo Executor (0.4.x) aos
    ``TaskRun`` correspondentes:

    - ``PENDING``: aguardando execução;
    - ``IN_PROGRESS``: reservado (executor step-a-step futuro);
    - ``DONE``: executada com sucesso (``result`` preenchido);
    - ``FAILED``: falhou na execução (``error`` preenchido);
    - ``REJECTED``: executou, mas foi **reprovada na verificação**
      de resultado (0.4.x — ``result`` preservado, ``verified=False``);
    - ``SKIPPED``: não executada — plano interrompido por falha anterior.
    """

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class PlannedTask:
    """Uma etapa planejada de um plano.

    Args:
        id: identificador canônico dentro do plano (``T1``…``Tn``).
        description: o que deve ser feito (texto claro, sem comandos).
        order: posição de execução sugerida (1-based).
        dependencies: ids de tarefas que precisam terminar antes desta.
        status: sempre ``PENDING`` na 0.4 (nada é executado).
        result: resultado da execução (sempre ``None`` na 0.4).
        error: erro da execução (sempre ``None`` na 0.4).
    """

    id: str
    description: str
    order: int
    dependencies: tuple[str, ...] = ()
    status: PlannedTaskStatus = PlannedTaskStatus.PENDING
    result: str | None = None
    error: str | None = None
    #: Ferramenta designada para executar a tarefa (0.5). ``None`` em
    #: tarefas "descritivas" (todas as produzidas pelo Planner nesta
    #: versão — o protocolo de planejamento não emite tools); planos com
    #: ferramentas são montados programaticamente (ex.: integração
    #: Executor ↔ ToolRegistry).
    tool: str | None = None
    #: Parâmetros nomeados da ferramenta designada (0.5).
    parameters: dict[str, Any] | None = None
    #: 10B — critérios de sucesso declarados no planejamento.
    #: Metadado PURAMENTE INFORMATIVO (exibido em checkpoints/relatórios):
    #: nenhum efeito operacional — não altera execução, status ou gates.
    success_criteria: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "order": self.order,
            "dependencies": list(self.dependencies),
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "tool": self.tool,
            "parameters": self.parameters,
            "success_criteria": list(self.success_criteria),
        }


@dataclass(frozen=True)
class Plan:
    """Plano estruturado produzido pelo Planner.

    Args:
        id: identificador sequencial por Planner (``PLN-0001``…).
        objective: o pedido original do usuário.
        status: estado do ciclo de vida (:class:`PlanStatus`).
        analysis: o que precisa ser analisado/verificado antes da
            execução (identificado durante o planejamento).
        tasks: etapas ordenadas (:class:`PlannedTask`).
        error: motivo claro quando ``status`` é ``BLOCKED``/``FAILED``.
        created_at/updated_at: timestamps ISO-8601 (UTC).
    """

    id: str
    objective: str
    status: PlanStatus = PlanStatus.PLANNING
    analysis: tuple[str, ...] = ()
    tasks: tuple[PlannedTask, ...] = ()
    error: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    # ------------------------------------------------------------- helpers
    def task_by_id(self, task_id: str) -> PlannedTask | None:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    @property
    def ready(self) -> bool:
        return self.status is PlanStatus.READY

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "objective": self.objective,
            "status": self.status.value,
            "analysis": list(self.analysis),
            "tasks": [task.to_dict() for task in self.tasks],
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
