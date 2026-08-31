"""Tool Calling / Planner Bridge — a ponte Chat → Ferramentas (0.6.3).

Antes da 0.6.3 o chat era **somente** conversacional: ``send_message``
ia direto ao provedor e nenhuma mensagem chegava ao Planner ou às
ferramentas (diagnóstico 0.6.2). Este módulo fecha os três gaps:

1. classifica o pedido (conversa × ação) **via provedor** com o
   protocolo estruturado do Planner (nada de regex no caminho principal
   — o regex determinístico vive só dentro do :class:`MockProvider`,
   que simula o LLM em testes/offline);
2. o Planner emite ``tool``/``parameters`` **validados contra uma
   allowlist** (:mod:`app.planner.catalog`) — o LLM não pode inventar
   ferramentas nem parâmetros;
3. entrega o plano válido ao ``ToolsController.run_plan`` — a cadeia de
   segurança existente (permissões → workspace/sandbox → checkpoint →
   tool) permanece a **autoridade final** e intocada.

Hierarquia de autoridade (nunca invertida)::

    Sistema de segurança → Permissões → Workspace/Sandbox →
    Checkpoint → ToolRegistry → Plano → LLM

O bridge **não** contém lógica de filesystem/terminal (isso vive na
camada de tools); ele apenas orquestra abstrações. Nenhum poder novo é
criado: se a operação exige WRITE/TERMINAL e a permissão não foi
concedida, falha controlada — "o usuário pediu" não é "o usuário
autorizou".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("lumen.bridge")


class RequestState(str, Enum):
    """Estados do ciclo de vida de uma mensagem (0.6.3 — FASE 8).

    CONVERSATIONAL/PLAN_*/WAITING_APPROVAL/COMPLETED/FAILED/REJECTED
    são desfechos observáveis; PLANNING/EXECUTING/VERIFYING são
    transitórios (registrados no log/auditoria da cadeia).
    """

    CONVERSATIONAL = "CONVERSATIONAL"    # só conversa — nada é executado
    PLANNING = "PLANNING"                # pedindo o plano ao provedor
    PLAN_READY = "PLAN_READY"            # plano válido pronto p/ executar
    PLAN_INVALID = "PLAN_INVALID"        # saída inválida — nada executa
    WAITING_APPROVAL = "WAITING_APPROVAL"  # checkpoint pausou a execução
    EXECUTING = "EXECUTING"              # execução em andamento
    VERIFYING = "VERIFYING"              # verificação pós-execução
    COMPLETED = "COMPLETED"              # sucesso (verificado)
    FAILED = "FAILED"                    # falha controlada
    REJECTED = "REJECTED"                # reprovação de verificação


@dataclass(frozen=True)
class AgentOutcome:
    """Resultado de :meth:`ToolCallingBridge.process` para a UI.

    ``text`` é SEMPRE uma mensagem pronta para exibir ao usuário (no
    caminho conversacional é a resposta do provedor, já transmitida por
    streaming via ``on_delta``).
    """

    state: RequestState
    text: str
    plan_id: str | None = None


class ToolCallingBridge:
    """Orquestra CHAT → INTENÇÃO → PLANNER → VALIDAÇÃO → TOOLS CONTROLLER.

    Depende apenas de abstrações: o ``agent`` (provedor vigente,
    memória, gates) e o ``controller`` (fachada de ferramentas). Não
    conhece UI, filesystem ou terminal.
    """

    def __init__(self, agent, controller) -> None:
        self._agent = agent
        self._controller = controller

    # ------------------------------------------------------------------ API
    def process(self, text: str, on_delta=None) -> AgentOutcome:
        """Processa uma mensagem do chat decidindo conversa × ação."""
        cleaned = (text or "").strip()
        if not cleaned:
            return AgentOutcome(
                RequestState.CONVERSATIONAL, "A mensagem não pode ser vazia."
            )

        # 1) PLANNING: o provedor classifica e (se for ação) planeja com
        #    a allowlist de ferramentas do controller.
        catalog = self._controller.planning_catalog()
        result = self._agent.request_tool_plan(cleaned, catalog)

        if result.kind == "conversation":
            # 2) Conversa: fluxo clássico preservado (streaming + memória).
            reply = self._agent.send_message(cleaned, on_delta=on_delta)
            return AgentOutcome(RequestState.CONVERSATIONAL, reply)

        if result.kind == "invalid":
            # 3) Saída inválida do LLM/provedor: falha controlada, NADA
            #    executa (nunca execução parcial de plano inválido).
            reason = result.reason or "motivo desconhecido"
            logger.warning("Plano inválido via chat: %s", reason)
            message = (
                f"⚠ Não foi possível montar um plano válido: {reason}. "
                "Nada foi executado."
            )
            self._remember(cleaned, message)
            return AgentOutcome(
                RequestState.PLAN_INVALID, message, result.plan.id
            )

        plan = result.plan
        logger.info(
            "Plano %s pronto via chat (%d tarefa(s)) — executando.",
            plan.id, len(plan.tasks),
        )

        # 4) PLAN_READY → EXECUTING: entrega ao controller. Todas as
        #    proteções (permissões, sandbox, checkpoint) rodam lá.
        try:
            report = self._controller.run_plan(plan)
        except Exception as exc:  # controlado — a UI segue viva
            logger.exception("Falha ao executar plano %s via chat.", plan.id)
            message = f"✖ Falha ao executar o plano {plan.id}: {exc}"
            self._remember(cleaned, message)
            return AgentOutcome(RequestState.FAILED, message, plan.id)

        # 5) Desfecho do relatório de execução.
        return self.outcome_for_report(cleaned, plan.id, report)

    # ------------------------------------------------------------ internals
    def outcome_for_report(
        self, request: str | None, plan_id: str, report
    ) -> AgentOutcome:
        """Converte um ``ExecutionReport`` em mensagem para o usuário.

        Método **puro e reutilizável** (0.6.6): além do fluxo interno de
        :meth:`process`, pode ser usado por quem conclui um plano fora
        do ciclo do chat (ex.: aprovação de checkpoint na tela 🛡) para
        formatar o desfecho final com o mesmo texto. ``request`` é o
        texto original do usuário quando conhecido (usado para registrar
        o par pergunta/resposta na memória linear); ``None`` registra
        apenas a mensagem de desfecho.
        """
        from app.planner.models import PlanStatus
        from app.planner.models import PlannedTaskStatus

        done = sum(1 for r in report.tasks if r.status.value == "DONE")
        total = len(report.tasks)

        if report.status is PlanStatus.COMPLETED:
            verified = sum(
                1 for r in report.tasks
                if r.status.value == "DONE" and r.verified is not False
            )
            message = (
                f"✔ Plano {plan_id} concluído: {done}/{total} tarefa(s) "
                f"executada(s) e verificada(s) ({verified} com verificação "
                "explícita)."
            )
            self._remember(request, message)
            return AgentOutcome(RequestState.COMPLETED, message, plan_id)

        if report.status is PlanStatus.RUNNING and self._controller.has_pending:
            pending = self._controller.pending_approval() or {}
            what = pending.get("description") or pending.get("tool") or "?"
            where = pending.get("resolved_path") or pending.get("requested_path")
            message = (
                f"⏸ Plano {plan_id} pronto e PAUSADO para a sua aprovação "
                "(janela 🛡 Ferramentas e Segurança):\n"
                f"Operação: {what}"
            )
            if where:
                message += f"\nOnde: {where}"
            message += (
                "\nNada é executado antes de você APROVAR; RECUSAR mantém "
                "tudo como está."
            )
            self._remember(request, message)
            return AgentOutcome(RequestState.WAITING_APPROVAL, message, plan_id)

        # FAILED (fail-fast) — distingue reprovação de verificação.
        rejected = next(
            (r for r in report.tasks
             if r.status is PlannedTaskStatus.REJECTED),
            None,
        )
        first_error = (rejected or next(
            (r for r in report.tasks if r.error), None
        ))
        detail = getattr(first_error, "error", None) or "motivo desconhecido"
        state = RequestState.REJECTED if rejected is not None else RequestState.FAILED
        label = "reprovada na verificação" if rejected is not None else "falhou"
        message = (
            f"✖ Plano {plan_id} {label}: {detail} "
            f"({done}/{total} tarefa(s) concluída(s)). Nada mais foi executado."
        )
        self._remember(request, message)
        return AgentOutcome(state, message, plan_id)

    def _remember(self, request: str | None, reply: str) -> None:
        """Mantém o histórico de conversa coerente (ação também é conversa)."""
        try:
            memory = self._agent.memory
            if request:
                memory.add_message("user", request)
            memory.add_message("assistant", reply)
        except Exception:  # memória nunca deve derrubar o fluxo
            logger.exception("Falha ao registrar ação na memória linear.")
