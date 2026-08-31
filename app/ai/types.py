"""Tipos da camada de IA da Lumen — independentes de provedor.

0.2: normalização de resposta (`AIResponse`/`Usage`) para que nem o Agent
Core nem a UI dependam do formato de uma API específica, e preparação
para o futuro de Agent (`ResponseType`: FINAL_RESPONSE | TOOL_CALL |
PLAN) sem implementar tool calling real nesta versão.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ResponseType(str, Enum):
    """Natureza de uma resposta do modelo.

    Fase 0.2: todo provedor retorna apenas ``FINAL_RESPONSE``. Os demais
    valores existem para que versões futuras (Planner/Tool Calling, 0.4+)
    evoluam **sem reescrever o Agent Core**.
    """

    FINAL_RESPONSE = "FINAL_RESPONSE"
    TOOL_CALL = "TOOL_CALL"
    PLAN = "PLAN"


@dataclass(frozen=True)
class Usage:
    """Uso de tokens reportado pelo provedor (quando disponível)."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class AIResponse:
    """Resposta normalizada de um provedor de IA.

    Atributos:
        content: texto da resposta (vazio somente em chamadas de tool
            futuras; nesta versão sempre há texto).
        model: identificador do modelo que respondeu (ex.: ``gpt-4o-mini``).
        usage: contadores de tokens, se o provedor informar.
        finish_reason: motivo do término (``stop``, ``length``, …).
        response_type: nesta versão, sempre ``FINAL_RESPONSE``.
        tool_calls: reservado para 0.4+ (tool calling) — sempre vazio na
            0.2; existe apenas como estrutura preparatória.
    """

    content: str
    model: str = ""
    usage: Usage | None = None
    finish_reason: str = ""
    response_type: ResponseType = ResponseType.FINAL_RESPONSE
    tool_calls: tuple = ()

    def __str__(self) -> str:
        return self.content
