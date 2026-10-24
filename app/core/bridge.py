"""Tool Calling / Planner Bridge — a ponte Chat → Ferramentas (0.6.3 + Fase C).

Antes da 0.6.3 o chat era **somente** conversacional: ``send_message``
ia direto ao provedor e nenhuma mensagem chegava ao Planner ou às
ferramentas. Este módulo orquestra o fluxo de intenções e a recuperação
de contexto de execuções anteriores.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("lumen.bridge")

_READ_ONLY_RESULT_TOOLS = frozenset({
    "web_search",
    "unreal_get_info",
    "unreal_describe_object",
    "unreal_search_assets",
    "read_file",
    "search_files",
})


def _display_text(value: object, limit: int = 500) -> str:
    """Texto curto para a UI; não transforma dados externos em instruções."""
    if value is None:
        return ""
    text = " ".join(str(value).replace("\x00", "").split())
    if len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def _format_read_only_result(tool: str, data: Mapping) -> str:
    """Renderiza os resultados de leitura para o chat da UI com dados reais do ToolResult."""
    if tool == "read_file":
        requested_path = _display_text(data.get("requested_path"), 300)
        resolved_path = _display_text(data.get("resolved_path"), 300)
        exists = data.get("exists", True)
        lines = [f"Arquivo verificado — {requested_path}"]
        if resolved_path:
            lines.append(f"Caminho resolvido: {resolved_path}")
        lines.append(f"Existe: {'Sim' if exists else 'Não'}")
        if data.get("is_dir") is not None:
            lines.append(f"Tipo: {'Diretório' if data.get('is_dir') else 'Arquivo'}")
        return "\n".join(lines)

    if tool == "search_files":
        requested_path = _display_text(data.get("requested_path"), 300)
        resolved_path = _display_text(data.get("resolved_path"), 300)
        matches = data.get("matches") or []
        count = data.get("count", len(matches))
        lines = [f"Busca de arquivos — {requested_path}"]
        if resolved_path:
            lines.append(f"Caminho resolvido: {resolved_path}")
        lines.append(f"Arquivos encontrados ({count}):")
        if isinstance(matches, list):
            for match in matches[:20]:
                lines.append(f"  • {_display_text(match, 240)}")
            if len(matches) > 20:
                lines.append(f"  • … e mais {len(matches) - 20}")
        return "\n".join(lines)

    if tool == "web_search":
        lines = [f"Pesquisa web — {_display_text(data.get('query'), 240)}"]
        answer = _display_text(data.get("answer"), 800)
        if answer:
            lines.append(f"Resumo do provedor: {answer}")
        results = data.get("results")
        results = results if isinstance(results, list) else []
        for index, result in enumerate(results[:5], start=1):
            if not isinstance(result, Mapping):
                continue
            title = _display_text(result.get("title"), 180) or "Sem título"
            url = _display_text(result.get("url"), 500)
            snippet = _display_text(result.get("content"), 600)
            lines.append(f"[{index}] {title}")
            if url:
                lines.append(f"    {url}")
            if snippet:
                lines.append(f"    {snippet}")
        if not results:
            lines.append("Nenhum resultado encontrado.")
        return "\n".join(lines)

    if tool == "unreal_get_info":
        connection = "conectado" if data.get("connected") else "não conectado"
        lines = [
            f"Unreal Editor — {connection}",
            f"Endereço: {_display_text(data.get('base_url'), 180) or '—'}",
            f"Rotas disponíveis: {_display_text(data.get('route_count'), 20) or '0'}",
        ]
        routes = data.get("routes")
        if isinstance(routes, list) and routes:
            lines.extend(f"  • {_display_text(route, 240)}" for route in routes[:12])
            if len(routes) > 12:
                lines.append(f"  • … e mais {len(routes) - 12}")
        return "\n".join(lines)

    if tool == "unreal_describe_object":
        lines = [
            f"Objeto Unreal — {_display_text(data.get('name'), 180) or 'sem nome'}",
            f"Caminho: {_display_text(data.get('object_path'), 400) or '—'}",
            f"Classe: {_display_text(data.get('class'), 240) or '—'}",
        ]
        for label, key, count_key in (
            ("Propriedades", "properties", "property_count"),
            ("Funções", "functions", "function_count"),
        ):
            values = data.get(key)
            values = values if isinstance(values, list) else []
            count = data.get(count_key, len(values))
            lines.append(f"{label} ({_display_text(count, 20)}):")
            lines.extend(f"  • {_display_text(value, 180)}" for value in values[:30])
            if len(values) > 30:
                lines.append(f"  • … e mais {len(values) - 30}")
        return "\n".join(lines)

    if tool == "unreal_search_assets":
        query = _display_text(data.get("query"), 200)
        lines = [
            f"Assets Unreal — busca: {query}",
            f"Encontrados: {_display_text(data.get('count'), 20) or '0'}",
        ]
        assets = data.get("assets")
        assets = assets if isinstance(assets, list) else []
        for asset in assets[:20]:
            if not isinstance(asset, Mapping):
                continue
            name = _display_text(asset.get("name"), 180) or "Sem nome"
            asset_class = _display_text(asset.get("class"), 120)
            path = _display_text(asset.get("path"), 400)
            lines.append(f"  • {name}" + (f" ({asset_class})" if asset_class else ""))
            if path:
                lines.append(f"      {path}")
        if len(assets) > 20:
            lines.append(f"  • … e mais {len(assets) - 20}")
        return "\n".join(lines)

    return ""


def _read_only_results_for_display(report) -> str:
    """Extrai saída legível dos resultados de leitura, com tamanho limitado."""
    blocks: list[str] = []
    for run in getattr(report, "tasks", ()):
        if getattr(getattr(run, "status", None), "value", None) != "DONE":
            continue
        raw = getattr(run, "result", None)
        if not isinstance(raw, str) or not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, Mapping) or not payload.get("ok"):
            continue
        data = payload.get("data")
        if not isinstance(data, Mapping):
            continue
        name = data.get("tool") or data.get("operation")
        if name not in _READ_ONLY_RESULT_TOOLS:
            continue
        block = _format_read_only_result(str(name), data)
        if block:
            blocks.append(block)
    if not blocks:
        return ""
    text = "Resultados das consultas (dados para você revisar):\n" + "\n\n".join(blocks)
    return text[:8_000] + ("\n… (saída truncada)" if len(text) > 8_000 else "")


class RequestState(str, Enum):
    """Estados do ciclo de vida de uma mensagem (0.6.3 — FASE 8)."""

    CONVERSATIONAL = "CONVERSATIONAL"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    PLAN_INVALID = "PLAN_INVALID"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class AgentOutcome:
    """Resultado de :meth:`ToolCallingBridge.process` para a UI."""

    state: RequestState
    text: str
    plan_id: str | None = None
    execution_details: dict[str, Any] | None = None


class ToolCallingBridge:
    """Orquestra CHAT → INTENÇÃO → PLANNER → VALIDAÇÃO → TOOLS CONTROLLER."""

    def __init__(self, agent, controller) -> None:
        self._agent = agent
        self._controller = controller

    # ------------------------------------------------------------------ API
    def process(
        self, text: str, on_delta=None, conversation_id: str | None = None
    ) -> AgentOutcome:
        """Processa uma mensagem do chat decidindo conversa × ação."""
        cleaned = (text or "").strip()
        if not cleaned:
            return AgentOutcome(
                RequestState.CONVERSATIONAL, "A mensagem não pode ser vazia."
            )

        # 1) PLANNING
        catalog = self._controller.planning_catalog()
        result = self._agent.request_tool_plan(cleaned, catalog)

        if result.kind == "conversation":
            # Tenta recuperar contexto de execução prévia se houver pergunta sobre execuções anteriores
            context_text = self.get_execution_context(conversation_id, cleaned)
            augmented_input = (
                f"{cleaned}\n\n[Contexto de execuções anteriores recuperadas:\n{context_text}]"
                if context_text
                else cleaned
            )
            reply = self._agent.send_message(augmented_input, on_delta=on_delta)
            return AgentOutcome(RequestState.CONVERSATIONAL, reply)

        if result.kind == "invalid":
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
        if conversation_id:
            setattr(plan, "conversation_id", conversation_id)
        logger.info(
            "Plano %s pronto via chat (%d tarefa(s)) — executando.",
            plan.id, len(plan.tasks),
        )

        try:
            report = self._controller.run_plan(plan)
        except Exception as exc:
            logger.exception("Falha ao executar plano %s via chat.", plan.id)
            message = f"✖ Falha ao executar o plano {plan.id}: {exc}"
            self._remember(cleaned, message)
            return AgentOutcome(RequestState.FAILED, message, plan.id)

        return self.outcome_for_report(cleaned, plan.id, report)

    def get_execution_context(
        self, conversation_id: str | None, query: str = ""
    ) -> str:
        """Recupera execuções anteriores estruturadas para o contexto conversacional."""
        if not conversation_id:
            return ""

        execution_store = getattr(self._controller, "execution_store", None)
        if not execution_store:
            try:
                from app.config.settings import Settings
                from app.memory.execution_store import ExecutionBundleStore

                execution_store = ExecutionBundleStore(
                    Settings().execution_dir
                )
            except Exception:
                return ""

        records = execution_store.query_executions(
            conversation_id=conversation_id, limit=5
        )
        if not records:
            return ""

        lines = []
        for rec in records:
            tool = rec.get("tool_name") or "ferramenta"
            action = rec.get("requested_action") or ""
            res = rec.get("result")
            res_str = ""
            if isinstance(res, dict):
                data = res.get("data") if "data" in res else res
                if isinstance(data, dict):
                    resolved = data.get("resolved_path") or data.get("path")
                    exists = data.get("exists")
                    res_str = f"caminho_resolvido={resolved}, existe={exists}"
                else:
                    res_str = str(data)[:200]
            else:
                res_str = str(res)[:200] if res is not None else "Sem resultado"

            lines.append(
                f"- Execução {rec.get('execution_id')}: Tool '{tool}' ({action}) -> Resultado: {res_str}"
            )

        return "\n".join(lines)

    # -------------------------------------------------------- F2 ToolCall API
    def process_tool_call(self, payload: ToolCall | dict) -> AgentOutcome:
        """Recebe uma intenção ToolCall e entrega-a ao gateway seguro."""
        try:
            result = self._controller.run_tool_call(payload)
        except Exception as exc:
            logger.exception("Falha controlada ao processar ToolCall.")
            return AgentOutcome(RequestState.FAILED, f"✖ Falha ao processar ToolCall: {exc}")
        if result.ok:
            return AgentOutcome(RequestState.COMPLETED, "✔ ToolCall concluído.", result.data.get("plan_id"))
        if result.data.get("awaiting_approval"):
            return AgentOutcome(
                RequestState.WAITING_APPROVAL,
                "⏸ ToolCall validado e aguardando aprovação no checkpoint.",
                result.data.get("plan_id"),
            )
        return AgentOutcome(
            RequestState.FAILED,
            f"✖ ToolCall não concluído: {result.error or 'falha desconhecida'}",
            result.data.get("plan_id"),
        )

    # ------------------------------------------------------------ internals
    def outcome_for_report(
        self, request: str | None, plan_id: str, report
    ) -> AgentOutcome:
        """Converte um ``ExecutionReport`` em mensagem para o usuário."""
        from app.planner.models import PlanStatus, PlannedTaskStatus

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
            results = _read_only_results_for_display(report)
            visible = f"{message}\n\n{results}" if results else message
            return AgentOutcome(RequestState.COMPLETED, visible, plan_id)

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
            results = _read_only_results_for_display(report)
            visible = f"{message}\n\n{results}" if results else message
            return AgentOutcome(RequestState.WAITING_APPROVAL, visible, plan_id)

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
        results = _read_only_results_for_display(report)
        visible = f"{message}\n\n{results}" if results else message
        return AgentOutcome(state, visible, plan_id)

    def _remember(self, request: str | None, reply: str) -> None:
        """Mantém o histórico de conversa coerente."""
        try:
            memory = self._agent.memory
            if request:
                memory.add_message("user", request)
            memory.add_message("assistant", reply)
        except Exception:
            logger.exception("Falha ao registrar ação na memória linear.")
