"""Ponte entre o MCP e a cadeia de segurança do LUMEN (Fase 3).

O ponto perigoso de um servidor MCP de filesystem/terminal é virar um
**atalho** para as permissões do LUMEN: um LLM externo chamando
``write_file`` não pode pular o checkpoint que o usuário veria na UI.

Este módulo existe para garantir que isso não aconteça:

1. a execução passa por ``ToolsController.run_tool_call()``, que converte o
   ``ToolCall`` em um ``Plan`` de uma tarefa e roda ``run_plan()`` em
   seguida — permissões, sandbox, checkpoint, auditoria e verificação
   continuam ativos;
2. o que é **exposto** é fail-closed: tools destrutivas só aparecem com
   opt-in explícito do operador (``allow_write=True``), exatamente como
   ``web_search`` só aparece com provider habilitado;
3. um checkpoint pendente **não** é aprovado silenciosamente. Ou o servidor
   devolve "aguardando aprovação" (default), ou o operador autorizou
   previamente (``auto_approve=True``) — e nesse caso a autorização é
   nomeada, auditada e documentada como consentimento do humano que
   iniciou o processo.

Esta camada **não** conhece JSON-RPC nem MCP: recebe nome+argumentos e
devolve dados prontos para virar ``content``. Isso mantém a serialização
trocável e o gateway testável sozinho.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from app.tools.protocol import ToolCall, ToolDefinition, ToolProtocolError

logger = logging.getLogger(__name__)

#: Prefixo de toda mensagem devolvida ao cliente MCP.
CHECKPOINT_PENDING_MESSAGE = (
    "⏸ A operação está aguardando aprovação (checkpoint {checkpoint_id}). "
    "Nada foi executado. Este servidor MCP independente NÃO tem interface "
    "para aprovar este checkpoint: não repita a chamada (criaria outro). "
    "Para testar operações com escrita, reinicie o servidor explicitamente "
    "com --allow-write --auto-approve, APÓS revisar o risco; esse modo "
    "executa sem confirmação por operação."
)


class McpGatewayError(Exception):
    """Falha ao encaminhar uma chamada MCP para a cadeia do LUMEN."""


@dataclass
class ToolCallOutcome:
    """Resultado normalizado de uma chamada, pronto para virar ``content``."""

    ok: bool
    text: str
    structured: dict[str, Any] = field(default_factory=dict)
    awaiting_approval: bool = False


class ControllerToolGateway:
    """Expõe as tools de um ``ToolsController`` para o MCP.

    Args:
        controller: ``ToolsController`` **já configurado** (permissões
            concedidas, workspaces autorizados, terminal/allowlist). O
            gateway não configura nada por conta própria.
        allow_write: expõe tools destrutivas. Default ``False`` —
            fail-closed: um cliente MCP recém-conectado só lê.
        auto_approve: resolve os checkpoints automaticamente. Default
            ``False`` (devolve "aguardando aprovação"). Só faz sentido com
            ``allow_write=True`` e representa a autorização **prévia e
            explícita** do humano que iniciou o servidor — por isso é
            registrada em log a cada uso.
    """

    def __init__(
        self,
        controller: Any,
        *,
        allow_write: bool = False,
        auto_approve: bool = False,
        max_auto_approvals: int = 20,
    ) -> None:
        if auto_approve and not allow_write:
            raise McpGatewayError(
                "auto_approve=True exige allow_write=True: não faz sentido "
                "auto-aprovar operações destrutivas que nem são expostas."
            )
        self._controller = controller
        self._allow_write = allow_write
        self._auto_approve = auto_approve
        self._max_auto_approvals = max_auto_approvals

    # ------------------------------------------------------------- exposição
    @property
    def allow_write(self) -> bool:
        return self._allow_write

    @property
    def auto_approve(self) -> bool:
        return self._auto_approve

    def definitions(self) -> tuple[ToolDefinition, ...]:
        """As ``ToolDefinition`` que este gateway expõe ao cliente MCP."""
        protocol = self._controller.tool_protocol()
        if self._allow_write:
            return protocol.definitions
        return tuple(d for d in protocol.definitions if not d.destructive)

    def definition_for(self, name: str) -> ToolDefinition | None:
        for definition in self.definitions():
            if definition.name == name:
                return definition
        return None

    def exposed_names(self) -> set[str]:
        return {d.name for d in self.definitions()}

    # -------------------------------------------------------------- execução
    def call(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        call_id: str = "",
        on_checkpoint: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> ToolCallOutcome:
        """Executa uma tool respeitando o porteio de permissões do LUMEN.

        Nunca levanta por falha de *conteúdo* (tool bloqueada, permissão
        negada, argumento inválido): devolve ``ok=False`` com a mensagem
        amigável do LUMEN, que é o que o LLM precisa ler para se corrigir.
        Levanta apenas para erro de programação (nome fora da exposição).
        """
        if self.definition_for(name) is None:
            # Defesa em profundidade: mesmo que o cliente chame algo fora do
            # `tools/list`, o gateway revalida antes de encostar no controller.
            raise McpGatewayError(
                f"Ferramenta {name!r} não está exposta por este servidor MCP."
            )

        call = ToolCall(tool=name, parameters=dict(arguments or {}), call_id=call_id)

        try:
            result = self._controller.run_tool_call(call)
        except ToolProtocolError as exc:
            # Argumento inválido/desconhecido ou tool fora do contrato: é erro
            # do cliente, não do servidor. Vira conteúdo legível, não exceção.
            return ToolCallOutcome(
                ok=False,
                text=f"Chamada inválida para {name!r}: {exc}",
                structured={"tool": name, "error": str(exc)},
            )
        except Exception as exc:  # pragma: no cover - salvaguarda
            logger.exception("Falha inesperada ao executar %s via MCP.", name)
            return ToolCallOutcome(
                ok=False,
                text=f"Falha interna ao executar {name!r}: {exc}",
                structured={"tool": name, "error": str(exc)},
            )

        data = dict(result.data or {})
        if result.ok:
            return ToolCallOutcome(
                ok=True,
                text=_summarize_success(name, data),
                structured={"tool": name, "ok": True, **_public_view(data)},
            )

        if data.get("awaiting_approval"):
            checkpoint = self._controller.pending_approval() or {}
            checkpoint_id = str(checkpoint.get("checkpoint_id") or "?")
            if on_checkpoint is not None:
                on_checkpoint(checkpoint)
            if self._auto_approve:
                return self._resolve_checkpoints(
                    name, call_id=call_id, first_checkpoint=checkpoint
                )
            return ToolCallOutcome(
                ok=False,
                awaiting_approval=True,
                text=CHECKPOINT_PENDING_MESSAGE.format(checkpoint_id=checkpoint_id),
                structured={
                    "tool": name,
                    "awaiting_approval": True,
                    "checkpoint_id": checkpoint_id,
                    "checkpoint": dict(checkpoint),
                },
            )

        return ToolCallOutcome(
            ok=False,
            text=f"❌ {result.error or 'a execução falhou.'}",
            structured={"tool": name, "error": result.error, **_public_view(data)},
        )

    # ------------------------------------------------------------ internos
    def _resolve_checkpoints(
        self, name: str, *, call_id: str, first_checkpoint: Mapping[str, Any]
    ) -> ToolCallOutcome:
        """Aprova os checkpoints pendentes quando o operador autorizou.

        O laço é limitado: cada aprovação pode revelar a próxima operação
        destrutiva. O teto evita que um plano inesperadamente longo rode
        para sempre sob autorização ampla.
        """
        checkpoint = first_checkpoint
        last_report: Any = None
        approvals = 0
        logger.warning(
            "MCP auto_approve: aprovando checkpoint %s de %s (autorização prévia "
            "do operador).",
            checkpoint.get("checkpoint_id"),
            name,
        )
        while checkpoint and approvals < self._max_auto_approvals:
            checkpoint_id = str(checkpoint.get("checkpoint_id") or "?")
            last_report = self._controller.approve(
                note=f"auto-aprovado pelo servidor MCP (tool {name}, {checkpoint_id})"
            )
            approvals += 1
            checkpoint = self._controller.pending_approval()

        if approvals >= self._max_auto_approvals and checkpoint:
            return ToolCallOutcome(
                ok=False,
                awaiting_approval=True,
                text=(
                    f"⏸ Limite de {self._max_auto_approvals} auto-aprovações atingido; "
                    f"ainda há checkpoint pendente "
                    f"({checkpoint.get('checkpoint_id')}). Nada mais foi executado."
                ),
                structured={
                    "tool": name,
                    "awaiting_approval": True,
                    "auto_approvals": approvals,
                    "checkpoint": dict(checkpoint),
                },
            )

        tasks = getattr(last_report, "tasks", ()) or ()
        # Comparar com o enum, não com string literal: `PlannedTaskStatus.DONE`
        # tem valor "DONE" (maiúsculo) e um literal minúsculo passaria batido,
        # reportando falha depois de escrever no disco com sucesso.
        from app.planner.models import PlannedTaskStatus

        failed = [t for t in tasks if getattr(t, "status", None) is not PlannedTaskStatus.DONE]
        payload = {
            "tool": name,
            "auto_approvals": approvals,
            "execution_report": last_report.to_dict() if hasattr(last_report, "to_dict") else None,
        }
        if failed:
            first_error = getattr(failed[0], "error", None) or "falha na execução"
            return ToolCallOutcome(
                ok=False,
                text=f"❌ {first_error}",
                structured={**payload, "error": first_error},
            )
        if last_report is None:
            error = "nenhum relatório de execução foi produzido"
            return ToolCallOutcome(
                ok=False, text=f"❌ {error}", structured={**payload, "error": error}
            )
        result = _task_result(last_report)
        if isinstance(result, dict):
            inner = result.get("data") if result.get("ok") else None
            summary = _compact(inner if isinstance(inner, dict) else result)
        else:
            summary = (
                f"executado ({approvals} operação(ões) aprovada(s) pela "
                "autorização prévia do operador)"
            )
        return ToolCallOutcome(
            ok=True,
            text=f"✅ {name}: {summary}",
            structured={**payload, "ok": True},
        )


def _decode(value: Any) -> Any:
    """``StructuredTool`` entrega o ``ToolResult`` como JSON **string**.

    Sem decodificar, o LLM recebe uma string escapada e o resumo vira
    "✅ read_file executado." sem o conteúdo lido.
    """
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in "{[" and stripped[-1:] in "}]":
            try:
                import json

                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def _task_result(report: Any) -> Any:
    """Resultado da primeira tarefa do relatório, já decodificado."""
    for task in getattr(report, "tasks", ()) or ():
        if getattr(task, "result", None) is not None:
            return _decode(task.result)
    return None


def _public_view(data: Mapping[str, Any]) -> dict[str, Any]:
    """Remove o relatório bruto (verboso) e mantém o essencial para o LLM."""
    view = {k: v for k, v in data.items() if k != "execution_report"}
    report = data.get("execution_report")
    if isinstance(report, dict):
        view["plan_id"] = report.get("plan_id")
        view["status"] = report.get("status")
        tasks = report.get("tasks") or []
        if tasks and isinstance(tasks[0], dict):
            view["result"] = _decode(tasks[0].get("result"))
            view["task_error"] = tasks[0].get("error")
    return view


def _summarize_success(name: str, data: Mapping[str, Any]) -> str:
    """Mensagem curta e útil para o LLM (o JSON completo vai em structured)."""
    report = data.get("execution_report")
    result: Any = None
    if isinstance(report, dict):
        tasks = report.get("tasks") or []
        if tasks and isinstance(tasks[0], dict):
            result = _decode(tasks[0].get("result"))
    if isinstance(result, dict) and result.get("ok") is not None:
        # ToolResult serializado (StructuredTool.run devolve JSON)
        inner = result.get("data") if result.get("ok") else None
        if isinstance(inner, dict):
            return f"✅ {name}: {_compact(inner)}"
    if isinstance(result, dict):
        return f"✅ {name}: {_compact(result)}"
    return f"✅ {name} executado."


def _compact(payload: Mapping[str, Any], limit: int = 400) -> str:
    import json

    text = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
    return text if len(text) <= limit else text[: limit - 1] + "…"


__all__ = [
    "CHECKPOINT_PENDING_MESSAGE",
    "ControllerToolGateway",
    "McpGatewayError",
    "ToolCallOutcome",
]
