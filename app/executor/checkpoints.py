"""Checkpoints de execução (Lumen 0.4.x — fundação).

Abstração que permitirá, no futuro, **pausar a execução antes de ações
importantes** e solicitar confirmação (interface gráfica futura — nesta
etapa é somente API interna, sem UI).

Ciclo representado:

- ``PENDING_APPROVAL``: checkpoint **necessário** — execução **pausada**
  aguardando confirmação;
- ``APPROVED``: checkpoint **aprovado** — a tarefa pode executar;
- ``REFUSED``: checkpoint **recusado** — o plano falha de forma
  controlada e as tarefas restantes ficam ``SKIPPED``.

Nada aqui executa ações, toca arquivos ou fala com o usuário — apenas
representa estados e decisões.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from app.planner.models import PlannedTask


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CheckpointStatus(str, Enum):
    """Estado de um checkpoint."""

    PENDING_APPROVAL = "PENDING_APPROVAL"  # necessário; pausado
    APPROVED = "APPROVED"                  # aprovado
    REFUSED = "REFUSED"                    # recusado


@dataclass(frozen=True)
class CheckpointRequest:
    """Pedido de confirmação antes de executar uma tarefa.

    Args:
        id: identificador sequencial por executor (``CP-0001``…).
        task_id: tarefa que exige confirmação antes de rodar.
        reason: por que a confirmação é pedida (descrição da tarefa).
        status: :class:`CheckpointStatus` (inicia ``PENDING_APPROVAL``).
        note: observação registrada na decisão (aprovação/recusa).
        decided_at: timestamp da decisão (``None`` enquanto pendente).
    """

    id: str
    task_id: str
    reason: str
    status: CheckpointStatus = CheckpointStatus.PENDING_APPROVAL
    note: str = ""
    decided_at: str | None = None
    created_at: str = field(default_factory=_now_iso)

    @property
    def pending(self) -> bool:
        return self.status is CheckpointStatus.PENDING_APPROVAL

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "reason": self.reason,
            "status": self.status.value,
            "note": self.note,
            "decided_at": self.decided_at,
            "created_at": self.created_at,
        }


class CheckpointPolicy(ABC):
    """Decide quais tarefas exigem checkpoint antes de executar.

    Futuro: políticas por criticidade/tipo de ação (ex.: antes de
    sobrescrever arquivos — 0.5+). Hoje: ``NeverCheckpoints`` (padrão,
    comportamento da 0.4.1 preservado) e ``EveryTaskCheckpoints``.
    """

    @abstractmethod
    def requires_checkpoint(self, task: PlannedTask) -> bool:
        """A tarefa exige confirmação antes de executar?"""
        raise NotImplementedError  # pragma: no cover


class NeverCheckpoints(CheckpointPolicy):
    """Nenhum checkpoint (padrão — compatível com a 0.4.1)."""

    def requires_checkpoint(self, task: PlannedTask) -> bool:
        return False


class EveryTaskCheckpoints(CheckpointPolicy):
    """Toda tarefa exige checkpoint (útil para testes/validação)."""

    def requires_checkpoint(self, task: PlannedTask) -> bool:
        return True
