"""Testes de integração do Planner (0.4) — offline.

Agent → Planner (provider fake) → memória 0.3, incluindo a garantia de
que **nenhum comando real é executado** e que o fluxo de conversa da
0.2/0.3 permanece intacto.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import main as lumen_main
from app.ai.mock import MockProvider
from app.ai.provider import AIProvider
from app.ai.types import AIResponse, ResponseType
from app.config.secrets import FileSecretStore
from app.config.settings import Settings
from app.core.agent import Agent
from app.memory.records import MemoryKind
from app.memory.store import MemoryStore
from app.memory.system import MemorySystem
from app.planner import PlanStatus, PlannedTaskStatus
from app.security.permissions import PermissionDeniedError, PermissionManager


class FakePlanProvider(AIProvider):
    name = "fake-plan"

    def __init__(self, content: str):
        self._content = content
        self.calls: list[dict] = []

    def generate(self, message, context=None):  # pragma: no cover
        return self._content

    def chat(self, message, context=None, *, system_prompt=None,
             on_delta=None, max_tokens=None):
        self.calls.append({"message": message, "system_prompt": system_prompt})
        return AIResponse(content=self._content, model="fake",
                          response_type=ResponseType.FINAL_RESPONSE)


PLAN_JSON = json.dumps({
    "objective": "Sistema de evolução de níveis",
    "analysis": ["verificar a estrutura do projeto"],
    "tasks": [
        {"id": 1, "description": "Entender os requisitos", "dependencies": []},
        {"id": 2, "description": "Analisar a estrutura atual", "dependencies": [1]},
        {"id": 3, "description": "Implementar o sistema", "dependencies": [2]},
    ],
}, ensure_ascii=False)


def make_agent(provider=None, memory_system=None, permissions=True,
               tmp_path=None) -> Agent:
    return Agent(
        provider=provider or MockProvider(),
        memory=MemoryStore(Path(tmp_path or ".") / "conversation.json"),
        permissions=PermissionManager() if permissions else None,
        memory_system=memory_system,
    )


# ------------------------------------------------------- Agent → Planner
def test_agent_request_plan_returns_ready_plan(tmp_path):
    fake = FakePlanProvider(PLAN_JSON)
    agent = make_agent(fake, tmp_path=tmp_path)
    plan = agent.request_plan(
        "Lumen, crie um sistema de evolução de níveis com recompensa em pontos.")
    assert plan.status is PlanStatus.READY
    assert len(plan.tasks) == 3
    assert plan.tasks[1].dependencies == ("T1",)
    assert all(t.status is PlannedTaskStatus.PENDING for t in plan.tasks)


def test_request_plan_requires_chat_permission(tmp_path):
    from app.security.permissions import PermissionLevel, PermissionManager as PM

    permissions = PM()
    permissions.revoke(PermissionLevel.CHAT)  # única permissão concedida por padrão
    agent = make_agent(FakePlanProvider(PLAN_JSON), tmp_path=tmp_path)
    agent._permissions = permissions
    with pytest.raises(PermissionDeniedError):
        agent.request_plan("qualquer objetivo")


def test_request_plan_rejects_empty_text(tmp_path):
    agent = make_agent(tmp_path=tmp_path)
    with pytest.raises(ValueError):
        agent.request_plan("   ")


def test_planning_does_not_touch_conversation_memory(tmp_path):
    fake = FakePlanProvider(PLAN_JSON)
    agent = make_agent(fake, tmp_path=tmp_path)
    before = agent.memory.count
    agent.request_plan("objetivo do plano")
    assert agent.memory.count == before  # planejamento não é conversa


def test_chat_flow_still_works_after_planning(tmp_path):
    fake = FakePlanProvider(PLAN_JSON)
    agent = make_agent(fake, tmp_path=tmp_path)
    plan = agent.request_plan("objetivo")
    assert plan.ready
    reply = agent.send_message("Olá Lumen")
    assert reply.strip()
    assert agent.memory.count >= 2  # conversa segue gravando normalmente


def test_planner_uses_current_provider_after_runtime_swap(tmp_path):
    agent = make_agent(MockProvider(), tmp_path=tmp_path)
    blocked_or_failed = agent.request_plan("objetivo")
    assert blocked_or_failed.status is PlanStatus.FAILED  # mock não devolve JSON

    fake = FakePlanProvider(PLAN_JSON)
    agent.set_provider(fake)
    plan = agent.request_plan("objetivo")
    assert plan.status is PlanStatus.READY
    assert fake.calls  # o planner usou o provider vigente


def test_agent_with_structured_memory_enriches_planning(tmp_path):
    memory = MemorySystem(tmp_path)
    memory.remember(MemoryKind.PROJECT, "Jogo de fazenda",
                    "projeto Unreal com sistema de níveis em C++")
    fake = FakePlanProvider(PLAN_JSON)
    agent = make_agent(fake, memory_system=memory, tmp_path=tmp_path)
    agent.request_plan("sistema de níveis")
    assert "Jogo de fazenda" in fake.calls[0]["system_prompt"]
    # memória estruturada permanece intacta (leitura apenas)
    assert memory.stats()["PROJECT"] == 1


def test_agent_memory_system_property_default_none(tmp_path):
    agent = make_agent(tmp_path=tmp_path)
    assert agent.memory_system is None
    fake = FakePlanProvider(PLAN_JSON)
    agent.set_provider(fake)
    plan = agent.request_plan("objetivo")  # funciona sem memória estruturada
    assert plan.status is PlanStatus.READY


# ------------------------------------------------------------- build_app (0.4)
def test_build_app_wires_memory_system_without_side_effects(tmp_path, monkeypatch):
    monkeypatch.setattr(lumen_main, "create_secret_store",
                        lambda data_dir: FileSecretStore(data_dir))
    agent, service = lumen_main.build_app(Settings(data_dir=tmp_path))
    assert isinstance(agent.memory_system, MemorySystem)
    # montagem sem efeitos colaterais: nenhum arquivo de domínio criado
    assert list((tmp_path / "memory").glob("*.json")) == []
    # e o modo conversa segue idêntico (mock, sem chave)
    config = service.current_config()
    assert config["provider"] == "mock" and config["key_source"] == "nenhuma"


def test_build_app_request_plan_fails_controlled_with_mock(tmp_path, monkeypatch):
    monkeypatch.setattr(lumen_main, "create_secret_store",
                        lambda data_dir: FileSecretStore(data_dir))
    agent, _ = lumen_main.build_app(Settings(data_dir=tmp_path))
    plan = agent.request_plan("crie um sistema de inventário")
    assert plan.status is PlanStatus.FAILED  # MockProvider não produz JSON
    assert plan.error  # motivo claro, sem traceback
    # nenhuma tarefa executada e nenhum arquivo de memória criado
    assert list((tmp_path / "memory").glob("*.json")) == []


# ------------------------------------------------- garantia: nada é executado
FORBIDDEN_TOKENS = (
    "subprocess", "os.system", "os.exec", "popen", "shutil", "ctypes",
    "pyautogui", "pynput", "pytesseract", "opencv", "win32api",
    "send_keys", "click(", "move(", "scroll(", "PyMouse", "PyKeyboard",
    "unreal", "editor",  # Unreal/editor automation
)


def _planner_sources() -> str:
    root = Path(__file__).parent.parent / "app" / "planner"
    parts = [p.read_text(encoding="utf-8") for p in sorted(root.glob("*.py"))]
    return "\n".join(parts)


def test_planner_package_contains_no_execution_code():
    source = _planner_sources()
    lowered = source.lower()
    for token in FORBIDDEN_TOKENS:
        assert token.lower() not in lowered, f"planner não deve conter {token!r}"


def test_planner_module_has_no_file_write_calls():
    source = _planner_sources()
    for token in ("write_text", "write_bytes", "open(", "mkdir", "unlink",
                  "rename(", "os.replace"):
        assert token not in source, f"planner não deve escrever arquivos ({token!r})"


def test_planned_tasks_are_never_executed_by_agent(tmp_path):
    fake = FakePlanProvider(PLAN_JSON)
    agent = make_agent(fake, tmp_path=tmp_path)
    plan = agent.request_plan("objetivo")
    assert plan.ready
    assert all(t.status is PlannedTaskStatus.PENDING for t in plan.tasks)
    assert all(t.result is None for t in plan.tasks)  # nada "executado"


def test_agent_has_no_tool_dispatch():
    """Nenhum dispatcher de ferramentas existe no Agent (0.5+)."""
    import inspect

    from app.core import agent as agent_module

    source = inspect.getsource(agent_module)
    for token in ("ToolRegistry", "execute_tool", "dispatch", "run_command"):
        assert token not in source
