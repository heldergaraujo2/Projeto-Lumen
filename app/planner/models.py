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
    """Ciclo de vida de um plano."""

    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class PlannedTaskStatus(str, Enum):
    """Estado de uma tarefa planejada."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class PlannedTask:
    """Uma etapa planejada de um plano."""

    id: str
    description: str
    order: int
    dependencies: tuple[str, ...] = ()
    status: PlannedTaskStatus = PlannedTaskStatus.PENDING
    result: str | None = None
    error: str | None = None
    tool: str | None = None
    parameters: dict[str, Any] | None = None
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
    """Plano estruturado produzido pelo Planner."""

    id: str
    objective: str
    status: PlanStatus = PlanStatus.PLANNING
    analysis: tuple[str, ...] = ()
    tasks: tuple[PlannedTask, ...] = ()
    error: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    conversation_id: str | None = None

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
            "conversation_id": self.conversation_id,
        }
