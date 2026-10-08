"""Camada de capacidades de modelo (antes vivia em ``app.evolution``).

Extraída para ``app/ai`` na Fase 0 da limpeza: ``StackLayer`` é usada por
:mod:`app.ai.provider_runtime` (camada viva), mas o pacote ``app.evolution``
era código inalcançável a partir da aplicação. Mover a enum quebra a
dependência invertida de ``app/ai`` para código morto.

Nenhuma semântica foi alterada — apenas o endereço do símbolo.
"""
from __future__ import annotations

from enum import Enum


class StackLayer(str, Enum):
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    VISION = "vision"
    CODING = "coding"
    RESEARCH = "research"
    PLANNING = "planning"


__all__ = ["StackLayer"]
