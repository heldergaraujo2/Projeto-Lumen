"""Loop de aprovação do plano (Fase 2) — o portão do usuário.

Regra central, herdada de ``app/core/bridge.py``: **o LLM propõe, o usuário
autoriza**. Um plano fica em ``PENDING`` até uma decisão explícita; só um
plano ``APPROVED`` pode ser convertido em execução
(:meth:`FeaturePlan.to_planner_plan`).

Propriedades garantidas (todas cobertas por teste):

- plano pendente **nunca** executa;
- plano **rejeitado** nunca executa e a rejeição é registrada com o motivo;
- aprovar um plano de outro ``plan_id`` é erro — não há aprovação cruzada;
- a decisão é vinculada ao ``digest`` do plano: se o conteúdo mudar depois
  da aprovação, a aprovação é **invalidada** (defesa contra TOCTOU);
- o histórico de decisões é append-only e limitado (anti-crescimento).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from app.planning.models import (
    ApprovalRecord,
    ApprovalStatus,
    FeaturePlan,
    PlanNotApprovedError,
    PlanningError,
)

logger = logging.getLogger("lumen.planning.approval")

#: Teto do histórico de decisões mantido em memória.
MAX_HISTORY = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ApprovalDecision:
    """Resultado de uma tentativa de aprovar/rejeitar."""

    plan_id: str
    accepted: bool
    status: ApprovalStatus
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "accepted": self.accepted,
            "status": self.status.value,
            "reason": self.reason,
        }


@dataclass
class ApprovalGate:
    """Mantém planos pendentes e aplica a decisão do usuário.

    Não executa nada: apenas guarda estado de aprovação e devolve o plano
    decidido. Quem executa é o chamador, e só pode fazê-lo passando pelo
    :meth:`~app.planning.models.FeaturePlan.to_planner_plan`, que revalida.
    """

    #: Teto de planos pendentes simultâneos (anti-acúmulo).
    max_pending: int = 20
    _pending: dict[str, FeaturePlan] = field(default_factory=dict, repr=False)
    _decided: dict[str, ApprovalRecord] = field(default_factory=dict, repr=False)
    _history: list[ApprovalRecord] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------- regras
    def submit(self, plan: FeaturePlan) -> FeaturePlan:
        """Registra um plano como pendente de decisão.

        Rejeita reenvio do mesmo ``plan_id`` e excedente de pendentes.
        """
        plan.validate()
        if plan.plan_id in self._pending:
            raise PlanningError(f"plano {plan.plan_id} já está pendente de aprovação")
        if plan.plan_id in self._decided:
            raise PlanningError(
                f"plano {plan.plan_id} já foi decidido "
                f"({self._decided[plan.plan_id].status.value}); use outro id"
            )
        if len(self._pending) >= self.max_pending:
            raise PlanningError(
                f"já existem {len(self._pending)} planos pendentes (máximo {self.max_pending})"
            )
        if plan.is_approved:
            raise PlanningError(
                f"plano {plan.plan_id} já chega aprovado; envie-o pendente "
                "e registre a decisão pelo gate"
            )
        pending = plan.with_approval(ApprovalRecord(plan_id=plan.plan_id))
        self._pending[plan.plan_id] = pending
        logger.info("Plano %s aguardando aprovação do usuário.", plan.plan_id)
        return pending

    def approve(
        self, plan_id: str, *, note: str = "", approved_by: str = "local-user"
    ) -> FeaturePlan:
        """Aprova um plano pendente e devolve a cópia aprovada."""
        pending = self._require_pending(plan_id)
        record = ApprovalRecord(
            plan_id=plan_id,
            status=ApprovalStatus.APPROVED,
            decided_at=_now_iso(),
            note=note[:1_000],
            approved_by=approved_by[:200],
        )
        approved = pending.with_approval(record)
        self._finalise(plan_id, record)
        logger.info("Plano %s APROVADO por %s.", plan_id, approved_by)
        return approved

    def reject(self, plan_id: str, *, reason: str = "", rejected_by: str = "local-user") -> FeaturePlan:
        """Rejeita um plano pendente; nada será executado."""
        pending = self._require_pending(plan_id)
        record = ApprovalRecord(
            plan_id=plan_id,
            status=ApprovalStatus.REJECTED,
            decided_at=_now_iso(),
            note=reason[:1_000],
            approved_by=rejected_by[:200],
        )
        rejected = pending.with_approval(record)
        self._finalise(plan_id, record)
        logger.info("Plano %s REJEITADO: %s", plan_id, reason or "(sem motivo)")
        return rejected

    def expire(self, plan_id: str, *, reason: str = "expirado") -> FeaturePlan:
        """Marca um pendente como expirado (ex.: timeout de sessão)."""
        pending = self._require_pending(plan_id)
        record = ApprovalRecord(
            plan_id=plan_id,
            status=ApprovalStatus.EXPIRED,
            decided_at=_now_iso(),
            note=reason[:1_000],
        )
        expired = pending.with_approval(record)
        self._finalise(plan_id, record)
        return expired

    # ------------------------------------------------------------ consulta
    def pending(self) -> tuple[FeaturePlan, ...]:
        return tuple(self._pending.values())

    def get(self, plan_id: str) -> FeaturePlan | None:
        return self._pending.get(plan_id)

    def decision_for(self, plan_id: str) -> ApprovalRecord | None:
        return self._decided.get(plan_id)

    def history(self) -> tuple[ApprovalRecord, ...]:
        return tuple(self._history)

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def __iter__(self) -> Iterator[FeaturePlan]:
        return iter(self._pending.values())

    # -------------------------------------------------------------- interno
    def _require_pending(self, plan_id: str) -> FeaturePlan:
        if not isinstance(plan_id, str) or not plan_id.strip():
            raise PlanningError("plan_id é obrigatório")
        plan = self._pending.get(plan_id)
        if plan is None:
            if plan_id in self._decided:
                raise PlanningError(
                    f"plano {plan_id} já foi decidido "
                    f"({self._decided[plan_id].status.value})"
                )
            raise PlanningError(f"plano {plan_id} não está pendente de aprovação")
        return plan

    def _finalise(self, plan_id: str, record: ApprovalRecord) -> None:
        self._pending.pop(plan_id, None)
        self._decided[plan_id] = record
        self._history.append(record)
        if len(self._history) > MAX_HISTORY:
            del self._history[: len(self._history) - MAX_HISTORY]


@dataclass(frozen=True)
class ApprovalResult:
    """Par (plano, decisão) pronto para a UI exibir."""

    plan: FeaturePlan
    decision: ApprovalDecision

    @property
    def executable(self) -> bool:
        return self.plan.is_approved


def require_approved(plan: FeaturePlan) -> FeaturePlan:
    """Guarda de sanidade reutilizável antes de qualquer execução."""
    if not plan.is_approved:
        raise PlanNotApprovedError(
            f"plano {plan.plan_id} está {plan.approval.status.value}; "
            "nenhuma execução é permitida sem aprovação explícita"
        )
    return plan


__all__ = [
    "ApprovalDecision",
    "ApprovalGate",
    "ApprovalResult",
    "MAX_HISTORY",
    "require_approved",
]
