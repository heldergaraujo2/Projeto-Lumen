"""Verificação de resultados (Lumen 0.4.x — fundação).

Depois que uma tarefa **executa** com sucesso, um :class:`TaskVerifier`
pode conferir se o resultado realmente funcionou:

    EXECUTOU → VERIFICOU → SUCESSO   (``DONE`` + ``verified=True``)
    EXECUTOU → VERIFICOU → FALHOU    (``REJECTED`` + ``verified=False``)

Nesta fundação existe apenas o :class:`SimulatedVerifier`
(determinístico, in-memory). Verificadores reais (0.5+: conferir
arquivos, compilação, logs…) entrarão como novas implementações da
mesma interface — o Executor não muda.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from app.planner.models import PlannedTask


@dataclass(frozen=True)
class VerificationResult:
    """Desfecho de uma verificação."""

    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {"passed": self.passed, "detail": self.detail}


class TaskVerifier(ABC):
    """Contrato de verificação do resultado de uma tarefa."""

    name: str = "verifier"

    @abstractmethod
    def verify(self, task: PlannedTask, result: str) -> VerificationResult:
        """Confere o ``result`` da ``task`` e devolve o desfecho."""
        raise NotImplementedError  # pragma: no cover


class SimulatedVerifier(TaskVerifier):
    """Verificador SIMULADO (in-memory) — prova de conceito.

    Determinístico: reprova exatamente os ids mapeados em ``failures``
    (com o motivo informado) e aprova os demais.
    """

    name = "simulated"

    def __init__(self, failures: Mapping[str, str] | None = None) -> None:
        self._failures = dict(failures or {})

    def verify(self, task: PlannedTask, result: str) -> VerificationResult:
        if task.id in self._failures:
            return VerificationResult(False, self._failures[task.id])
        return VerificationResult(True, "verificado (simulado)")
