"""Testes de integração do Executor (0.4.x) — offline.

Planner → Executor → Agent, com handlers simulados, garantindo que
nenhuma ferramenta real é executada e que os fluxos anteriores
(conversa, memória 0.3, providers) permanecem intactos.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from app.ai.mock import MockProvider
from app.ai.provider import AIProvider
from app.ai.types import AIResponse, ResponseType
from app.core.agent import Agent
from app.executor import (
    ExecutorError,
    PlanExecutor,
    SimulatedHandler,
)
from app.memory.records import MemoryKind
from app.memory.store import MemoryStore
from app.memory.system import MemorySystem
from app.planner import PlanStatus, PlannedTaskStatus
from app.planner.planner import Planner
from app.security.permissions import PermissionDeniedError, PermissionManager


class FakePlanProvider(AIProvider):
    name = "fake-plan"

    def __init__(self, content: str):
        self._content = content

    def generate(self, message, context=None):  # pragma: no cover
        return self._content

    def chat(self, message, context=None, *, system_prompt=None,
             on_delta=None, max_tokens=None):
        return AIResponse(content=self._content, model="fake",
                          response_type=ResponseType.FINAL_RESPONSE)


PLAN_JSON = json.dumps({
    "objective": "Sistema de evolução de níveis",
    "analysis": ["verificar a estrutura do projeto"],
    "tasks": [
        {"id": 1, "description": "Entender os requisitos", "dependencies": []},
        {"id": 2, "description": "Analisar a estrutura atual", "dependencies": [1]},
        {"id": 3, "description": "Implementar o sistema", "dependencies": [2]},
        {"id": 4, "description": "Implementar as recompensas", "dependencies": [3]},
    ],
}, ensure_ascii=False)


def make_agent(tmp_path, provider=None, memory_system=None) -> Agent:
    return Agent(
        provider=provider or MockProvider(),
        memory=MemoryStore(Path(tmp_path) / "conversation.json"),
        permissions=PermissionManager(),
        memory_system=memory_system,
    )


# --------------------------------------------------- Planner → Executor
def test_planner_plan_runs_end_to_end_with_simulated_handler():
    plan = Planner(FakePlanProvider(PLAN_JSON)).create_plan(
        "Lumen, crie um sistema de evolução de níveis com recompensa em pontos.")
    assert plan.status is PlanStatus.READY

    handler = SimulatedHandler()
    report = PlanExecutor(plan, handler).run_all()

    assert report.status is PlanStatus.COMPLETED
    assert handler.executed == ["T1", "T2", "T3", "T4"]       # ordem/dependências
    assert all(r.status is PlannedTaskStatus.DONE for r in report.tasks)
    assert report.task_run("T3").result.startswith("Simulado:")


def test_planner_failed_plan_cannot_be_executed():
    plan = Planner(FakePlanProvider("não sou um plano")).create_plan("x")
    assert plan.status is PlanStatus.FAILED
    with pytest.raises(ExecutorError):
        PlanExecutor(plan, SimulatedHandler()).run_all()


# --------------------------------------------------- Agent → Executor
def test_agent_execute_plan_returns_completed_report(tmp_path):
    agent = make_agent(tmp_path, FakePlanProvider(PLAN_JSON))
    plan = agent.request_plan("sistema de níveis")
    report = agent.execute_plan(plan)
    assert report.status is PlanStatus.COMPLETED
    assert len(report.tasks) == 4


def test_agent_execute_plan_with_failure(tmp_path):
    agent = make_agent(tmp_path, FakePlanProvider(PLAN_JSON))
    plan = agent.request_plan("sistema de níveis")
    report = agent.execute_plan(
        plan, handler=SimulatedHandler(failures={"T2": "ambiente sem X"}))
    assert report.status is PlanStatus.FAILED
    assert report.task_run("T2").status is PlannedTaskStatus.FAILED
    assert report.task_run("T4").status is PlannedTaskStatus.SKIPPED


def test_agent_execute_plan_requires_chat_permission(tmp_path):
    from app.security.permissions import PermissionLevel

    agent = make_agent(tmp_path, FakePlanProvider(PLAN_JSON))
    plan = agent.request_plan("objetivo")
    agent._permissions.revoke(PermissionLevel.CHAT)
    with pytest.raises(PermissionDeniedError):
        agent.execute_plan(plan)


def test_execution_does_not_touch_conversation_nor_memory(tmp_path):
    memory_system = MemorySystem(tmp_path)
    memory_system.remember(MemoryKind.KNOWLEDGE, "Níveis", "contexto prévio")
    agent = make_agent(tmp_path, FakePlanProvider(PLAN_JSON),
                       memory_system=memory_system)
    plan = agent.request_plan("sistema de níveis")
    conversation_before = agent.memory.count
    stats_before = memory_system.stats()

    report = agent.execute_plan(plan)

    assert report.completed
    assert agent.memory.count == conversation_before   # conversa intocada
    assert memory_system.stats() == stats_before       # memória 0.3 intocada
    assert list((tmp_path / "memory").glob("*.json")) == [tmp_path / "memory" / "knowledge.json"]


def test_chat_flow_unchanged_after_execution(tmp_path):
    agent = make_agent(tmp_path, FakePlanProvider(PLAN_JSON))
    plan = agent.request_plan("objetivo")
    agent.execute_plan(plan)
    reply = agent.send_message("Olá Lumen")
    assert reply.strip()
    assert agent.memory.count == 2  # user + assistant; plan/execução não gravaram


# ------------------------------------- 15. garantia: nenhuma ferramenta real
FORBIDDEN_IDENTIFIERS = (
    "subprocess", "popen", "shutil", "ctypes", "pyautogui", "pynput",
    "pytesseract", "cv2", "opencv", "win32api", "win32com", "send_keys",
    "unreal", "urllib", "requests", "socket", "system", "exec",
    "write_text", "write_bytes", "mkdir", "unlink",
)
FORBIDDEN_MODULES = (
    "subprocess", "shutil", "ctypes", "socket", "urllib", "requests",
    "pyautogui", "pynput", "os", "pathlib", "app.tools", "app.tools.base",
)


def _code_identifiers_and_imports(package: str):
    """Extrai (identificadores usados, módulos importados) via AST.

    Docstrings/comentários são ignorados — a auditoria é sobre o CÓDIGO.
    """
    import ast

    root = Path(__file__).parent.parent / "app" / package
    identifiers: set[str] = set()
    imports: set[str] = set()
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
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


def test_executor_package_contains_no_real_tool_code():
    identifiers, imports = _code_identifiers_and_imports("executor")
    for token in FORBIDDEN_IDENTIFIERS:
        assert token not in identifiers, f"executor não deve usar {token!r}"
    for module in FORBIDDEN_MODULES:
        assert module not in imports, f"executor não deve importar {module!r}"


def test_executor_does_not_import_tool_registry():
    """ToolRegistry segue vazio — o executor não despacha ferramentas."""
    identifiers, imports = _code_identifiers_and_imports("executor")
    assert "ToolRegistry" not in identifiers
    assert not any(imp.startswith("app.tools") for imp in imports)


def test_tool_registry_still_empty():
    from app.tools.base import ToolRegistry

    assert ToolRegistry().list_tools() == []


def test_agent_has_no_real_execution_paths():
    source = inspect.getsource(Agent)
    for token in ("subprocess", "os.system", "shutil", "pyautogui", "pynput"):
        assert token not in source


def test_simulated_handler_is_in_memory_only():
    handler = SimulatedHandler()
    task = next(iter(
        Planner(FakePlanProvider(PLAN_JSON)).create_plan("x").tasks))
    result = handler.execute(task)
    assert isinstance(result, str) and result
    # nenhum arquivo/tipo real envolvido: resultado é texto puro em memória
    assert result == f"Simulado: {task.description}"
