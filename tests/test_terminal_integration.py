"""Testes de integração do terminal (0.6) — cadeia completa e segurança.

Registry → ToolTaskHandler → PlanExecutor · plano programático
(protocolo do Planner, sem Planner autônomo) → Executor → Terminal ·
ToolsController (enable_terminal/run_plan/approve/refuse) · auditoria
JSONL · anti-futuro (subprocess só em terminal.py). Comandos POSIX
inofensivos (printf/mkdir) em diretórios temporários.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

from app.planner.models import Plan, PlanStatus, PlannedTask
from app.security.permissions import PermissionManager
from app.tools.base import ToolRegistry
from app.tools.control import ToolsControlError, ToolsController
from app.tools.filesystem import FilesystemAudit, build_filesystem_registry
from app.tools.handler import ToolTaskHandler
from app.tools.terminal import (
    AllowedCommand,
    RunCommandTool,
    TerminalPolicy,
)
from app.tools.workspaces import MultiWorkspaceSandbox, WorkspaceEntry
from app.executor.executor import PlanExecutor

PROJECT_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="usa comandos POSIX do sandbox"
)


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    root.mkdir()
    return root


@pytest.fixture()
def permissions() -> PermissionManager:
    manager = PermissionManager()
    manager.grant("TERMINAL")  # concessão programática explícita (integrador)
    return manager


@pytest.fixture()
def audit_file(tmp_path: Path) -> Path:
    return tmp_path / "audit" / "audit.jsonl"


@pytest.fixture()
def controller(permissions, tmp_path: Path, audit_file: Path) -> ToolsController:
    return ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=audit_file,
    )


def task(task_id: str, command: str, args: list[str] | None = None,
         cwd: str = ".", order: int = 1,
         dependencies: tuple[str, ...] = ()) -> PlannedTask:
    return PlannedTask(
        id=task_id, description=f"executar {command}", order=order,
        dependencies=dependencies, tool="run_command",
        parameters={"command": command, "args": args or [], "cwd": cwd},
    )


def plan(*tasks: PlannedTask) -> Plan:
    return Plan(id="PLN-6006", objective="trabalho de terminal",
                status=PlanStatus.READY, tasks=tasks)


def pytask(task_id: str, path: str = "mini_tests", order: int = 1,
           dependencies: tuple[str, ...] = ()) -> PlannedTask:
    """Tarefa da tool ``run_pytest`` (11D) apontando a mini-suite do ws."""
    return PlannedTask(
        id=task_id, description=f"rodar mini-suite de {path}", order=order,
        dependencies=dependencies, tool="run_pytest",
        parameters={"path": path, "maxfail": 1, "timeout_s": 60},
    )


def mini_suite(ws: Path) -> Path:
    """Cria a mini-suite (1 teste que passa) dentro do workspace."""
    suite = ws / "mini_tests"
    suite.mkdir()
    (suite / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    return suite


def armed(controller: ToolsController, ws: Path, *commands) -> ToolsController:
    controller.add_workspace(str(ws))
    controller.enable_terminal(list(commands))
    return controller


def sandbox_for(ws: Path) -> MultiWorkspaceSandbox:
    return MultiWorkspaceSandbox(
        [WorkspaceEntry(root=ws.resolve(), writable=True, allow_delete=False)]
    )


# ------------------------------------------- Registry → Handler → Executor
def test_registry_handler_executor_chain(ws, permissions):
    sandbox = sandbox_for(ws)
    audit = FilesystemAudit()
    registry = build_filesystem_registry(permissions, sandbox, audit)
    registry.register(RunCommandTool(TerminalPolicy(["printf"]), sandbox, audit))
    handler = ToolTaskHandler(registry, audit=audit, plan_id="PLN-6006")
    executor = PlanExecutor(plan(task("T1", "printf", ["cadeia-completa"])), handler)
    executor.run_all()
    report = executor.report()
    assert report.status is PlanStatus.COMPLETED
    assert "cadeia-completa" in (report.task_run("T1").result or "")


def test_blocked_command_fails_plan_and_executes_nothing(controller, ws):
    armed(controller, ws, "printf")
    report = controller.run_plan(plan(task("T1", "mkdir", ["vazou"])))
    assert report.status is PlanStatus.FAILED
    assert not controller.has_pending  # inviável: sem checkpoint decorativo
    assert "allowlist" in (report.task_run("T1").error or "")
    assert not (ws / "vazou").exists()  # nada rodou
    run_records = [r for r in controller.audit_records()
                   if r["tool"] == "run_command"]
    assert run_records and run_records[-1]["success"] is False


# ------------------------------------------------------------- checkpoints
def test_checkpoint_pauses_command_and_shows_full_context(controller, ws):
    armed(controller, ws, "mkdir")
    controller.run_plan(plan(task("T1", "mkdir", ["pasta"])))
    assert controller.has_pending
    assert not (ws / "pasta").exists()  # nada roda antes da decisão
    pending = controller.pending_approval()
    assert pending["tool"] == "run_command"
    assert pending["operation"] == "run_command"
    assert pending["operation_label"] == "execução de comando"
    assert pending["permission"] == "TERMINAL"
    assert pending["command"] == ["mkdir", "pasta"]
    assert pending["timeout_s"] == 10
    assert pending["resolved_path"] == str(ws.resolve())
    assert pending["workspace"] == str(ws.resolve())
    assert pending["task_id"] == "T1"
    assert pending["status"] == "PENDING_APPROVAL"


def test_approval_executes_the_command(controller, ws):
    armed(controller, ws, "mkdir")
    controller.run_plan(plan(task("T1", "mkdir", ["aprovada"])))
    report = controller.approve("pode")
    assert report.status is PlanStatus.COMPLETED
    assert (ws / "aprovada").exists()
    assert not controller.has_pending


def test_refusal_never_executes_the_command(controller, ws):
    armed(controller, ws, "mkdir")
    controller.run_plan(plan(task("T1", "mkdir", ["recusada"])))
    report = controller.refuse("não autorizo")
    assert report.status is PlanStatus.FAILED
    assert report.task_run("T1").status.value == "SKIPPED"
    assert not (ws / "recusada").exists()
    runs = [r for r in controller.audit_records()
            if r["tool"] == "run_command" and r["success"]]
    assert runs == []  # nenhuma execução bem-sucedida


# -------------------------------------------------- checkpoints de run_pytest
def test_run_pytest_checkpoint_approved_runs(controller, ws):
    """11D: run_pytest viável PAUSA em checkpoint; aprovar executa o pytest."""
    armed(controller, ws, "mkdir")  # habilita o terminal (registra run_pytest)
    mini_suite(ws)
    controller.run_plan(plan(pytask("T1")))
    assert controller.has_pending  # pausa ANTES de executar
    pending = controller.pending_approval()
    assert pending["tool"] == "run_pytest"
    assert pending["operation"] == "run_pytest"
    assert pending["permission"] == "TERMINAL"
    assert pending["task_id"] == "T1"
    assert pending["status"] == "PENDING_APPROVAL"
    assert pending["requested_path"] == "mini_tests"
    assert pending["resolved_path"] == str((ws / "mini_tests").resolve())
    assert pending["workspace"] == str(ws.resolve())
    report = controller.approve("pode")
    assert report.status is PlanStatus.COMPLETED
    assert not controller.has_pending
    payload = json.loads(report.task_run("T1").result)
    assert payload["ok"] is True
    assert payload["data"]["exit_code"] == 0  # mini-suite verde


def test_run_pytest_checkpoint_refused_does_not_run(controller, ws):
    """11D: recusar o checkpoint de run_pytest ⇒ SKIPPED, nada executa."""
    armed(controller, ws, "mkdir")
    mini_suite(ws)
    controller.run_plan(plan(pytask("T1")))
    assert controller.has_pending  # pausa ANTES de executar
    report = controller.refuse("não autorizo")
    assert report.status is PlanStatus.FAILED
    assert report.task_run("T1").status.value == "SKIPPED"
    assert report.task_run("T1").result is None  # nunca chegou a rodar
    runs = [r for r in controller.audit_records()
            if r["tool"] == "run_pytest" and r["success"]]
    assert runs == []  # nenhuma execução aconteceu


def test_command_without_approval_flag_runs_directly(controller, ws):
    armed(controller, ws, AllowedCommand("printf", requires_approval=False))
    report = controller.run_plan(plan(task("T1", "printf", ["direto"])))
    assert report.status is PlanStatus.COMPLETED
    assert not controller.has_pending
    assert "direto" in (report.task_run("T1").result or "")


def test_without_terminal_permission_no_checkpoint_just_block(ws, tmp_path,
                                                               audit_file):
    permissions = PermissionManager()  # SEM TERMINAL
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=audit_file,
    )
    controller.add_workspace(str(ws))
    controller.enable_terminal(["mkdir"])
    report = controller.run_plan(plan(task("T1", "mkdir", ["negado"])))
    assert report.status is PlanStatus.FAILED  # bloqueado no porteiro
    assert not controller.has_pending  # sem checkpoint decorativo
    assert "TERMINAL" in (report.task_run("T1").error or "")
    assert not (ws / "negado").exists()
    gate = [r for r in controller.audit_records()
            if r["operation"] == "permission_gate"]
    assert gate and gate[-1]["success"] is False
    assert gate[-1]["requested_path"] == "."  # cwd registrado no gate


def test_command_outside_allowlist_never_asks_approval(controller, ws):
    armed(controller, ws, "printf")
    report = controller.run_plan(plan(task("T1", "mkdir", ["fora"])))
    assert report.status is PlanStatus.FAILED
    assert not controller.has_pending
    assert "allowlist" in (report.task_run("T1").error or "")


# --------------------------------------- plano programático → Executor
def test_plan_with_multiple_checkpoints_approves_each(controller, ws):
    armed(controller, ws, "mkdir", "printf")
    controller.run_plan(plan(
        task("T1", "printf", ["etapa-1"]),
        task("T2", "mkdir", ["etapa-2"], order=2, dependencies=("T1",)),
    ))
    assert controller.has_pending and controller.pending_approval()["task_id"] == "T1"
    controller.approve("1ª ok")
    assert controller.has_pending and controller.pending_approval()["task_id"] == "T2"
    assert not (ws / "etapa-2").exists()  # T2 bloqueada até a decisão
    report = controller.approve("2ª ok")
    assert report.status is PlanStatus.COMPLETED
    assert (ws / "etapa-2").exists()


def test_mixed_plan_filesystem_and_terminal_share_checkpoints(controller, ws,
                                                              permissions):
    """Plano misto: create_file pausa (0.5) e run_command pausa (0.6)."""
    controller.add_workspace(str(ws), writable=True)
    permissions.grant("WRITE")
    controller.enable_terminal(["printf"])
    mixed = Plan(
        id="PLN-6006", objective="misto", status=PlanStatus.READY,
        tasks=(
            PlannedTask(id="T1", description="cria arquivo", order=1,
                        tool="create_file",
                        parameters={"path": "gerado.txt", "content": "x"}),
            task("T2", "printf", ["feito"], order=2, dependencies=("T1",)),
        ),
    )
    controller.run_plan(mixed)
    assert controller.pending_approval()["tool"] == "create_file"
    controller.approve("arquivo ok")
    assert controller.pending_approval()["tool"] == "run_command"
    report = controller.approve("comando ok")
    assert report.status is PlanStatus.COMPLETED
    assert (ws / "gerado.txt").exists()


# --------------------------------------------------------------- auditoria
def test_audit_jsonl_contains_terminal_records_without_content(controller, ws,
                                                                audit_file):
    armed(controller, ws, AllowedCommand("printf", requires_approval=False))
    controller.run_plan(plan(task("T1", "printf", ["JSONL-AQUI"])))
    records = controller.audit_records()
    terminal = [r for r in records if r["tool"] == "run_command"]
    assert terminal, "esperado registro run_command na trilha"
    rec = terminal[-1]
    assert rec["operation"] == "run_command"
    assert rec["success"] is True
    assert rec["detail"]["exit_code"] == 0
    assert rec["detail"]["command"] == ["printf", "JSONL-AQUI"]
    assert rec["task_id"] == "T1" and rec["plan_id"] == "PLN-6006"
    assert "stdout" not in rec["detail"] and "stderr" not in rec["detail"]
    assert audit_file.exists()  # persistiu em JSONL


# ------------------------------------------------------------ controller API
def test_enable_disable_and_allow_command_api(controller, ws):
    controller.add_workspace(str(ws))
    assert controller.terminal_policy is None
    assert controller.enable_terminal(["printf"]) == ["printf"]
    assert controller.terminal_policy is not None
    info = controller.allow_command("git", requires_approval=False)
    assert info == {"name": "git", "requires_approval": False}
    with pytest.raises(ToolsControlError):
        controller.allow_command("sh")  # denylist permanente
    controller.disable_terminal()
    assert controller.terminal_policy is None
    # Sem terminal: run_command não registrada → falha honesta controlada
    report = controller.run_plan(plan(task("T1", "printf", ["x"])))
    assert report.status is PlanStatus.FAILED
    assert "não registrada" in (report.task_run("T1").error or "")


def test_enable_terminal_rejects_invalid_allowlist(controller):
    with pytest.raises(ToolsControlError):
        controller.enable_terminal(["powershell"])  # denylist no registro
    with pytest.raises(ToolsControlError):
        controller.enable_terminal(["git"], default_timeout_s=0)


def test_startup_registers_no_terminal_tool(controller, ws):
    """Sem enable_terminal não existe run_command (sem efeitos colaterais)."""
    controller.add_workspace(str(ws))
    names = [tool["name"] for tool in controller.build_registry().list_tools()]
    assert "run_command" not in names
    assert names == ["list_directory", "read_file", "write_file",
                     "create_file", "delete_file", "file_exists",
                     "search_files", "edit_file"]


def test_permission_gate_blocks_before_tool_code_via_handler(ws):
    sandbox = sandbox_for(ws)
    audit = FilesystemAudit()
    registry = ToolRegistry(PermissionManager())  # só CHAT
    registry.register(RunCommandTool(TerminalPolicy(["mkdir"]), sandbox, audit))
    handler = ToolTaskHandler(registry, audit=audit, plan_id="PLN-G")
    executor = PlanExecutor(plan(task("T1", "mkdir", ["gated"])), handler)
    executor.run_all()
    report = executor.report()
    assert report.status is PlanStatus.FAILED
    assert not (ws / "gated").exists()
    gate = [r for r in audit.to_dicts() if r["operation"] == "permission_gate"]
    assert gate, "bloqueio de permissão deve ser auditado"


# ---------------------------------------------------- auditoria anti-futuro
def _module_sources() -> dict[str, str]:
    sources: dict[str, str] = {}
    for path in sorted((PROJECT_ROOT / "app").rglob("*.py")):
        sources[str(path.relative_to(PROJECT_ROOT))] = path.read_text(
            encoding="utf-8"
        )
    return sources


def _imports_of(source: str) -> set[str]:
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            imports.update(alias.name for alias in node.names)
    return imports


def test_subprocess_exists_only_in_terminal_module():
    """Execução de processos é exclusiva de terminal.py + run_pytest.py.

    0.6: só ``app/tools/terminal.py``; 11D: ``app/tools/run_pytest.py``
    ganha subprocess **controlado** por design (spec 11D §4 — runner
    conhecido, sem shell, sandbox e timeout). Nenhum outro módulo pode
    importar subprocess.
    """
    allowed = {"app/tools/terminal.py", "app/tools/run_pytest.py"}
    offenders = [
        name for name, source in _module_sources().items()
        if name not in allowed and "subprocess" in _imports_of(source)
    ]
    assert offenders == []


def test_terminal_module_has_no_network_or_automation():
    """terminal.py: sem rede/automação — apenas subprocess controlado."""
    source = (PROJECT_ROOT / "app" / "tools" / "terminal.py").read_text(
        encoding="utf-8"
    )
    imports = _imports_of(source)
    for forbidden in ("socket", "urllib", "requests", "http.client", "ftplib",
                      "pyautogui", "pynput", "selenium", "mss", "shutil",
                      "ctypes"):
        assert forbidden not in imports, f"terminal.py importa {forbidden}"


def test_planner_executor_core_ai_memory_ui_stay_agnostic():
    """Núcleo agnóstico: sem app.tools/subprocess. A UI só conhece a
    fachada (app.tools.control) — nunca filesystem/terminal direto."""
    for package in ("planner", "executor", "core", "ai", "memory"):
        directory = PROJECT_ROOT / "app" / package
        for path in sorted(directory.rglob("*.py")):
            imports = _imports_of(path.read_text(encoding="utf-8"))
            assert not any(imp.startswith("app.tools") for imp in imports), path
            assert "subprocess" not in imports, path
    for path in sorted((PROJECT_ROOT / "app" / "ui").rglob("*.py")):
        imports = _imports_of(path.read_text(encoding="utf-8"))
        assert "subprocess" not in imports, path
        for imp in imports:
            if imp.startswith("app.tools"):
                assert imp == "app.tools.control", f"{path}: {imp}"
