"""Testes de integração das ferramentas de filesystem (Lumen 0.5).

Cobrem a cadeia completa — Planner (modelos) → Executor → TaskHandler →
ToolRegistry → ferramentas reais — com diretórios temporários, além das
garantias de segurança/auditoria e das auditorias anti-futuro.
"""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from app.ai.provider import AIProvider
from app.ai.types import AIResponse, ResponseType
from app.core.agent import Agent
from app.executor import PlanExecutor
from app.executor.handlers import HandlerError
from app.memory.store import MemoryStore
from app.planner.models import Plan, PlanStatus, PlannedTask
from app.planner.planner import Planner
from app.security.permissions import PermissionDeniedError, PermissionManager
from app.tools.base import ToolRegistry
from app.tools.filesystem import (
    FILESYSTEM_DESTRUCTIVE_TOOLS,
    FilesystemAudit,
    WorkspaceSandbox,
    build_filesystem_registry,
)
from app.tools.handler import ToolCheckpoints, ToolTaskHandler

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ helpers
def tool_task(task_id: str, order: int, tool: str, parameters: dict,
              dependencies: tuple[str, ...] = ()) -> PlannedTask:
    return PlannedTask(
        id=task_id, description=f"{tool} {parameters.get('path', '')}",
        order=order, dependencies=dependencies, tool=tool, parameters=parameters,
    )


def ready_plan(objective: str, *tasks: PlannedTask) -> Plan:
    return Plan(id="PLN-9001", objective=objective, status=PlanStatus.READY,
                tasks=tasks)


class FakePlanProvider(AIProvider):
    """Provider offline que devolve um JSON de plano válido."""

    name = "fake-plan"

    def __init__(self, content: str) -> None:
        self._content = content

    def generate(self, message, context=None):  # pragma: no cover
        return self._content

    def chat(self, message, context=None, *, system_prompt=None,
             on_delta=None, max_tokens=None):
        return AIResponse(content=self._content, model="fake",
                          response_type=ResponseType.FINAL_RESPONSE)


PLAN_JSON = """{
  "objective": "organizar arquivos de trabalho",
  "analysis": ["verificar conteúdo atual"],
  "tasks": [
    {"description": "listar o diretório de trabalho"},
    {"description": "criar um arquivo de notas"},
    {"description": " conferir o resultado"}
  ]
}"""


def make_chain(root: Path, *, levels: tuple[str, ...] = ("READ", "WRITE"),
               writable: bool = True, allow_delete: bool = True):
    permissions = PermissionManager()
    for level in levels:
        permissions.grant(level)
    audit = FilesystemAudit()
    sandbox = WorkspaceSandbox([root], writable=writable, allow_delete=allow_delete)
    registry = build_filesystem_registry(permissions, sandbox, audit)
    handler = ToolTaskHandler(registry, audit=audit, plan_id="PLN-9001")
    return permissions, audit, registry, handler


# --------------------------------------------- modelos do Planner (0.5 fields)
def test_planned_task_tool_fields_are_optional_and_serialized():
    plain = PlannedTask(id="T1", description="etapa", order=1)
    assert plain.tool is None and plain.parameters is None
    data = plain.to_dict()
    assert data["tool"] is None and data["parameters"] is None
    armed = PlannedTask(id="T2", description="escrever", order=2,
                        tool="write_file", parameters={"path": "a.txt"})
    assert armed.to_dict()["tool"] == "write_file"


def test_planner_protocol_still_produces_description_only_tasks():
    plan = Planner(FakePlanProvider(PLAN_JSON)).create_plan("organizar arquivos")
    assert plan.status is PlanStatus.READY
    assert all(task.tool is None for task in plan.tasks)  # planner não emite tools


# --------------------------------------------------- Registry → Handler → Executor
def test_full_chain_executes_real_filesystem_operations(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _permissions, _audit, _registry, handler = make_chain(root)
    plan = ready_plan(
        "trabalhar com arquivos",
        tool_task("T1", 1, "create_file", {"path": "notas.md", "content": "# Notas"}),
        tool_task("T2", 2, "write_file",
                  {"path": "notas.md", "content": "# Notas\nconteúdo novo"},
                  dependencies=("T1",)),
        tool_task("T3", 3, "read_file", {"path": "notas.md"}, dependencies=("T2",)),
    )
    executor = PlanExecutor(plan, handler)
    report = executor.run_all()
    assert report.completed
    assert [run.status.value for run in report.tasks] == ["DONE", "DONE", "DONE"]
    # arquivo REAL criado e sobrescrito no disco
    assert (root / "notas.md").read_text(encoding="utf-8") == "# Notas\nconteúdo novo"
    # resultado estruturado preservado no TaskRun
    read_result = json.loads(report.task_run("T3").result)
    assert read_result["ok"] is True
    assert read_result["data"]["content"] == "# Notas\nconteúdo novo"
    write_result = json.loads(report.task_run("T2").result)
    assert write_result["data"]["overwritten"] is True


def test_task_without_tool_fails_honestly_instead_of_faking(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _p, _a, _r, handler = make_chain(root)
    plan = ready_plan("sem ferramenta", PlannedTask(id="T1", description="algo",
                                                    order=1))
    executor = PlanExecutor(plan, handler)
    report = executor.run_all()
    assert report.status is PlanStatus.FAILED
    run = report.task_run("T1")
    assert run.status.value == "FAILED"
    assert "não designa ferramenta" in run.error


def test_planner_produced_plan_is_not_fake_executed_by_tool_handler(tmp_path):
    """Plano do Planner (só descrições) + handler de ferramentas: falha
    honesta por tarefa — nenhuma execução fantasma."""
    root = tmp_path / "ws"
    root.mkdir()
    _p, _a, _r, handler = make_chain(root)
    plan = Planner(FakePlanProvider(PLAN_JSON)).create_plan("organizar arquivos")
    executor = PlanExecutor(plan, handler)
    report = executor.run_all()
    assert report.status is PlanStatus.FAILED
    assert all(run.status.value in ("FAILED", "SKIPPED") for run in report.tasks)
    assert "não designa ferramenta" in report.tasks[0].error
    assert list(root.iterdir()) == []  # nada foi criado


def test_unknown_tool_fails_controlled(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _p, _a, _r, handler = make_chain(root)
    plan = ready_plan("ferramenta fantasma",
                      tool_task("T1", 1, "rocket_launcher", {"path": "x"}))
    report = PlanExecutor(plan, handler).run_all()
    assert report.status is PlanStatus.FAILED
    assert "não registrada" in report.task_run("T1").error


# ------------------------------------------------------------ segurança na cadeia
def test_missing_permission_blocks_task_and_executes_nothing(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _p, audit, _r, handler = make_chain(root, levels=())  # sem READ/WRITE
    plan = ready_plan("escrever sem permissão",
                      tool_task("T1", 1, "create_file",
                                {"path": "segredo.txt", "content": "x"}))
    report = PlanExecutor(plan, handler).run_all()
    assert report.status is PlanStatus.FAILED
    error = report.task_run("T1").error
    assert "bloqueada" in error and "WRITE" in error
    assert not (root / "segredo.txt").exists()  # bloqueado, não executado
    gate = [r for r in audit.to_dicts() if r["operation"] == "permission_gate"]
    assert gate and gate[0]["success"] is False and gate[0]["tool"] == "create_file"


def test_sandbox_escape_via_task_parameters_is_blocked(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _p, _a, _r, handler = make_chain(root)
    plan = ready_plan("escape",
                      tool_task("T1", 1, "write_file",
                                {"path": "../../fora-do-workspace.txt",
                                 "content": "vazamento"}))
    report = PlanExecutor(plan, handler).run_all()
    assert report.status is PlanStatus.FAILED
    assert "traversal" in report.task_run("T1").error
    assert not (tmp_path / "fora-do-workspace.txt").exists()
    assert list(root.iterdir()) == []  # nada dentro do workspace também


def test_read_only_policy_blocks_write_task(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _p, _a, _r, handler = make_chain(root, writable=False)
    plan = ready_plan("escrita negada",
                      tool_task("T1", 1, "write_file",
                                {"path": "negado.txt", "content": "x"}))
    report = PlanExecutor(plan, handler).run_all()
    assert report.status is PlanStatus.FAILED
    assert "somente leitura" in report.task_run("T1").error
    assert not (root / "negado.txt").exists()


def test_delete_task_respects_double_opt_in(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "velho.txt").write_text("lixo", encoding="utf-8")
    plan = ready_plan("limpeza",
                      tool_task("T1", 1, "delete_file", {"path": "velho.txt"}))
    _p, _a, _r, blocked_handler = make_chain(root, allow_delete=False)
    blocked = PlanExecutor(plan, blocked_handler).run_all()
    assert blocked.status is PlanStatus.FAILED
    assert "allow_delete" in blocked.task_run("T1").error
    assert (root / "velho.txt").exists()
    _p2, _a2, _r2, allowed_handler = make_chain(root, allow_delete=True)
    allowed = PlanExecutor(plan, allowed_handler).run_all()
    assert allowed.completed and not (root / "velho.txt").exists()


# ----------------------------------------------------------------- checkpoints
def test_checkpoint_pauses_before_destructive_write_and_resumes(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "ex.txt").write_text("original", encoding="utf-8")
    _p, _a, _r, handler = make_chain(root)
    plan = ready_plan(
        "escrever com consentimento",
        tool_task("T1", 1, "read_file", {"path": "ex.txt"}),
        tool_task("T2", 2, "write_file",
                  {"path": "ex.txt", "content": "novo"}, dependencies=("T1",)),
    )
    executor = PlanExecutor(plan, handler,
                            checkpoints=ToolCheckpoints(FILESYSTEM_DESTRUCTIVE_TOOLS))
    assert executor.step().id == "T1"          # leitura roda sem checkpoint
    assert executor.step() is None              # pausa antes da escrita
    assert executor.paused
    pending = executor.pending_checkpoint
    assert pending.task_id == "T2" and pending.status.value == "PENDING_APPROVAL"
    assert (root / "ex.txt").read_text(encoding="utf-8") == "original"  # não executou
    executor.approve_checkpoint("ok")
    assert executor.step().status.value == "DONE"
    assert (root / "ex.txt").read_text(encoding="utf-8") == "novo"
    report = executor.report()
    assert report.completed
    assert report.checkpoints[0].status.value == "APPROVED"


def test_checkpoint_refusal_blocks_destructive_operation(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _p, _a, _r, handler = make_chain(root)
    plan = ready_plan("escrita recusada",
                      tool_task("T1", 1, "create_file",
                                {"path": "perigoso.txt", "content": "x"}))
    executor = PlanExecutor(plan, handler,
                            checkpoints=ToolCheckpoints(FILESYSTEM_DESTRUCTIVE_TOOLS))
    assert executor.step() is None and executor.paused
    executor.refuse_checkpoint("não autorizo")
    report = executor.report()
    assert report.status is PlanStatus.FAILED
    assert report.task_run("T1").status.value == "SKIPPED"
    assert not (root / "perigoso.txt").exists()   # nada rodou sem consentimento


def test_edit_file_checkpoint_approved_edits_file(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "ex.txt").write_text("titulo\nversao alpha\nfim\n", encoding="utf-8")
    _p, _a, _r, handler = make_chain(root)
    plan = ready_plan(
        "editar com consentimento",
        tool_task("T1", 1, "edit_file",
                  {"path": "ex.txt", "expected_old_text": "versao alpha",
                   "new_text": "versao beta"}),
    )
    executor = PlanExecutor(plan, handler,
                            checkpoints=ToolCheckpoints(FILESYSTEM_DESTRUCTIVE_TOOLS))
    assert executor.step() is None and executor.paused   # pausa ANTES de editar
    pending = executor.pending_checkpoint
    assert pending.task_id == "T1" and pending.status.value == "PENDING_APPROVAL"
    assert (root / "ex.txt").read_text(encoding="utf-8") == \
        "titulo\nversao alpha\nfim\n"                      # nada foi escrito ainda
    executor.approve_checkpoint("ok")
    assert executor.step().status.value == "DONE"
    assert (root / "ex.txt").read_text(encoding="utf-8") == \
        "titulo\nversao beta\nfim\n"                       # edição aplicada
    report = executor.report()
    assert report.completed
    assert report.checkpoints[0].status.value == "APPROVED"


def test_edit_file_checkpoint_refused_does_not_edit_file(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    original = "titulo\nversao alpha\nfim\n"
    (root / "ex.txt").write_text(original, encoding="utf-8")
    _p, _a, _r, handler = make_chain(root)
    plan = ready_plan(
        "edição recusada",
        tool_task("T1", 1, "edit_file",
                  {"path": "ex.txt", "expected_old_text": "versao alpha",
                   "new_text": "versao beta"}),
    )
    executor = PlanExecutor(plan, handler,
                            checkpoints=ToolCheckpoints(FILESYSTEM_DESTRUCTIVE_TOOLS))
    assert executor.step() is None and executor.paused   # checkpoint pendente
    executor.refuse_checkpoint("não autorizo")
    report = executor.report()
    assert report.status is PlanStatus.FAILED
    assert report.task_run("T1").status.value == "SKIPPED"
    assert (root / "ex.txt").read_text(encoding="utf-8") == original  # intacto


def test_tool_checkpoints_policy_targets_configured_tools():
    policy = ToolCheckpoints({"delete_file"})
    assert policy.requires_checkpoint(
        PlannedTask(id="T1", description="d", order=1, tool="delete_file")
    ) is True
    assert policy.requires_checkpoint(
        PlannedTask(id="T2", description="d", order=2, tool="read_file")
    ) is False
    assert policy.requires_checkpoint(
        PlannedTask(id="T3", description="d", order=3)
    ) is False


# ------------------------------------------------------------------- auditoria
def test_audit_records_carry_task_and_plan_context(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _p, audit, _r, handler = make_chain(root)
    plan = ready_plan("auditoria",
                      tool_task("T1", 1, "create_file",
                                {"path": "a.txt", "content": "conteúdo-sensível"}))
    PlanExecutor(plan, handler).run_all()
    records = audit.to_dicts()
    assert records
    for record in records:
        assert record["task_id"] == "T1"
        assert record["plan_id"] == "PLN-9001"
        assert record["timestamp"]
        assert record["tool"] and record["operation"]
    # campos exigidos: caminho solicitado + resolvido + desfecho
    assert records[0]["requested_path"] == "a.txt"
    assert records[0]["resolved_path"] == str((root / "a.txt").resolve())
    assert records[0]["success"] is True
    # conteúdo sensível NUNCA vai para a auditoria
    assert "conteúdo-sensível" not in json.dumps(records, ensure_ascii=False)


# --------------------------------------------------------------- Agent (0.5)
def test_agent_executes_plan_with_filesystem_handler(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _p, _a, _r, handler = make_chain(root)
    agent = Agent(provider=FakePlanProvider("ok"),
                  memory=MemoryStore(tmp_path / "conversation.json"))
    plan = ready_plan("via Agent",
                      tool_task("T1", 1, "create_file",
                                {"path": "agente.txt", "content": "feito"}))
    report = agent.execute_plan(plan, handler=handler)
    assert report.completed
    assert (root / "agente.txt").read_text(encoding="utf-8") == "feito"
    # conversa e memória intocadas pela execução
    assert agent.memory.count == 0


# ------------------------------------------------- auditorias anti-futuro (AST)
def _sources(package: str) -> dict[str, str]:
    directory = PROJECT_ROOT / "app" / package
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(directory.glob("*.py"))
    }


def _identifiers_and_imports(source: str) -> tuple[set[str], set[str]]:
    tree = ast.parse(source)
    identifiers: set[str] = set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
    return identifiers, imports


def test_planner_package_has_no_filesystem_or_tools_code():
    """O Planner NÃO ganha lógica de filesystem/ferramentas (0.5)."""
    for source in _sources("planner").values():
        identifiers, imports = _identifiers_and_imports(source)
        for forbidden in ("os", "pathlib", "shutil", "subprocess", "socket"):
            assert forbidden not in imports, f"planner não deve importar {forbidden}"
        assert not any(imp.startswith("app.tools") for imp in imports)
        assert "WorkspaceSandbox" not in identifiers
        assert "ToolRegistry" not in identifiers


def test_executor_package_still_free_of_tools_and_filesystem():
    """O núcleo do Executor permanece agnóstico (handler vive em app.tools)."""
    for name, source in _sources("executor").items():
        identifiers, imports = _identifiers_and_imports(source)
        assert not any(imp.startswith("app.tools") for imp in imports), name
        for token in ("WorkspaceSandbox", "ToolRegistry", "write_text", "read_text",
                      "unlink", "mkdir", "pathlib"):
            assert token not in identifiers, f"{name}: {token}"


def test_tools_modules_have_no_execution_or_network_code():
    """Filesystem/controle sem subprocess.

    0.6: ``terminal.py`` é a ÚNICA exceção autorizada; 11D:
    ``run_pytest.py`` ganha subprocess **controlado** (runner conhecido,
    sem shell, sandbox e timeout — spec 11D §4). Qualquer outro módulo
    continua proibido.
    """
    sources = _sources("tools")
    for name, source in sources.items():
        if name in ("terminal.py", "run_pytest.py"):
            continue  # módulos autorizados a usar subprocess (0.6/11D)
        identifiers, imports = _identifiers_and_imports(source)
        for forbidden in ("subprocess", "shutil", "ctypes", "socket", "urllib",
                          "requests", "pyautogui", "pynput", "selenium"):
            assert forbidden not in imports, f"{name} importa {forbidden}"
            assert forbidden not in identifiers, f"{name} usa {forbidden}"
        tokens = ("system", "popen", "Popen", "exec", "eval", "send_keys",
                  "click", "screenshot")
        # CC-5: computer_control.py é a fachada de Computer Control — precisa
        # referenciar driver.screenshot(...) via driver injetado (FakeDriver em
        # testes; o driver real vive fora de app/tools e não importa nenhuma lib
        # de OS/rede/automação, checado acima). Liberamos apenas o token
        # "screenshot"; tokens perigosos (exec/eval/system/popen/send_keys/click)
        # continuam proibidos.
        if name == "computer_control.py":
            tokens = ("system", "popen", "Popen", "exec", "eval", "send_keys", "click")
        for token in tokens:
            assert token not in identifiers, f"{name} usa {token}"


def test_agent_core_does_not_import_tools():
    source = inspect.getsource(__import__("app.core.agent", fromlist=["Agent"]))
    assert "app.tools" not in source  # integração acontece via handler injetado


def test_no_filesystem_side_effects_on_startup(tmp_path):
    """Importar/buildar a aplicação não cria nem toca arquivos fora de data/."""
    before = {p: p.stat().st_mtime for p in tmp_path.rglob("*") if p.is_file()}
    import main  # noqa: F401 — import não registra ferramentas

    from app.config.settings import Settings
    settings = Settings(provider="mock", data_dir=tmp_path / "data")
    settings.ensure_dirs()
    agent = main.build_agent(settings)
    assert agent.provider.name == "mock"
    after = {p: p.stat().st_mtime for p in tmp_path.rglob("*") if p.is_file()}
    # nenhum arquivo existente foi tocado; apenas data/ pode crescer
    for path, mtime in after.items():
        if path in before:
            assert path.stat().st_mtime == mtime
        else:
            assert "data" in path.parts
    # e nenhum registro global de ferramentas aconteceu
    assert ToolRegistry().list_tools() == []


def test_handler_error_contract_for_permission_denied(tmp_path):
    """PermissionDeniedError vira HandlerError (fail-fast controlado)."""
    root = tmp_path / "ws"
    root.mkdir()
    permissions = PermissionManager()  # só CHAT
    sandbox = WorkspaceSandbox([root], writable=True)
    registry = build_filesystem_registry(permissions, sandbox)
    handler = ToolTaskHandler(registry)
    task = tool_task("T1", 1, "read_file", {"path": "x.txt"})
    with pytest.raises(PermissionDeniedError):
        registry.execute("read_file", path="x.txt")
    with pytest.raises(HandlerError) as exc:
        handler.execute(task)
    assert "READ" in str(exc.value)
