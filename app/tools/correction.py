"""Estratégia de correção para as ferramentas autorizadas (0.6.2).

Implementa :class:`~app.executor.correction.CorrectionStrategy` para as
ferramentas JÁ autorizadas (filesystem 0.5 / terminal 0.6), de forma
**conservadora e controlada**:

- propõe apenas ajustes equivalentes e seguros (ex.: trocar
  ``create_file`` por ``write_file`` quando o arquivo já existe e a
  intenção era gravar);
- **nunca** propõe bypass: erros de permissão, allowlist, política de
  workspace, delete sem opt-in, operadores proibidos etc. não geram
  proposta (a falha permanece falha — honesta);
- toda proposta carrega a tarefa corrigida e exige aprovação explícita
  (``requires_approval=True``) — nada é aplicado sozinho.

O :func:`build_proposal_validator` valida a proposta contra o sistema
de permissões/política vigentes (registry + sandbox + política de
terminal) **antes** de qualquer aplicação — correção inválida nunca roda
(a engine registra ``INVALID`` e encerra).
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from app.executor.correction import (
    CorrectionProposal,
    CorrectionStrategy,
)
from app.executor.executor import TaskRun
from app.planner.models import PlannedTask
from app.security.permissions import PermissionManager
from app.tools.base import ToolRegistry
from app.tools.filesystem import FilesystemError, WorkspaceSandbox
from app.tools.terminal import TerminalPolicy, TerminalSecurityError

logger = logging.getLogger("lumen.tools.correction")

#: Marcadores de erro que JAMAIS geram proposta (segurança/política).
_SECURITY_MARKERS: tuple[str, ...] = (
    "permissão negada",           # gate do ToolRegistry
    "allowlist",                  # terminal fora da lista
    "proibido",                   # denylist permanente
    "somente leitura",            # política de workspace
    "allow_delete",               # exclusão sem opt-in
    "fora do workspace",          # confinamento
    "traversal",                  # ..
    "operador",                   # shell/redirecionamento
    "permitida a execução arbitrária",
)


def _is_security_error(error: str | None) -> bool:
    if not error:
        return False
    lowered = error.lower()
    return any(marker in lowered for marker in _SECURITY_MARKERS)


class ToolCorrectionStrategy(CorrectionStrategy):
    """Correção conservadora das ferramentas autorizadas (0.6.2).

    Regras (todas exigem aprovação explícita; nenhuma contorna política):

    - ``create_file`` falhou porque **o arquivo já existe** → propor
      ``write_file`` com os mesmos parâmetros (gravar por cima é a
      intenção evidente); o usuário decide.
    - Qualquer falha de segurança/política (permissão, allowlist,
      somente leitura, delete sem opt-in, fora do workspace, operadores)
      → **sem proposta** (falha honesta; correção nunca é bypass).
    - Qualquer outro erro → **sem proposta** (a estratégia não inventa).
    """

    def propose_correction(
        self, task: PlannedTask, run: TaskRun
    ) -> CorrectionProposal | None:
        if task.tool is None:
            return None
        error = run.error or ""
        if _is_security_error(error):
            logger.info(
                "Falha de segurança/política em %s: correção automática "
                "recusada por princípio (nenhuma proposta).", task.id,
            )
            return None
        if task.tool == "create_file" and "já existe" in error.lower():
            corrected = PlannedTask(
                id=task.id,
                description=f"{task.description} [corrigido: gravar por cima]",
                order=task.order,
                dependencies=task.dependencies,
                tool="write_file",
                parameters=dict(task.parameters or {}),
            )
            return CorrectionProposal(
                suggestion=(
                    "O arquivo já existe e create_file não sobrescreve — "
                    "usar write_file para gravar por cima (mesmo conteúdo)."
                ),
                detail=f"Falha original: {error}",
                corrected_task=corrected,
                requires_approval=True,
            )
        return None


class EvidenceCorrectionStrategy(CorrectionStrategy):
    """11J (MVP): conselho com evidência real para ``run_pytest`` (advice-only).

    Quando a task ``run_pytest`` falha (REJECTED/FAILED), parseia o JSON
    ``ToolResult`` de ``run.result`` e enriquece o conselho do ciclo com a
    evidência executada (``exit_code``, ``summary_line``, ``timed_out``,
    ``truncated``) — **sem** propor tarefa corrigida
    (``corrected_task=None``): a engine registra o conselho e encerra o
    ciclo (nada é aplicado, sem pausa, sem card). Demais casos delegam à
    estratégia base (comportamento conservador 0.6.2; erros de
    segurança/política continuam sem proposta).
    """

    def __init__(self, base: CorrectionStrategy) -> None:
        self._base = base

    def propose_correction(
        self, task: PlannedTask, run: TaskRun
    ) -> CorrectionProposal | None:
        if task.tool is None:
            return None
        # Erro de segurança/política: delega à base (conservadora → None).
        if _is_security_error(run.error):
            return self._base.propose_correction(task, run)
        if task.tool == "run_pytest":
            return self._pytest_advice(run)
        return self._base.propose_correction(task, run)

    def _pytest_advice(self, run: TaskRun) -> CorrectionProposal:
        """Evidência do ``run.result`` (JSON ToolResult) → conselho 11J."""
        try:
            payload = json.loads(run.result)
            if not isinstance(payload, dict):
                raise ValueError("resultado não é um objeto JSON")
            data = payload.get("data")
            if not isinstance(data, dict):
                raise ValueError("resultado sem objeto 'data'")
            exit_code = data.get("exit_code")
            summary = str(data.get("summary_line") or "").strip()
            timed_out = bool(data.get("timed_out"))
            truncated = bool(data.get("truncated"))
            headline = summary or f"exit_code={exit_code}"
            return CorrectionProposal(
                suggestion=f"pytest falhou: {headline}",
                detail=(
                    f"exit_code={exit_code} timed_out={timed_out} "
                    f"truncated={truncated}. Próximo passo: inspecionar a "
                    "saída dos testes que falharam (resumo acima) e "
                    "ajustar a suíte antes de re-executar o pytest."
                ),
                corrected_task=None,
                requires_approval=False,
            )
        except (TypeError, ValueError) as exc:
            return CorrectionProposal(
                suggestion="pytest falhou (resultado inválido)",
                detail=f"Não foi possível extrair evidência do run.result: {exc}",
                corrected_task=None,
                requires_approval=False,
            )


def build_proposal_validator(
    registry: ToolRegistry,
    permissions: PermissionManager,
    sandbox: WorkspaceSandbox,
    terminal_policy: TerminalPolicy | None = None,
) -> Callable[[PlannedTask], str | None]:
    """Validador de viabilidade da tarefa corrigida (antes de aplicar).

    Devolve ``None`` quando a correção pode rodar sob as regras atuais,
    ou o **motivo** do bloqueio (a engine marca ``INVALID`` e não aplica):

    - ferramenta precisa estar registrada;
    - permissão exigida precisa estar concedida (gate do registry);
    - filesystem: caminho resolve dentro do workspace e a operação passa
      na política (``check_operation``);
    - terminal: comando/argumentos/cwd passam na ``TerminalPolicy``.
    """

    def validate(task: PlannedTask) -> str | None:
        if not task.tool:
            return "Tarefa corrigida sem ferramenta designada."
        try:
            tool = registry.get(task.tool)
        except Exception:
            return f"Ferramenta não registrada: {task.tool!r}."
        if not permissions.is_granted(tool.required_permission):
            return (
                f"Permissão {tool.required_permission.name} não concedida — "
                "a correção não pode executar."
            )
        parameters = dict(task.parameters or {})
        if task.tool == "run_command":
            if terminal_policy is None:
                return "Terminal não habilitado — comando não pode executar."
            try:
                terminal_policy.validate(
                    parameters.get("command"),
                    parameters.get("args", []),
                    parameters.get("cwd"),
                    sandbox,
                )
            except TerminalSecurityError as exc:
                return f"Correção viola a política de terminal: {exc}"
            return None
        requested = parameters.get("path")
        if not isinstance(requested, str) or not requested.strip():
            return "Correção sem caminho utilizável."
        try:
            resolved = sandbox.resolve(requested)
            operation = getattr(tool, "operation", "read")
            sandbox.check_operation(operation, resolved)
        except FilesystemError as exc:
            return f"Correção viola a política de workspace: {exc}"
        except Exception as exc:  # defensivo: nunca aplica no escuro
            return f"Correção inválida: {exc}"
        return None

    return validate
