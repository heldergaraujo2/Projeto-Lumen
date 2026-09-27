"""Camada de controle das ferramentas (0.5.x).

:class:`ToolsController` é a **única porta** da UI para workspaces,
permissões, execução com checkpoints e auditoria — toda a lógica vive
aqui (testável sem Tk); os diálogos são apenas apresentação.

Garantias:

- permissões: somente ``CHAT``/``READ``/``WRITE`` são gerenciáveis —
  ``TERMINAL``/``COMPUTER_CONTROL`` são **rejeitados** (nada de concessão
  silenciosa de níveis futuros) e ``DELETE`` não é um nível: é o opt-in
  por workspace (``writable`` + ``allow_delete``) da 0.5;
- execução: ``run_plan`` constrói a cadeia real
  ``ToolTaskHandler → ToolRegistry → ferramentas`` com
  ``ToolCheckpoints`` nas ferramentas destrutivas — a operação fica
  **realmente bloqueada** até :meth:`approve`; :meth:`refuse` garante que
  nada roda;
- auditoria: toda tentativa vai para a trilha (memória + JSONL via
  sink), **sem conteúdo de arquivos**;
- nada é executado ou persistido no startup — o controller só age quando
  chamado (workspaces vazios ⇒ tudo bloqueado).
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.executor.correction import (
    CorrectionCycle,
    CorrectionEngine,
    CorrectionStrategy,
)
from app.executor.executor import PlanExecutor
from app.executor.executor import ExecutionEvent, ExecutionReport, TaskRun
from app.executor.verification import TaskVerifier
from app.memory.execution_store import ExecutionBundleStore
from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus
from app.security.permissions import PermissionLevel, PermissionManager
from app.tools.audit_log import JsonlAuditSink, read_audit_tail
from app.tools.base import ToolRegistry
from app.tools.filesystem import (
    FILESYSTEM_DESTRUCTIVE_TOOLS,
    OPERATION_DELETE,
    OPERATION_WRITE,
    FilesystemAudit,
    FilesystemError,
    build_filesystem_registry,
)
from app.tools.handler import ToolCheckpoints, ToolTaskHandler
from app.tools.snapshot_store import SnapshotStore
from app.tools.terminal import (
    TERMINAL_TOOL_NAME,
    AllowedCommand,
    PrevalidatedTerminalCheckpoints,
    RunCommandTool,
    TerminalPolicy,
    TerminalSecurityError,
    TerminalStore,
    TerminalStoreError,
)
from app.tools.report_export import (
    build_export_payload,
    export_execution_report,
)
from app.tools.toggles_store import ToggleStore, ToggleStoreError
from app.tools.correction import (
    EvidenceCorrectionStrategy,
    ToolCorrectionStrategy,
    build_proposal_validator,
)
from app.tools.workspaces import MultiWorkspaceSandbox, WorkspaceStore

logger = logging.getLogger("lumen.tools.control")

#: Rótulos humanos das operações (UX de aprovação/auditoria).
OPERATION_LABELS = {
    "read": "leitura",
    "write": "escrita",
    "delete": "exclusão",
    "permission_gate": "verificação de permissão",
    "run_command": "execução de comando",
    "terminal_grant": "concessão de TERMINAL",
    "terminal_revoke": "revogação de TERMINAL",
    "cc_grant": "concessão de COMPUTER_CONTROL",
    "cc_revoke": "revogação de COMPUTER_CONTROL",
    "terminal_enable": "habilitação do terminal",
    "terminal_disable": "desabilitação do terminal",
    "allowlist_add": "comando allowlistado",
    "allowlist_remove": "comando removido da allowlist",
    "correction_proposed": "correção proposta",
    "correction_invalid": "correção inválida (bloqueada)",
    "correction_refused": "correção recusada",
    "correction_approved": "correção aprovada",
    "correction_applied": "correção aplicada",
    "correction_retried": "nova tentativa",
    "correction_succeeded": "sucesso após correção",
    "correction_failed": "falha definitiva",
    "correction_no_proposal": "sem proposta de correção",
    "correction_exhausted": "limite de correções atingido",
}

#: Níveis gerenciáveis pela UI (DELETE é opt-in de workspace, não nível).
MANAGEABLE_LEVELS = (PermissionLevel.CHAT, PermissionLevel.READ, PermissionLevel.WRITE)

#: 11F — tools contadas como WRITE para o auto-anexo de ``run_pytest``.
_AUTO_PYTEST_WRITE_TOOLS = frozenset({
    "write_file",
    "create_file",
    "delete_file",
    "edit_file",
})

#: 11F — espelha ``PlannerLimits.max_tasks`` (``app/planner/planner.py``):
#: anexo necessário com plano no limite NÃO excede o teto silenciosamente —
#: falha **antes de executar** (tudo SKIPPED, motivo claro).
_AUTO_PYTEST_MAX_TASKS = 12


def _needs_auto_pytest(
    plan: Plan, *, terminal_enabled: bool, verification_enabled: bool
) -> bool:
    """11F — decisão pura: anexar task final ``run_pytest``?

    Somente quando (a) terminal habilitado, (b) verificação 11E
    habilitada, (c) o plano tem ao menos 1 WRITE (MVP: as 4 tools de
    filesystem) e (d) o plano ainda não contém ``run_pytest``
    (idempotência — 1 por plano).
    """
    if not terminal_enabled or not verification_enabled:
        return False
    if any(task.tool == "run_pytest" for task in plan.tasks):
        return False
    return any(task.tool in _AUTO_PYTEST_WRITE_TOOLS for task in plan.tasks)


def _attach_run_pytest(plan: Plan) -> Plan:
    """11F — pura: devolve novo plano com a task final ``run_pytest``.

    O plano original não é alterado (``Plan`` é frozen — ``replace``).
    A task anexada depende de **todas** as tasks existentes (executa
    por último), com id defensivo (``T{n+1}``, incrementado se
    colidir) e parâmetros estáticos, sem dataflow.
    """
    tasks = list(plan.tasks)
    used_ids = {task.id for task in tasks}
    order = len(tasks) + 1
    while f"T{order}" in used_ids:
        order += 1
    new_task = PlannedTask(
        id=f"T{order}",
        description="11F: run_pytest após WRITE",
        order=order,
        dependencies=tuple(task.id for task in tasks),
        tool="run_pytest",
        parameters={"path": "tests"},
    )
    return replace(plan, tasks=tuple(tasks + [new_task]))


def _auto_pytest_limit_report(plan: Plan) -> ExecutionReport:
    """11F — relatório do guardrail: anexo necessário e plano no limite.

    Coerente com o fail-fast do executor: todas as tasks ``SKIPPED``,
    plano ``FAILED``, **nada** executado (sem chamadas de tool, sem
    checkpoints).
    """
    reason = (
        "Auto-verificação (11F) requer 1 task extra (run_pytest), mas "
        f"o plano já tem {len(plan.tasks)} tasks (máximo "
        f"{_AUTO_PYTEST_MAX_TASKS}) — nada foi executado."
    )
    tasks = tuple(
        TaskRun(
            id=task.id,
            description=task.description,
            order=task.order,
            dependencies=task.dependencies,
            status=PlannedTaskStatus.SKIPPED,
            error="Pulada: guardrail 11F (plano no limite de tasks).",
        )
        for task in plan.tasks
    )
    events: list[ExecutionEvent] = [
        ExecutionEvent("task_skipped", task.id) for task in plan.tasks
    ]
    events.append(ExecutionEvent("plan_finished", None, PlanStatus.FAILED.value))
    return ExecutionReport(
        plan_id=plan.id,
        objective=plan.objective,
        status=PlanStatus.FAILED,
        tasks=tasks,
        events=tuple(events),
        error=reason,
    )


class ToolsControlError(RuntimeError):
    """Uso incorreto da camada de controle (mensagem amigável)."""


class PrevalidatedCheckpoints(ToolCheckpoints):
    """Checkpoint apenas quando a operação é **viável**.

    Não interroga o usuário sobre algo que falharia de qualquer forma:
    exige checkpoint somente se (1) a ferramenta é destrutiva, (2) a
    permissão exigida **está concedida** e (3) o caminho/operacao
    **passa** na política do sandbox (resolve + check_operation). Caso
    contrário, a tarefa roda no handler e falha com o motivo real
    (permissão/política/caminho) — bloqueio honesto, sem aprovação
    decorativa.
    """

    def __init__(self, permissions: PermissionManager, registry: ToolRegistry,
                 sandbox: MultiWorkspaceSandbox,
                 snapshots_dir: Path | None = None) -> None:
        super().__init__(FILESYSTEM_DESTRUCTIVE_TOOLS)
        self._permissions = permissions
        self._registry = registry
        self._sandbox = sandbox
        # 11K: raiz de snapshots para pré-validar restore_snapshot
        # (evitar aprovação decorativa).
        self._snapshots_dir = snapshots_dir
        self._snapshot_store = (
            SnapshotStore(snapshots_dir) if snapshots_dir is not None else None
        )

    def requires_checkpoint(self, task) -> bool:  # type: ignore[override]
        if task.tool == "restore_snapshot":
            # 11K: destrutiva, mas o parâmetro não é "path" — a viabilidade
            # vem do manifest do snapshot (pré-validada; sem aprovação
            # decorativa para algo que falharia de qualquer forma).
            return self._restore_snapshot_viable(task)
        if not super().requires_checkpoint(task):
            return False
        if not task.tool:
            return False
        try:
            tool = self._registry.get(task.tool)
        except Exception:
            return False  # ferramenta desconhecida: falha controlada no handler
        if not self._permissions.is_granted(tool.required_permission):
            return False  # sem permissão: o handler bloqueia de verdade
        parameters = dict(task.parameters or {})
        requested = parameters.get("path")
        if not isinstance(requested, str) or not requested.strip():
            return False  # sem caminho utilizável: falha controlada no handler
        try:
            resolved = self._sandbox.resolve(requested)
            self._sandbox.check_operation(tool.operation, resolved)
        except FilesystemError:
            return False  # fora do workspace/política: falha controlada
        return True

    def _restore_snapshot_viable(self, task) -> bool:
        """11K: ``restore_snapshot`` é **viável**? (sem aprovação decorativa).

        Pausa apenas quando o restore de fato executaria: (1) ``WRITE``
        concedida (gate da tool), (2) parâmetros
        ``snapshot_plan_id``/``snapshot_task_id`` presentes, (3) manifest
        existe, (4) alvo confinado pelo sandbox
        (``manifest.requested_path`` — nunca ``resolved_path``) e (5) a
        operação passa na política (``write`` ao restaurar conteúdo,
        ``delete`` ao desfazer criação). Senão a task falha direto na
        tool com o motivo real (bloqueio honesto).
        """
        if self._snapshot_store is None:
            return False
        if not self._permissions.is_granted(PermissionLevel.WRITE):
            return False  # sem permissão: o handler bloqueia de verdade
        parameters = dict(task.parameters or {})
        plan_id = parameters.get("snapshot_plan_id")
        task_id = parameters.get("snapshot_task_id")
        if not isinstance(plan_id, str) or not plan_id.strip():
            return False
        if not isinstance(task_id, str) or not task_id.strip():
            return False
        try:
            manifest = self._snapshot_store.load_manifest(plan_id, task_id)
            if manifest is None:
                return False  # sem snapshot: a tool falha honestamente
            resolved = self._sandbox.resolve(manifest.requested_path)
            operation = (
                OPERATION_WRITE if manifest.existed_before else OPERATION_DELETE
            )
            self._sandbox.check_operation(operation, resolved)
        except FilesystemError:
            return False  # fora do workspace/política: falha controlada
        return True


class _CombinedCheckpoints(ToolCheckpoints):
    """Une as políticas de checkpoint (filesystem + terminal, 0.6).

    O Executor recebe UMA política; esta delega para cada política
    específica (qualquer uma pode pedir aprovação).
    """

    def __init__(self, policies: list[ToolCheckpoints]) -> None:
        combined: set[str] = set()
        for policy in policies:
            combined.update(policy.required_tools)
        super().__init__(combined)
        self._policies = tuple(policies)

    def requires_checkpoint(self, task) -> bool:  # type: ignore[override]
        return any(policy.requires_checkpoint(task) for policy in self._policies)


def _maybe_persist_execution_state(config, plan, report, *, correction=None) -> None:
    """9B: persiste o bundle de execução, se ``config`` habilitar (best-effort).

    ``config`` é qualquer objeto Settings-like com
    ``persist_execution_state`` e ``execution_dir`` (a integração real
    usa :class:`~app.config.settings.Settings`). Desligado (default)
    retorna imediatamente — nenhum diretório/arquivo é criado. Falha do
    sink NUNCA mascara o resultado da execução: é apenas registrada.
    """
    if not getattr(config, "persist_execution_state", False):
        return
    try:
        from app import __version__

        base_dir = getattr(config, "execution_dir", None)
        if base_dir is None:
            from app.config.settings import Settings

            base_dir = Settings().execution_dir
        ExecutionBundleStore(base_dir).save_bundle(
            plan=plan, report=report,
            correction=correction, lumen_version=__version__,
        )
    except Exception:  # sink nunca derruba o fluxo
        logger.exception(
            "Falha (não fatal) ao persistir o estado de execução do plano %s.",
            getattr(report, "plan_id", "?"),
        )


class ToolsController:
    """Fachada de workspaces + permissões + execução + auditoria."""

    def __init__(
        self,
        permissions: PermissionManager,
        *,
        workspaces_file: Path,
        audit_file: Path,
        terminal_file: Path | None = None,
        persist_execution_state: bool = False,
        execution_state_dir: Path | str | None = None,
        toggles_file: Path | None = None,
        export_execution_reports: bool = False,
        reports_dir: Path | None = None,
        enable_snapshots: bool = False,
        snapshots_dir: Path | None = None,
        snapshot_max_bytes: int = 1_000_000,
    ) -> None:
        if not isinstance(permissions, PermissionManager):
            raise ToolsControlError(
                "ToolsController exige um PermissionManager válido "
                "(compartilhe a instância do Agent)."
            )
        self._permissions = permissions
        self._store = WorkspaceStore(workspaces_file)
        self._audit_file = Path(audit_file)
        self._audit = FilesystemAudit(sink=JsonlAuditSink(self._audit_file))
        self._executor: PlanExecutor | None = None
        self._plan: Plan | None = None
        self._registry: ToolRegistry | None = None
        self._terminal_policy: TerminalPolicy | None = None
        # CC-4: escopos de Computer Control criados em sessão (NÃO
        # persistem entre sessões — assim como a permissão COMPUTER_CONTROL;
        # ver grant_computer_control). Cada plano/execução lê este dict.
        self._cc_scopes: dict = {}
        self._terminal_store = (
            TerminalStore(terminal_file) if terminal_file is not None else None
        )
        self._engine: CorrectionEngine | None = None
        self._corrections: dict | None = None
        # 11E: verificação real opt-in (default None = sem verificação —
        # comportamento atual preservado; ver docs/SPEC-11E-REAL_VERIFICATION.md).
        self._verifier: TaskVerifier | None = None
        # 11H: toggles persistentes (SÓ capacidade — nunca concede
        # permissão; fail-closed; ver docs/SPEC-11H-SETTINGS_UI_TOGGLES.md).
        self._toggles_store = ToggleStore(
            toggles_file
            if toggles_file is not None
            else Path("data/agent_toggles.json")
        )
        self._toggles = self._toggles_store.load()  # fail-closed: não levanta
        # 11I: export do relatório de evidências pós-execução (opt-in;
        # best-effort — só escreve <reports_dir>/<plan_id>.json sanitizado;
        # sem execução, sem permissões; ver docs/SPEC-11I-REPORT_EXPORT.md).
        self._export_execution_reports = bool(export_execution_reports)
        self._reports_dir = (
            Path(reports_dir) if reports_dir is not None
            else Path("data") / "reports"
        )
        # 9B: persistência sanitizada do estado de execução (default OFF).
        self._persist_execution_state = bool(persist_execution_state)
        self._execution_state_dir = (
            Path(execution_state_dir) if execution_state_dir is not None else None
        )
        # 11K: snapshot "before" de operações destrutivas (opt-in,
        # default OFF — bit-a-bit; best-effort; somente metadados no
        # audit; ver docs/SPEC-11K-SNAPSHOT_ROLLBACK.md). O store não
        # tem efeitos colaterais no construtor (nada é criado em disco).
        self._enable_snapshots = bool(enable_snapshots)
        self._snapshots_dir = (
            Path(snapshots_dir) if snapshots_dir is not None
            else Path("data") / "snapshots"
        )
        self._snapshot_store = SnapshotStore(
            self._snapshots_dir, max_snapshot_bytes=snapshot_max_bytes
        )
        self._load_terminal()  # fail-closed; não cria arquivo nem concede nada
        self._apply_persisted_toggles()  # 11H: só capacidade, sem permissões

    def _load_terminal(self) -> None:
        """Carrega a allowlist persistida (se houver) — **fail closed**.

        Arquivo ausente ⇒ terminal segue desabilitado (nada muda no
        startup). Arquivo ilegível/inválido ⇒ terminal desabilitado + erro
        registrado (nunca habilita "por otimismo"). Entradas inválidas ou
        denylistadas no arquivo são **descartadas** com aviso. A permissão
        TERMINAL **nunca** é restaurada — concessão é explícita por sessão.
        """
        if self._terminal_store is None:
            return
        try:
            data = self._terminal_store.load()
        except TerminalStoreError as exc:
            logger.error("Terminal desabilitado (persistência ilegível): %s", exc)
            return
        if data is None:
            return
        defaults = data.get("defaults") or {}
        entries: list[AllowedCommand] = []
        for item in data.get("commands", []):
            if not isinstance(item, dict):
                logger.warning("Entrada de allowlist ignorada (inválida): %r", item)
                continue
            try:
                entries.append(TerminalPolicy.make_entry(
                    item.get("name", ""),
                    full_path=Path(item["full_path"]) if item.get("full_path") else None,
                    args_allowlist=tuple(item.get("args_allowlist") or ()),
                    requires_approval=bool(item.get("requires_approval", True)),
                    timeout_s=item.get("timeout_s"),
                    max_output_bytes=item.get("max_output_bytes"),
                    description=str(item.get("description") or ""),
                ))
            except (TerminalSecurityError, TypeError, ValueError) as exc:
                logger.warning("Entrada de allowlist descartada: %s", exc)
        try:
            self._terminal_policy = TerminalPolicy(
                entries,
                default_timeout_s=int(defaults.get("default_timeout_s", 10)),
                max_timeout_s=int(defaults.get("max_timeout_s", 60)),
                default_max_output_bytes=int(
                    defaults.get("default_max_output_bytes", 64 * 1024)
                ),
                allow_operators=bool(defaults.get("allow_operators", False)),
            )
            logger.info("Allowlist de terminal carregada: %s.",
                        self._terminal_policy.allowed_names)
        except (TerminalSecurityError, TypeError, ValueError) as exc:
            logger.error("Terminal desabilitado (defaults inválidos): %s", exc)
            self._terminal_policy = None

    def _persist_terminal(self) -> None:
        if self._terminal_store is None or self._terminal_policy is None:
            return
        self._terminal_store.save(
            self._terminal_policy.entries(),
            {
                "default_timeout_s": self._terminal_policy.default_timeout_s,
                "max_timeout_s": self._terminal_policy.max_timeout_s,
                "default_max_output_bytes": (
                    self._terminal_policy.default_max_output_bytes
                ),
                "allow_operators": self._terminal_policy.allow_operators,
            },
        )

    def _apply_persisted_toggles(self) -> None:
        """11H: aplica os toggles persistidos no startup — SÓ capacidade.

        Liga apenas as capacidades (corrections/verification); **jamais
        concede permissão** — a concessão TERMINAL continua explícita por
        sessão (regra 0.6.x, ver ``_load_terminal``).
        """
        if self._toggles.corrections_enabled:
            self.enable_corrections()
        if self._toggles.verification_enabled:
            self.enable_verification("pytest_result")

    def _audit_admin(self, operation: str, *,
                     tool: str = "terminal_admin",
                     success: bool = True,
                     error: str | None = None, **detail: Any) -> None:
        """Audita ações administrativas de terminal (0.6.x) — JSONL.

        ``tool`` é "terminal_admin" por padrão; quem registra ações
        administrativas de outra ferramenta pode sobrescrevê-lo.
        """
        self._audit.record(
            tool=tool,
            operation=operation,
            requested_path=None,
            success=success,
            error=error,
            **detail,
        )

    # ---------------------------------------------------------------- terminal
    def enable_terminal(
        self,
        allowed_commands: list[AllowedCommand | str] | None = None,
        *,
        default_timeout_s: int = 10,
        max_timeout_s: int = 60,
        default_max_output_bytes: int = 64 * 1024,
        allow_operators: bool = False,
    ) -> list[str]:
        """Habilita a ferramenta ``run_command`` com uma **allowlist explícita**.

        Opt-in do integrador (a UI não liga o terminal; nada é habilitado
        no startup). A permissão ``TERMINAL`` continua sendo concessão
        programática explícita — não gerenciável pela UI nesta versão.
        Denylist permanente é aplicada no registro (shells/
        interpretadores/destrutivos/administrativos/rede são rejeitados).
        """
        try:
            policy = TerminalPolicy(
                allowed_commands or [],
                default_timeout_s=default_timeout_s,
                max_timeout_s=max_timeout_s,
                default_max_output_bytes=default_max_output_bytes,
                allow_operators=allow_operators,
            )
        except TerminalSecurityError as exc:
            self._audit_admin("terminal_enable", success=False, error=str(exc))
            raise ToolsControlError(f"Allowlist de terminal inválida: {exc}") from exc
        self._terminal_policy = policy
        self._persist_terminal()
        self._audit_admin("terminal_enable", command=list(policy.allowed_names))
        logger.info("Terminal habilitado com allowlist: %s.", policy.allowed_names)
        return list(policy.allowed_names)

    def allow_command(self, name: str, **kwargs: Any) -> dict:
        """Adiciona um comando à allowlist (denylist rejeita; persiste+audita).

        Primeiro comando em um terminal desabilitado **habilita** a
        allowlist (política vazia + o comando) — o cadastro explícito é o
        ato de habilitação (auditado como ``terminal_enable``); não há
        concessão de permissão aqui.
        """
        if self._terminal_policy is None:
            try:
                self._terminal_policy = TerminalPolicy([])
            except TerminalSecurityError as exc:  # pragma: no cover - válidos
                raise ToolsControlError(str(exc)) from exc
            self._audit_admin("terminal_enable", command=[],
                              note="bootstrap pelo primeiro allowlist")
            logger.info("Terminal habilitado (primeiro comando allowlistado).")
        try:
            entry = self._terminal_policy.allow(name, **kwargs)
        except TerminalSecurityError as exc:
            self._audit_admin("allowlist_add", success=False, error=str(exc),
                              command=[str(name)])
            raise ToolsControlError(str(exc)) from exc
        self._persist_terminal()
        self._audit_admin("allowlist_add", command=[entry.name],
                          requires_approval=entry.requires_approval)
        return {"name": entry.name, "requires_approval": entry.requires_approval}

    def remove_allowed_command(self, name: str) -> dict:
        """Remove um comando da allowlist (persiste + audita)."""
        if self._terminal_policy is None:
            raise ToolsControlError(
                "Terminal não habilitado — chame enable_terminal antes."
            )
        try:
            entry = self._terminal_policy.remove(name)
        except TerminalSecurityError as exc:
            self._audit_admin("allowlist_remove", success=False, error=str(exc),
                              command=[str(name)])
            raise ToolsControlError(str(exc)) from exc
        self._persist_terminal()
        self._audit_admin("allowlist_remove", command=[entry.name])
        return {"name": entry.name}

    def list_allowed_commands(self) -> list[dict]:
        """Allowlist vigente para a UI (nome, flags e limites resolvidos)."""
        if self._terminal_policy is None:
            return []
        policy = self._terminal_policy
        return [
            {
                "name": entry.name,
                "full_path": str(entry.full_path) if entry.full_path else None,
                "args_allowlist": list(entry.args_allowlist),
                "requires_approval": entry.requires_approval,
                "timeout_s": (
                    entry.timeout_s if entry.timeout_s is not None
                    else policy.default_timeout_s
                ),
                "max_output_bytes": (
                    entry.max_output_bytes if entry.max_output_bytes is not None
                    else policy.default_max_output_bytes
                ),
                "description": entry.description,
            }
            for entry in policy.entries()
        ]

    def terminal_status(self) -> dict:
        """Estado do terminal para a UI (habilitação/allowlist/permissão)."""
        policy = self._terminal_policy
        return {
            "enabled": policy is not None,
            "allowed_count": len(policy.allowed_names) if policy else 0,
            "permission_granted": self._permissions.is_granted("TERMINAL"),
            "default_timeout_s": policy.default_timeout_s if policy else None,
            "max_timeout_s": policy.max_timeout_s if policy else None,
            "max_output_bytes": (
                policy.default_max_output_bytes if policy else None
            ),
            "allow_operators": policy.allow_operators if policy else False,
        }

    def grant_terminal(self) -> None:
        """Concede **explicitamente** a permissão TERMINAL (0.6.x).

        Caminho dedicado e auditado — o genérico :meth:`grant_permission`
        continua rejeitando TERMINAL (nenhuma concessão silenciosa ou
        "por engano"). A concessão **não persiste** entre sessões.
        """
        self._permissions.grant("TERMINAL")
        logger.info("Permissão TERMINAL concedida pela UI (explícita).")
        self._audit_admin("terminal_grant")

    def revoke_terminal(self) -> None:
        """Revoga a permissão TERMINAL (explícito; auditado)."""
        self._permissions.revoke("TERMINAL")
        logger.info("Permissão TERMINAL revogada pela UI.")
        self._audit_admin("terminal_revoke")

    def grant_computer_control(self) -> None:
        """Concede **explicitamente** a permissão COMPUTER_CONTROL (0.6.x).

        Caminho dedicado e auditado — o genérico :meth:`grant_permission`
        continua rejeitando COMPUTER_CONTROL (nenhuma concessão silenciosa
        ou "por engano"). A concessão **não persiste** entre sessões.
        """
        self._permissions.grant("COMPUTER_CONTROL")
        logger.info("Permissão COMPUTER_CONTROL concedida pela UI (explícita).")  # noqa: E501
        self._audit_admin("cc_grant", tool="cc_admin")

    def revoke_computer_control(self) -> None:
        """Revoga a permissão COMPUTER_CONTROL (explícito; auditado)."""
        self._permissions.revoke("COMPUTER_CONTROL")
        logger.info("Permissão COMPUTER_CONTROL revogada pela UI.")
        self._audit_admin("cc_revoke", tool="cc_admin")

    def disable_terminal(self) -> None:
        """Remove a ferramenta de terminal e esvazia a allowlist persistida."""
        had = self._terminal_policy is not None
        self._terminal_policy = TerminalPolicy([]) if had else None
        if had:
            self._persist_terminal()  # allowlist vazia no disco
        self._terminal_policy = None
        logger.info("Terminal desabilitado.")
        self._audit_admin("terminal_disable")

    @property
    def terminal_policy(self) -> TerminalPolicy | None:
        return self._terminal_policy

    # ---------------------------------------------------------------- correção
    def enable_corrections(
        self,
        strategy: CorrectionStrategy | None = None,
        *,
        max_cycles: int = 2,
        max_total_attempts: int = 8,
    ) -> None:
        """Habilita o ciclo controlado de correção automática (0.6.2).

        ``EXECUTAR → VERIFICAR → FALHA → ANALISAR → PROPOR → VALIDAR →
        APROVAR → APLICAR → RETRY → VERIFICAR``. Opt-in do integrador
        (nada no startup); limites rígidos (``max_cycles`` ≥ 0,
        ``max_total_attempts`` ≥ 1 — nunca retry infinito); estratégia
        default: :class:`EvidenceCorrectionStrategy` sobre
        :class:`ToolCorrectionStrategy` (11J: conselho com evidência real
        para ``run_pytest``, advice-only; conservadora; sem bypass; toda
        proposta com tarefa corrigida exige aprovação).
        """
        if max_cycles < 0:
            raise ToolsControlError("max_cycles deve ser >= 0.")
        if max_total_attempts < 1:
            raise ToolsControlError(
                "max_total_attempts deve ser >= 1 (sem retry infinito)."
            )
        self._corrections = {
            # 11J: default = evidência real (advice-only) sobre a base
            # conservadora; strategy custom fornecida NUNCA é sobrescrita.
            "strategy": strategy or EvidenceCorrectionStrategy(
                ToolCorrectionStrategy()
            ),
            "max_cycles": int(max_cycles),
            "max_total_attempts": int(max_total_attempts),
        }
        logger.info(
            "Correção automática habilitada (ciclos=%d, tentativas=%d).",
            max_cycles, max_total_attempts,
        )

    def disable_corrections(self) -> None:
        """Desliga a correção automática (execução volta ao modo direto)."""
        self._corrections = None
        logger.info("Correção automática desabilitada.")

    @property
    def corrections_enabled(self) -> bool:
        return self._corrections is not None

    # -------------------------------------------------- verificação real (11E)
    def enable_verification(self, verifier_name: str = "pytest_result") -> None:
        """Habilita verificação real no ``run_plan`` (11E — opt-in).

        ``"pytest_result"`` instala o :class:`PytestResultVerifier` —
        **interpretador sem execução**: apenas lê o JSON ``ToolResult``
        da task ``run_pytest`` (que continua sendo uma task normal do
        plano, com permissão ``TERMINAL`` + checkpoint obrigatório; o
        verifier jamais dispara subprocesso — spec 11E §3). O default do
        controller continua sem verificação (``verifier=None``).
        """
        if verifier_name == "pytest_result":
            # import local (padrão do módulo; evita ciclo/estouro de imports)
            from app.executor.verification import PytestResultVerifier

            self._verifier = PytestResultVerifier()
            logger.info("Verificação real habilitada (verifier=pytest_result).")
            return
        raise ValueError("unknown verifier")

    def disable_verification(self) -> None:
        """Desliga a verificação real (execução volta ao modo default)."""
        self._verifier = None
        logger.info("Verificação real desabilitada.")

    @property
    def verification_enabled(self) -> bool:
        return self._verifier is not None

    # ------------------------------------------- toggles persistentes (11H)
    @property
    def corrections_persisted(self) -> bool:
        """11H: valor persistido do toggle de correções (arquivo)."""
        return self._toggles.corrections_enabled

    @property
    def verification_persisted(self) -> bool:
        """11H: valor persistido do toggle de verificação (arquivo)."""
        return self._toggles.verification_enabled

    def _persist_toggles(self, operation: str, **detail: Any) -> None:
        """11H: grava o estado dos toggles (somente flags bool) + audita.

        Falha de escrita: audita ``success=False`` e re-levanta
        :class:`ToggleStoreError` (o chamador decide — padrão das ações
        administrativas de terminal).
        """
        try:
            self._toggles_store.save(self._toggles)
        except ToggleStoreError as exc:
            self._audit.record(
                tool="toggles", operation=operation,
                requested_path=None, success=False, error=str(exc), **detail,
            )
            raise
        self._audit.record(
            tool="toggles", operation=operation,
            requested_path=None, success=True, **detail,
        )

    def set_corrections_enabled(self, enabled: bool) -> None:
        """11H: liga/desliga a correção automática e persiste o toggle.

        Aplica na hora (``enable_corrections``/``disable_corrections``) e
        salva a flag booleana no store de toggles. **Nunca concede
        permissão** — autoridade de execução segue inalterada.
        """
        if bool(enabled):
            self.enable_corrections()
        else:
            self.disable_corrections()
        self._toggles.corrections_enabled = bool(enabled)
        self._persist_toggles("corrections_toggle",
                              corrections_enabled=self._toggles.corrections_enabled)

    def set_verification_enabled(self, enabled: bool) -> None:
        """11H: liga/desliga a verificação real e persiste o toggle.

        Quando ON, instala o verifier ``"pytest_result"`` (11E). Aplica na
        hora e salva a flag booleana no store de toggles. **Nunca concede
        permissão** — o verifier é um interpretador sem execução.
        """
        if bool(enabled):
            self.enable_verification("pytest_result")
        else:
            self.disable_verification()
        self._toggles.verification_enabled = bool(enabled)
        self._persist_toggles("verification_toggle",
                              verification_enabled=self._toggles.verification_enabled)

    def correction_history(self) -> list[dict]:
        """Ciclos de correção da última execução (auditoria/UI)."""
        if self._engine is None:
            return []
        return [cycle.to_dict() for cycle in self._engine.cycles]

    def _audit_cycle(self, cycle: CorrectionCycle) -> None:
        """Leva cada mudança de estado do ciclo para a trilha JSONL."""
        negative = {"INVALID", "REFUSED", "FAILED", "NO_PROPOSAL", "EXHAUSTED"}
        self._audit.record(
            tool="correction",
            operation=f"correction_{cycle.status.value.lower()}",
            requested_path=None,
            success=cycle.status.value not in negative,
            error=cycle.error,
            task_id=cycle.task_id,
            plan_id=cycle.plan_id,
            cycle=cycle.number,
            suggestion=(cycle.suggestion or "")[:160],
            replacement_tool=cycle.replacement_tool,
            note=(cycle.decision_note or "")[:160],
        )

    # -------------------------------------------------------------- permissões
    def permission_status(self) -> list[dict]:
        """Visão das permissões para a UI (CHAT/READ/WRITE + DELETE)."""
        rows = []
        for level in MANAGEABLE_LEVELS:
            rows.append({
                "level": level.name,
                "kind": "permission",
                "granted": self._permissions.is_granted(level),
                "description": (
                    "Conversar com o usuário" if level is PermissionLevel.CHAT
                    else "Ler arquivos e diretórios dos workspaces"
                    if level is PermissionLevel.READ
                    else "Criar/modificar arquivos dos workspaces"
                ),
            })
        rows.append({
            "level": "TERMINAL",
            "kind": "permission",
            "granted": self._permissions.is_granted(PermissionLevel.TERMINAL),
            "description": (
                "Executar APENAS comandos da allowlist, dentro do workspace, "
                "com timeout, limite de saída e checkpoint por comando "
                "(shells, interpretadores e rede são proibidos)"
            ),
        })
        rows.append({
            "level": "DELETE",
            "kind": "workspace_opt_in",
            "granted": any(e.allow_delete for e in self._store.load()),
            "description": "Exclusão de arquivos — opt-in por workspace "
                           "(escrita + permitir excluir)",
        })
        return rows


    def grant_vision_provider(self) -> None:
        """Concede explicitamente a permiss?o VISION_PROVIDER (envio de screenshots para provider com vis?o)."""
        self._permissions.grant(PermissionLevel.VISION_PROVIDER)
        try:
            self._audit.record(tool="vision_admin", action="grant_vision_provider")
        except Exception:
            pass

    def grant_permission(self, level: str) -> None:
        """Concede CHAT/READ/WRITE (explícito; outros níveis são rejeitados)."""
        resolved = self._resolve_manageable(level)
        self._permissions.grant(resolved)
        logger.info("Permissão concedida pela UI: %s.", resolved.name)

    def revoke_permission(self, level: str) -> None:
        """Revoga CHAT/READ/WRITE (explícito; outros níveis são rejeitados)."""
        resolved = self._resolve_manageable(level)
        self._permissions.revoke(resolved)
        logger.info("Permissão revogada pela UI: %s.", resolved.name)

    @staticmethod
    def _resolve_manageable(level: str) -> PermissionLevel:
        try:
            resolved = PermissionLevel[str(level).upper()]
        except KeyError as exc:
            raise ToolsControlError(
                f"Permissão desconhecida: {level!r}."
            ) from exc
        if resolved not in MANAGEABLE_LEVELS:
            raise ToolsControlError(
                f"A permissão {resolved.name} não pode ser concedida por esta "
                "interface (não faz parte desta versão)."
            )
        return resolved

    # -------------------------------------------------------------- workspaces
    def list_workspaces(self) -> list[dict]:
        """Workspaces autorizados (raiz normalizada + política legível)."""
        return [
            {
                "root": str(entry.root),
                "writable": entry.writable,
                "allow_delete": entry.allow_delete,
                "mode": entry.mode_label,
            }
            for entry in self._store.load()
        ]

    def add_workspace(
        self, path: str, *, writable: bool = False, allow_delete: bool = False
    ) -> dict:
        entry = self._store.add(path, writable=writable, allow_delete=allow_delete)
        return {"root": str(entry.root), "mode": entry.mode_label}

    def remove_workspace(self, path: str) -> None:
        self._store.remove(path)

    def set_workspace_flags(
        self, path: str, *, writable: bool, allow_delete: bool
    ) -> dict:
        entry = self._store.set_flags(
            path, writable=writable, allow_delete=allow_delete
        )
        return {"root": str(entry.root), "mode": entry.mode_label}

    # ------------------------------------------------------------- sandbox/tool
    def _sandbox(self) -> MultiWorkspaceSandbox:
        return MultiWorkspaceSandbox(self._store.load())

    def planning_catalog(self) -> dict:
        """Allowlist de ferramentas que o chat pode planejar (0.6.3).

        As 6 ferramentas de filesystem (sempre registradas por
        :meth:`build_registry`) + ``run_command`` **somente** quando o
        terminal já estiver explicitamente habilitado
        (:meth:`enable_terminal`); ferramentas de automação do desktop
        (CC) **somente** quando a permissão ``COMPUTER_CONTROL`` foi
        explicitamente concedida (:meth:`grant_computer_control` — CC-3).
        Nada além disso: o Planner não conhece ferramentas que a camada
        de tools não registraria — e o registro continua sendo o porteiro
        real na execução (permissões, sandbox e checkpoints inalterados).
        """
        from app.planner.catalog import build_catalog

        return build_catalog(
            include_terminal=self._terminal_policy is not None,
            include_computer_control=self._permissions.is_granted(
                "COMPUTER_CONTROL"
            ),
        )

    def build_registry(self) -> ToolRegistry:
        """Registry com as ferramentas habilitadas sobre os workspaces atuais.

        Filesystem (7 ferramentas, incluindo ``search_files``) sempre;
        ``run_command`` **somente** quando o terminal foi habilitado via
        :meth:`enable_terminal` (allowlist explícita — registro nunca é
        automático); 11K: ``restore_snapshot`` (rollback manual) também
        sempre — porteio pela permissão ``WRITE`` + checkpoint
        pré-validado (manifest + confinamento + política). CC-4:
        ``cc_request_scope`` **somente** quando a permissão
        ``COMPUTER_CONTROL`` foi explicitamente concedida (gate de
        catálogo no planning_catalog; o registry também exige o grant).
        """
        sandbox = self._sandbox()
        registry = build_filesystem_registry(self._permissions, sandbox, self._audit)
        # 11K: rollback manual — SEMPRE registrada (não depende do
        # terminal); nada é concedido (gate WRITE + checkpoint).
        from app.tools.restore_snapshot import RestoreSnapshotTool

        registry.register(
            RestoreSnapshotTool(sandbox, self._snapshots_dir, self._audit)
        )
        if self._terminal_policy is not None:
            from app.tools.run_pytest import RunPytestTool

            registry.register(
                RunCommandTool(self._terminal_policy, sandbox, self._audit)
            )
            registry.register(RunPytestTool(sandbox, self._audit))
        # CC-4/CC-5: ferramentas de Computer Control SOMENTE quando a
        # permissão COMPUTER_CONTROL foi explicitamente concedida (grant
        # por sessão, ver grant_computer_control). O registry também faz o
        # gate (required_permission = COMPUTER_CONTROL); aqui as
        # registramos só quando há grant — paridade com
        # include_computer_control do catálogo.
        if self._permissions.is_granted(PermissionLevel.COMPUTER_CONTROL):
            import sys

            from app.computer_control.fake_driver import FakeComputerControlDriver
            from app.tools.computer_control import (
                CcRequestScopeTool,
                CcScreenshotTool,
                CcMouseMoveTool,
                CcMouseClickTool,
                CcMouseClickAtTool,
                CcKeyTypeTool,
                CcDoubleClickAndTypeTool,
                CcFocusWindowTool,
                CcWaitForWindowTool,
                CcLocateTemplateTool,
                CcMouseMoveToTool,
                CcClickTemplateTool,
                CcClickTemplateLiveTool,
                CcClickTargetLiveTool,
                CcListScopesTool,
                CcRevokeScopeTool,
            )

            # Seleção do driver por SO. No Windows usamos o driver real
            # (mss -> PNG em data/audit/artifacts/cc); nos demais SOs, ou
            # se o driver real não puder ser carregado, usamos o FakeDriver
            # determinístico/metadata-only. O contrato das tools não muda.
            # (Usa ``sys.platform`` e não ``platform.system()`` para não
            # introduzir o token "system", proibido pelo guard estático.)
            cc_driver = FakeComputerControlDriver()
            if sys.platform == "win32":
                try:
                    from app.computer_control.windows.driver import (
                        WindowsComputerControlDriver,
                    )

                    artifacts_dir = self._audit_file.parent / "artifacts" / "cc"
                    cc_driver = WindowsComputerControlDriver(artifacts_dir=artifacts_dir)
                except Exception as exc:  # pragma: no cover - depende do SO/mss
                    logger.warning(
                        "Driver CC de Windows indisponível; caindo para "
                        "FakeComputerControlDriver: %s",
                        exc,
                    )
            registry.register(
                CcRequestScopeTool(scopes=self._cc_scopes, audit=self._audit)
            )
            registry.register(
                CcScreenshotTool(
                    scopes=self._cc_scopes, audit=self._audit, driver=cc_driver
                )
            )
            registry.register(
                CcMouseMoveTool(scopes=self._cc_scopes, audit=self._audit, driver=cc_driver)
            )
            registry.register(
                CcMouseClickTool(scopes=self._cc_scopes, audit=self._audit, driver=cc_driver)
            )
            registry.register(
                CcMouseClickAtTool(scopes=self._cc_scopes, audit=self._audit, driver=cc_driver)
            )
            registry.register(
                CcKeyTypeTool(scopes=self._cc_scopes, audit=self._audit, driver=cc_driver)
            )
            registry.register(
                CcDoubleClickAndTypeTool(scopes=self._cc_scopes, audit=self._audit, driver=cc_driver)
            )
            registry.register(
                CcFocusWindowTool(scopes=self._cc_scopes, audit=self._audit, driver=cc_driver)
            )
            registry.register(
                CcWaitForWindowTool(scopes=self._cc_scopes, audit=self._audit, driver=cc_driver)
            )
            registry.register(
                CcLocateTemplateTool(scopes=self._cc_scopes, audit=self._audit)
            )
            registry.register(
                CcMouseMoveToTool(scopes=self._cc_scopes, audit=self._audit, driver=cc_driver)
            )
            registry.register(
                CcClickTemplateTool(scopes=self._cc_scopes, audit=self._audit, driver=cc_driver)
            )
            registry.register(
                CcClickTemplateLiveTool(scopes=self._cc_scopes, audit=self._audit, driver=cc_driver)
            )
            # CC-18/19: hybrid offline-first click with provider fallback (only if VISION_PROVIDER granted)
            if self._permissions.is_granted(PermissionLevel.VISION_PROVIDER):
                from app.ai.openai_vision_locator import OpenAIVisionLocator
                from pathlib import Path
                locator = OpenAIVisionLocator()
                templates_dir = Path("data/templates/cc_targets").resolve()
                registry.register(
                    CcClickTargetLiveTool(
                        scopes=self._cc_scopes,
                        audit=self._audit,
                        driver=cc_driver,
                        locator=locator,
                        templates_dir=templates_dir,
                    )
                )
            registry.register(
                CcListScopesTool(scopes=self._cc_scopes, audit=self._audit)
            )
            registry.register(
                CcRevokeScopeTool(scopes=self._cc_scopes, audit=self._audit)
            )
        return registry

    # ---------------------------------------------------------------- execução
    def run_plan(self, plan: Plan) -> ExecutionReport:
        """Executa um plano com as ferramentas reais + checkpoints.

        Executa até pausar por checkpoint (operação destrutiva **viável**
        aguardando aprovação — veja :meth:`pending_approval`), concluir ou
        falhar. Operações sem permissão/fora da política falham direto
        (bloqueio real), sem aprovação decorativa. Comandos de terminal
        viáveis (allowlist + permissão ``TERMINAL`` + cwd) também pausam
        para aprovação quando marcados ``requires_approval``.

        11F: com terminal + verificação 11E habilitados e plano com
        WRITE, é anexada 1 task final ``run_pytest`` — com plano no
        limite de tasks, falha **antes de executar** (tudo ``SKIPPED``,
        motivo claro). 11K: com ``enable_snapshots`` (default OFF),
        operações destrutivas ganham snapshot "before" best-effort
        (somente metadados na auditoria; sem conteúdo).
        """
        sandbox = self._sandbox()
        registry = self.build_registry()
        self._plan = plan
        self._registry = registry
        self._executor = None
        self._engine = None
        # 11F: auto-anexo de run_pytest após WRITE — guardrails **antes**
        # de qualquer task executar (sem chamadas de tool, sem checkpoint).
        if _needs_auto_pytest(
            plan,
            terminal_enabled=self._terminal_policy is not None,
            verification_enabled=self.verification_enabled,
        ):
            if len(plan.tasks) >= _AUTO_PYTEST_MAX_TASKS:
                return self._final(_auto_pytest_limit_report(plan))
            plan = _attach_run_pytest(plan)
            self._plan = plan  # 9B: bundle persiste o plano ajustado
        policies: list[ToolCheckpoints] = [
            PrevalidatedCheckpoints(
                self._permissions, registry, sandbox,
                # 11K: pré-validação de restore_snapshot (viável ou não).
                snapshots_dir=self._snapshots_dir,
            )
        ]
        # CC-10: checkpoint prevalidated para a??es de clique (somente vi?veis).
        if self._permissions.is_granted(PermissionLevel.COMPUTER_CONTROL):
            from app.tools.computer_control import PrevalidatedComputerControlCheckpoints

            policies.append(
                PrevalidatedComputerControlCheckpoints(self._permissions, registry, self._cc_scopes)
            )

        if self._terminal_policy is not None:
            policies.append(
                PrevalidatedTerminalCheckpoints(
                    self._permissions, registry, self._terminal_policy, sandbox
                )
            )
        if self._corrections is not None:
            # 0.6.2: ciclo controlado EXECUTAR→VERIFICAR→(ANALISAR→PROPOR→
            # VALIDAR→APROVAR→APLICAR→RETRY→VERIFICAR)* com limites rígidos.
            # 11G etapa 1: sucessores #C recebem o mesmo auto-anexo de
            # run_pytest (regra 11F) quando aplicável; exceção do
            # transform = falha controlada do engine (sucessor não executa).
            plan_transform = None
            if self._terminal_policy is not None and self.verification_enabled:
                def plan_transform(p: Plan) -> Plan:
                    if not _needs_auto_pytest(
                        p,
                        terminal_enabled=self._terminal_policy is not None,
                        verification_enabled=self.verification_enabled,
                    ):
                        return p
                    if len(p.tasks) >= _AUTO_PYTEST_MAX_TASKS:
                        raise ValueError(
                            "auto-anexo 11F: o plano sucessor já tem "
                            f"{len(p.tasks)} tasks (máximo "
                            f"{_AUTO_PYTEST_MAX_TASKS}); run_pytest não "
                            "pode ser anexado — nada executa."
                        )
                    return _attach_run_pytest(p)
            engine = CorrectionEngine(
                plan,
                lambda plan_id: ToolTaskHandler(
                    registry, audit=self._audit, plan_id=plan_id,
                    # 11K: snapshot "before" (default OFF — bit-a-bit).
                    sandbox=sandbox,
                    snapshot_store=self._snapshot_store,
                    enable_snapshots=self._enable_snapshots,
                ),
                strategy=self._corrections["strategy"],
                validator=build_proposal_validator(
                    registry, self._permissions, sandbox, self._terminal_policy
                ),
                checkpoints_factory=lambda: _CombinedCheckpoints(policies),
                # 11G etapa 0: verificação 11E aplica também em modo
                # corrections (None quando desabilitada = default atual).
                verifier_factory=lambda: self._verifier,
                plan_transform=plan_transform,
                max_cycles=self._corrections["max_cycles"],
                max_total_attempts=self._corrections["max_total_attempts"],
                listener=self._audit_cycle,
            )
            self._engine = engine
            return self._final(engine.run().execution)
        handler = ToolTaskHandler(
            registry, audit=self._audit, plan_id=plan.id,
            # 11K: snapshot "before" (default OFF — bit-a-bit).
            sandbox=sandbox,
            snapshot_store=self._snapshot_store,
            enable_snapshots=self._enable_snapshots,
        )
        self._executor = PlanExecutor(
            plan, handler, checkpoints=_CombinedCheckpoints(policies),
            verifier=self._verifier,  # 11E: None (default) ou opt-in
        )
        return self._final(self._drive())

    def _drive(self) -> ExecutionReport:
        assert self._executor is not None
        while self._executor.step() is not None:
            pass
        return self._executor.report()

    def _final(self, report: ExecutionReport) -> ExecutionReport:
        """9B: persiste o bundle em estado TERMINAL (best-effort, opt-in).

        RUNNING (pausado por checkpoint) não persiste nada — o bundle é
        gravado uma única vez, no desfecho (COMPLETED/FAILED), a partir
        dos 8 retornos terminais (run_plan ×2, approve ×3, refuse ×3).

        11I: exporta o relatório de evidências no mesmo funil (opt-in
        independente do 9B; best-effort — falha nunca quebra o fluxo).
        """
        if self._export_execution_reports:
            self._maybe_export_report(report)
        if not self._persist_execution_state:
            return report
        if report.status not in (PlanStatus.COMPLETED, PlanStatus.FAILED):
            return report
        if self._plan is None:  # pragma: no cover - defensivo
            return report
        from types import SimpleNamespace

        config = SimpleNamespace(
            persist_execution_state=self._persist_execution_state,
            execution_dir=self._execution_state_dir,  # None ⇒ Settings()
        )
        _maybe_persist_execution_state(
            config, self._plan, report,
            correction=self.correction_history() or None,
        )
        return report

    def _maybe_export_report(self, report: ExecutionReport) -> None:
        """11I: exporta o relatório de evidências (best-effort, opt-in).

        Somente em estado TERMINAL (COMPLETED/FAILED) com plano ativo;
        grava ``<reports_dir>/<safe_plan_id>.json`` sanitizado (auditoria
        filtrada por ``plan_id``). **Sem execução, sem permissões**;
        qualquer falha é logada — o relatório/fluxo seguem inalterados
        (spec 11I §4).
        """
        if report.status not in (PlanStatus.COMPLETED, PlanStatus.FAILED):
            return
        if self._plan is None:  # pragma: no cover - defensivo
            return
        try:
            from app import __version__

            plan_id = str(report.plan_id)
            safe_name = re.sub(r"[^A-Za-z0-9._#-]", "_", plan_id) or "plano"
            filtered_audit = [
                record for record in self.audit_records(limit=500)
                if record.get("plan_id") == plan_id
            ]
            payload = build_export_payload(
                plan=self._plan,
                report=report,
                correction_history=self.correction_history(),
                audit_records=filtered_audit,
                lumen_version=__version__,
            )
            export_execution_report(
                self._reports_dir / f"{safe_name}.json", payload,
            )
        except Exception:
            logger.exception(
                "Falha (não fatal) ao exportar o relatório de execução "
                "do plano %s.",
                report.plan_id,
            )

    @property
    def has_pending(self) -> bool:
        if self._engine is not None:
            return self._engine.paused or self._engine.waiting_decision
        return self._executor is not None and self._executor.paused

    def pending_approval(self) -> dict | None:
        """Visão da operação aguardando aprovação (UX: o quê/onde/ferramenta).

        Retorna ``None`` quando nada está pendente.
        """
        if not self.has_pending or self._plan is None:
            return None
        if self._engine is not None:
            return self._pending_engine()
        executor: PlanExecutor = self._executor
        checkpoint = executor.pending_checkpoint
        assert checkpoint is not None
        task = self._plan.task_by_id(checkpoint.task_id)
        if task is None:  # pragma: no cover - plano consistente por construção
            raise ToolsControlError(
                f"Checkpoint {checkpoint.id} aponta tarefa inexistente."
            )
        return self._task_view(self._plan, task, checkpoint)

    def _task_view(self, plan: Plan, task, checkpoint) -> dict:
        """Visão de uma TAREFA aguardando checkpoint (comum aos modos)."""
        parameters = dict(task.parameters or {})
        tool = task.tool or ""
        requested = parameters.get("path")
        sandbox = self._sandbox()
        resolved: str | None = None
        workspace: str | None = None
        preview_error: str | None = None
        command_preview: list[str] | None = None
        timeout_s: int | None = None
        if tool == TERMINAL_TOOL_NAME and self._terminal_policy is not None:
            # Terminal (0.6): preview do comando validado (argv + cwd).
            requested = parameters.get("cwd") or "."
            try:
                validated = self._terminal_policy.validate(
                    parameters.get("command"),
                    parameters.get("args", []),
                    parameters.get("cwd"),
                    sandbox,
                )
                command_preview = list(validated.argv)
                timeout_s = validated.timeout_s
                resolved = str(validated.cwd)
                entry = sandbox.entry_for(validated.cwd)
                workspace = str(entry.root) if entry is not None else None
            except TerminalSecurityError as exc:
                preview_error = str(exc)
        elif isinstance(requested, str) and requested.strip():
            try:
                resolved_path = sandbox.resolve(requested)
                entry = sandbox.entry_for(resolved_path)
                resolved = str(resolved_path)
                workspace = str(entry.root) if entry is not None else None
            except FilesystemError as exc:
                preview_error = str(exc)
        tool_obj = self._registry.get(tool) if self._registry is not None and tool else None
        operation = getattr(tool_obj, "operation", None)
        permission = getattr(tool_obj, "required_permission", None)
        permission = permission.name if permission is not None else None
        raw_content = parameters.get("content")
        content_preview = (
            raw_content if isinstance(raw_content, str) and raw_content.strip()
            else None
        )
        if content_preview is not None and len(content_preview) > 200:
            content_preview = content_preview[:200] + "…"
        return {
            "checkpoint_id": checkpoint.id,
            "status": checkpoint.status.value,
            "task_id": task.id,
            "plan_id": plan.id,
            "description": task.description,
            "tool": tool,
            "content_preview": content_preview,
            "operation": operation,
            "operation_label": OPERATION_LABELS.get(operation or "", operation or "?"),
            "permission": permission,
            "requested_path": requested if isinstance(requested, str) else None,
            "resolved_path": resolved,
            "workspace": workspace,
            "preview_error": preview_error,
            "command": command_preview,
            "timeout_s": timeout_s,
        }

    def _pending_engine(self) -> dict | None:
        """Visão do pendente no modo correção (correção OU checkpoint)."""
        engine = self._engine
        assert engine is not None
        correction = engine.correction_pending
        if correction is not None:
            return {
                "kind": "correction",
                "checkpoint_id": f"COR-{correction.cycle_number:04d}",
                "status": "PENDING_APPROVAL",
                "task_id": correction.task_id,
                "plan_id": correction.plan_id,
                "description": correction.suggestion,
                "tool": correction.corrected_tool or "?",
                "operation": "correction",
                "operation_label": OPERATION_LABELS.get(
                    "correction_proposed", "correção proposta"
                ),
                "permission": None,
                "requested_path":
                    (correction.corrected_parameters or {}).get("path")
                    or (correction.corrected_parameters or {}).get("cwd"),
                "resolved_path": None,
                "workspace": None,
                "preview_error": correction.error,
                "command": (
                    [correction.corrected_parameters.get("command")]
                    + list(correction.corrected_parameters.get("args") or [])
                    if correction.corrected_tool == "run_command" else None
                ),
                "timeout_s": None,
                "failure_kind": correction.failure_kind,
                "original_tool": correction.original_tool,
                "original_parameters": correction.original_parameters,
                "corrected_parameters": correction.corrected_parameters,
                "detail": correction.detail,
            }
        checkpoint = engine.executor.pending_checkpoint
        if checkpoint is None:  # pragma: no cover - consistência interna
            return None
        task = engine.current_plan.task_by_id(checkpoint.task_id)
        if task is None:  # pragma: no cover - plano consistente
            raise ToolsControlError(
                f"Checkpoint {checkpoint.id} aponta tarefa inexistente."
            )
        return self._task_view(engine.current_plan, task, checkpoint)

    def approve(self, note: str = "") -> ExecutionReport:
        """Aprova o pendente (correção OU operação) e retoma até a próxima
        pausa/fim."""
        if not self.has_pending:
            raise ToolsControlError("Nenhuma operação aguardando aprovação.")
        if self._engine is not None:
            engine = self._engine
            if engine.correction_pending is not None:
                return self._final(engine.approve_correction(note).execution)
            engine.approve_checkpoint(note)
            return self._final(engine.run().execution)
        assert self._executor is not None
        self._executor.approve_checkpoint(note)
        return self._final(self._drive())

    def refuse(self, reason: str = "") -> ExecutionReport:
        """Recusa o pendente: correção ⇒ nada é aplicado (falha definitiva);
        operação ⇒ a ferramenta não executa (plano falha controlado)."""
        if not self.has_pending:
            raise ToolsControlError("Nenhuma operação aguardando decisão.")
        if self._engine is not None:
            engine = self._engine
            if engine.correction_pending is not None:
                return self._final(engine.refuse_correction(reason).execution)
            engine.refuse_checkpoint(reason)
            return self._final(engine.executor.report())
        assert self._executor is not None
        self._executor.refuse_checkpoint(reason)
        return self._final(self._executor.report())

    # --------------------------------------------------------------- auditoria
    def audit_records(self, limit: int = 100) -> list[dict]:
        """Últimos registros da trilha (JSONL persistido; memória se o
        arquivo ainda não existir)."""
        if self._audit_file.exists():
            return read_audit_tail(self._audit_file, limit)
        return self._audit.to_dicts()[-limit:]

    @property
    def audit(self) -> FilesystemAudit:
        """Trilha em memória da sessão (exposição para testes/diagnóstico)."""
        return self._audit
