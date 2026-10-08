"""Planner/ToolCallingBridge integration tests for the UI-only tools.

All providers are deterministic fakes: no external search service or Unreal
Editor is contacted. These prove that natural-language objectives enter the
same planner path as the UI, that only the read-only Unreal allowlist reaches
its prompt/registry, and that results are returned to the chat.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.ai.types import AIResponse
from app.core.agent import Agent
from app.core.bridge import RequestState
from app.memory.store import MemoryStore
from app.research.models import SearchResult, WebSearchResponse
from app.security.permissions import PermissionDeniedError, PermissionLevel, PermissionManager
from app.tools.control import ToolsController

READ_ONLY_UNREAL = {
    "unreal_get_info",
    "unreal_describe_object",
    "unreal_search_assets",
}
MUTATING_UNREAL = {
    "unreal_create_blueprint_class",
    "unreal_add_component",
    "unreal_set_property",
    "unreal_call_function",
}


class FakeSearchProvider:
    name = "fake-search"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, *, max_results=5, timeout=30.0):
        self.queries.append(query)
        return WebSearchResponse(
            query=query,
            provider=self.name,
            results=(SearchResult(
                title="Remote Control API — Epic documentation",
                url="https://docs.example.test/remote-control",
                content="The API can search assets by query and package path.",
                score=0.98,
            ),),
        )


class FakeUnrealClient:
    config = SimpleNamespace(
        base_url="http://127.0.0.1:30010",
        transport="rc",
        python_enabled=False,
    )

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.mutating_calls: list[str] = []

    def info(self):
        self.calls.append(("info", (), {}))
        return {"HttpRoutes": [{"Path": "/remote/info"}, {"Path": "/remote/search/assets"}]}

    def search_assets(self, query, *, class_names=(), package_paths=()):
        self.calls.append(("search_assets", (query,), {
            "class_names": class_names, "package_paths": package_paths,
        }))
        return [{
            "Name": "BP_Player",
            "Class": "Blueprint",
            "Path": "/Game/Blueprints/BP_Player.BP_Player",
        }]

    def describe(self, object_path):
        self.calls.append(("describe", (object_path,), {}))
        return {
            "Name": "PlayerActor",
            "Class": "/Script/Engine.Actor",
            "Properties": [{"Name": "ActorLocation"}, {"Name": "bHidden"}],
            "Functions": [{"Name": "SetActorLocation"}],
        }

    # These methods must never be called by a UI read-only planner.
    def set_property(self, *args, **kwargs):
        self.mutating_calls.append("set_property")

    def call_function(self, *args, **kwargs):
        self.mutating_calls.append("call_function")

    def create_blueprint_class(self, *args, **kwargs):
        self.mutating_calls.append("create_blueprint_class")

    def add_component(self, *args, **kwargs):
        self.mutating_calls.append("add_component")


OBJECTIVES = (
    (
        "Pesquise na web a documentação oficial da Unreal Remote Control API "
        "sobre busca de assets.",
        "web_search",
        {"query": "Unreal Remote Control API search assets"},
        "https://docs.example.test/remote-control",
    ),
    (
        "Verifique se o Unreal Editor está conectado e quais rotas da Remote "
        "Control API estão disponíveis.",
        "unreal_get_info",
        {},
        "/remote/info",
    ),
    (
        "Busque no Content Browser o Blueprint BP_Player e informe o caminho.",
        "unreal_search_assets",
        {"query": "BP_Player", "class_names": ["Blueprint"]},
        "/Game/Blueprints/BP_Player.BP_Player",
    ),
    (
        "Descreva o objeto /Game/Maps/Main.Main:PersistentLevel.PlayerActor "
        "e liste propriedades e funções.",
        "unreal_describe_object",
        {"object_path": "/Game/Maps/Main.Main:PersistentLevel.PlayerActor"},
        "ActorLocation",
    ),
)


class ObjectiveAwareMockProvider:
    """Fake LLM que mapeia cada objetivo natural para seu plano esperado."""

    name = "objective-aware-mock"
    model_name = "objective-aware-mock-v1"

    def __init__(self, objective: str, tool: str, parameters: dict) -> None:
        self._objective = objective.casefold()
        self._tool = tool
        self._parameters = parameters
        self.calls: list[tuple[str, str]] = []

    def chat(self, message, context=None, *, system_prompt=None, **kwargs):
        self.calls.append((message, system_prompt or ""))
        assert message.casefold() == self._objective
        payload = {
            "type": "plan",
            "objective": message,
            "analysis": [],
            "tasks": [{
                "id": 1,
                "description": f"Consultar usando {self._tool}",
                "dependencies": [],
                "tool": self._tool,
                "parameters": self._parameters,
            }],
        }
        return AIResponse(content=json.dumps(payload), model=self.model_name)

    def generate(self, message, context=None):  # pragma: no cover - planner uses chat
        raise AssertionError("o fluxo de ação da UI deve chamar chat() do planner")


def make_controller(tmp_path, permissions):
    return ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )


@pytest.mark.parametrize("objective,tool,parameters,visible_result", OBJECTIVES)
def test_ui_natural_language_objectives_select_read_only_tools(
    tmp_path, objective, tool, parameters, visible_result,
):
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.READ)
    controller = make_controller(tmp_path, permissions)
    search = FakeSearchProvider()
    unreal = FakeUnrealClient()
    controller.enable_web_search(search)
    controller.enable_unreal_bridge(unreal, read_only_only=True)

    provider = ObjectiveAwareMockProvider(objective, tool, parameters)
    agent = Agent(
        provider=provider,
        memory=MemoryStore(tmp_path / "conversation.json"),
        permissions=permissions,
    )
    agent.set_tools_controller(controller)

    selected: list[str] = []
    run_plan = controller.run_plan

    def capture_plan(plan):
        selected.extend(task.tool for task in plan.tasks)
        return run_plan(plan)

    controller.run_plan = capture_plan
    outcome = agent.process_message(objective)

    assert outcome.state is RequestState.COMPLETED
    assert selected == [tool]
    assert visible_result in outcome.text
    assert not controller.has_pending  # read-only calls never ask for WRITE/checkpoint
    assert PermissionLevel.WRITE not in permissions.granted_levels()

    # The exact planner prompt uses the runtime catalog and cannot mention
    # any of the four mutating Unreal tools in this UI configuration.
    prompt = provider.calls[0][1]
    assert f"- {tool} —" in prompt
    assert "- web_search —" in prompt
    for forbidden in MUTATING_UNREAL:
        assert forbidden not in prompt

    registry_names = {item["name"] for item in controller.build_registry().list_tools()}
    assert READ_ONLY_UNREAL <= registry_names
    assert not (MUTATING_UNREAL & registry_names)
    assert not unreal.mutating_calls
    if tool == "web_search":
        assert search.queries == [parameters["query"]]
    else:
        assert unreal.calls and unreal.calls[0][0] == {
            "unreal_get_info": "info",
            "unreal_search_assets": "search_assets",
            "unreal_describe_object": "describe",
        }[tool]


def test_read_only_unreal_mode_is_fail_closed_and_still_requires_read(tmp_path):
    permissions = PermissionManager()
    controller = make_controller(tmp_path, permissions)
    unreal = FakeUnrealClient()
    controller.enable_unreal_bridge(unreal, read_only_only=True)

    catalog = controller.planning_catalog()
    assert READ_ONLY_UNREAL <= set(catalog)
    assert not (MUTATING_UNREAL & set(catalog))
    assert controller.unreal_bridge_read_only_only is True
    with pytest.raises(PermissionDeniedError):
        controller.build_registry().execute("unreal_get_info")

    controller.disable_unreal_bridge()
    assert not any(name.startswith("unreal_") for name in controller.planning_catalog())
    assert controller.unreal_bridge_read_only_only is False
