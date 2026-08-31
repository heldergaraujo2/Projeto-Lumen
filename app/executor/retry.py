"""Política de retry controlado (Lumen 0.4.x — fundação).

Retry **por tarefa**, com limite estrito (nunca infinito) e registro de
cada tentativa (:class:`AttemptRecord`): número, resultado e erro.

O backoff é real (``time.sleep`` por padrão) mas **injetável** — os
testes registram os atrasos sem dormir, mantendo a suíte rápida e
determinística.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Limites de tentativa por tarefa.

    Args:
        max_attempts: total de tentativas **por tarefa** (≥1, incluindo
            a primeira) — garantia matemática contra retry infinito.
        backoff_seconds: atraso antes da tentativa ``n``-ésima
            (linear: ``backoff × tentativa``); ``0`` = sem espera.
    """

    max_attempts: int = 1
    backoff_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool):
            raise ValueError("max_attempts deve ser um inteiro.")
        if self.max_attempts < 1:
            raise ValueError("max_attempts deve ser >= 1 (sem retry infinito).")
        if not isinstance(self.backoff_seconds, (int, float)) or self.backoff_seconds < 0:
            raise ValueError("backoff_seconds deve ser um número >= 0.")

    @property
    def retries(self) -> int:
        """Tentativas EXTRA além da primeira."""
        return self.max_attempts - 1


@dataclass(frozen=True)
class AttemptRecord:
    """Resultado de UMA tentativa de execução de uma tarefa."""

    number: int  # 1-based
    result: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict:
        return {"number": self.number, "result": self.result, "error": self.error}
