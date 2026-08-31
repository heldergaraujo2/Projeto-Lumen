"""Verificação de resultados (Lumen 0.4.x — fundação).

Depois que uma tarefa **executa** com sucesso, um :class:`TaskVerifier`
pode conferir se o resultado realmente funcionou:

    EXECUTOU → VERIFICOU → SUCESSO   (``DONE`` + ``verified=True``)
    EXECUTOU → VERIFICOU → FALHOU    (``REJECTED`` + ``verified=False``)

Nesta fundação existe o :class:`SimulatedVerifier` (determinístico,
in-memory) e, desde a 11E, o :class:`PytestResultVerifier` —
**interpretador** do resultado estruturado da tool ``run_pytest``
(**NÃO executa nada**: a execução é sempre uma task do plano, com
permissão ``TERMINAL`` + checkpoint — ver
``docs/SPEC-11E-REAL_VERIFICATION.md`` §3). O Executor não muda.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from app.planner.models import PlannedTask


@dataclass(frozen=True)
class VerificationResult:
    """Desfecho de uma verificação.

    ``applied`` (11E): ``False`` marca verificação **não aplicável** à
    tarefa (ex.: tool diferente de ``run_pytest``) — a tarefa não foi
    reprovada; apenas não há evidência para conferir.
    Compatibilidade: ``VerificationResult(passed, detail)`` continua
    válido e :meth:`to_dict` mantém o contrato 0.4.x (não expõe
    ``applied``).
    """

    passed: bool
    detail: str = ""
    applied: bool = True

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


class PytestResultVerifier(TaskVerifier):
    """Verificador **interpretador** do resultado de ``run_pytest`` (11E).

    **NÃO executa nada** — não importa ``subprocess``, não chama
    terminal/shell, não tem efeito colateral (princípio normativo da
    spec 11E §3): apenas interpreta o JSON ``ToolResult`` já produzido
    pela task ``run_pytest`` (que, quando roda, é uma task normal do
    plano com permissão ``TERMINAL`` + checkpoint obrigatório).

    Semântica:

    - task de outra tool ⇒ ``passed=True, detail="not applicable",
      applied=False`` (não aplicável — sem rejeição decorativa);
    - ``run_pytest``: ``passed = (data.exit_code == 0)`` com
      ``detail = data.summary_line`` (fallback: ``exit_code=…``);
      ``data.timed_out`` ⇒ ``passed=False, detail="timed out"``;
    - resultado inválido (JSON ausente/inválido, ``ok != True``,
      campos ausentes) ⇒ ``passed=False`` com motivo claro — falha
      honesta, nunca aprovação silenciosa.
    """

    name = "pytest_result"

    def verify(self, task: PlannedTask, result: str) -> VerificationResult:
        if task.tool != "run_pytest":
            return VerificationResult(True, "not applicable", applied=False)

        try:
            payload = json.loads(result)
        except (TypeError, ValueError):
            return VerificationResult(False, "invalid tool result json")
        if not isinstance(payload, dict):
            return VerificationResult(False, "invalid tool result json")
        if payload.get("ok") is not True:
            return VerificationResult(
                False,
                str(payload.get("error") or "tool result reported failure"),
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            return VerificationResult(
                False, "invalid tool result: missing 'data' object"
            )
        if data.get("timed_out") is True:
            return VerificationResult(False, "timed out")
        exit_code = data.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            return VerificationResult(
                False, "invalid tool result: missing/invalid 'exit_code'"
            )
        summary = data.get("summary_line")
        detail = (
            summary
            if isinstance(summary, str) and summary
            else f"exit_code={exit_code}"
        )
        return VerificationResult(exit_code == 0, detail)
