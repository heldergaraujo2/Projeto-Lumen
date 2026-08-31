"""Handlers de execução do Executor de Planos (Lumen 0.4.x — fundação).

Um :class:`TaskHandler` é a **costura** entre o Executor e o mundo:
hoje existe apenas o :class:`SimulatedHandler` — determinístico, em
memória, **sem nenhum efeito no computador**. Ferramentas reais
(filesystem, terminal, …) chegarão em versões futuras (0.5+) como novos
``TaskHandler`` implementados sobre o :class:`~app.tools.base.ToolRegistry`
(porteiro de permissões) — o núcleo do Executor não mudará.

NADA neste módulo executa comandos, toca arquivos, terminal, mouse,
teclado, tela ou Unreal.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from app.planner.models import PlannedTask


class HandlerError(RuntimeError):
    """Falha de um handler ao "executar" uma tarefa (motivo na mensagem)."""


class TaskHandler(ABC):
    """Contrato de execução de uma tarefa planejada.

    Futuro (0.5+): implementações reais envelopam ferramentas do
    ``ToolRegistry`` (que continua bloqueando execução sem permissão).
    Esta etapa possui somente a implementação simulada abaixo.
    """

    name: str = "handler"

    @abstractmethod
    def execute(
        self, task: PlannedTask, *,
        parameters: Mapping[str, Any] | None = None,
    ) -> str:
        # ``parameters`` (data-flow 8B): parâmetros JÁ resolvidos pelo
        # Executor quando o chamador os possui; ``None`` usa os da task
        # (o Executor também grava os resolvidos na própria tarefa).
        """"Executa" a tarefa e devolve o resultado textual.

        Raises:
            HandlerError: se a tarefa não pôde ser concluída (o Executor
                marca a tarefa como FAILED e interrompe o plano).
        """
        raise HandlerError("TaskHandler.execute não implementado")  # pragma: no cover


class SimulatedHandler(TaskHandler):
    """Handler SIMULADO (in-memory) — prova de conceito do mecanismo.

    Determinístico: devolve o resultado programado para cada tarefa (ou
    um texto padrão) e falha exatamente para os ids informados. Não
    executa nada real — existe apenas para exercitar o Executor e seus
    testes.

    Args:
        results: mapa ``task_id → texto de resultado`` (opcional).
        failures: mapa ``task_id → motivo da falha`` (opcional); ids
            presentes aqui falham sempre, com o motivo informado.
        default_result: texto devolvido para tarefas sem resultado
            programado (padrão: ``"Simulado: <descrição>"``).
    """

    name = "simulated"

    def __init__(
        self,
        results: Mapping[str, str] | None = None,
        failures: Mapping[str, str] | None = None,
        default_result: str | None = None,
    ) -> None:
        self._results = dict(results or {})
        self._failures = dict(failures or {})
        self._default_result = default_result
        self.executed: list[str] = []  # ids na ordem em que rodaram (testes)

    def execute(
        self, task: PlannedTask, *,
        parameters: Mapping[str, Any] | None = None,
    ) -> str:
        # ``parameters`` (resolvidos, 8B) tem precedência quando fornecido;
        # o simulado não os consome — assinatura preparada, lógica intacta.
        self.executed.append(task.id)
        if task.id in self._failures:
            raise HandlerError(self._failures[task.id])
        if task.id in self._results:
            return self._results[task.id]
        if self._default_result is not None:
            return self._default_result
        return f"Simulado: {task.description}"
