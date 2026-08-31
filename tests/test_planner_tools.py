"""Planner com ferramentas (0.6.3) — allowlist, protocolo e validação.

Cobre a FASE 2/3 da 0.6.3: o Planner emite ``tool``/``parameters`` SOMENTE
para ferramentas da allowlist; saída inválida do "LLM" vira falha
controlada (plano FAILED com motivo) — nunca execução parcial.
"""
from __future__ import annotations

import dataclasses

import pytest

from app.ai.types import AIResponse, ResponseType
from app.planner.catalog import (
    build_catalog,
    catalog_prompt_section,
    spec_for,
    validate_task_tool,
)
from app.planner.models import PlanStatus
from app.planner.planner import Planner, ToolPlanResult


def tool_json(tool: str, parameters: dict, *, description: str = "etapa") -> str:
    import json

    return json.dumps({
        "type": "plan",
        "objective": "objetivo",
        "analysis": [],
        "tasks": [{
            "id": 1, "description": description, "dependencies": [],
            "tool": tool, "parameters": parameters,
        }],
    })


class FixedProvider:
    """Provedor fake que devolve um JSON fixo (simula LLM em modo plano)."""

    name = "fixed"

    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[str] = []

    def chat(self, message, context=None, *, system_prompt=None, **kwargs):
        self.calls.append(system_prompt or "")
        return AIResponse(
            content=self._content, model="fixed", usage=None,
            finish_reason="stop", response_type=ResponseType.FINAL_RESPONSE,
        )


def make_planner(content: str, *, terminal: bool = False) -> Planner:
    return Planner(
        FixedProvider(content),
        catalog=build_catalog(include_terminal=terminal),
    )


# ------------------------------------------------------------- allowlist
def test_catalog_lists_exactly_the_existing_tools():
    catalog = build_catalog(include_terminal=False)
    assert set(catalog) == {
        "list_directory", "read_file", "write_file",
        "create_file", "delete_file", "file_exists",
        "search_files", "edit_file",
    }


def test_catalog_omits_run_command_unless_terminal_enabled():
    without = build_catalog(include_terminal=False)
    with_terminal = build_catalog(include_terminal=True)
    # 11D: run_pytest segue a mesma regra de terminal que run_command.
    for name in ("run_command", "run_pytest"):
        assert name not in without
        assert name in with_terminal


def test_catalog_has_no_generic_or_invented_tool():
    catalog = build_catalog(include_terminal=True)
    for forbidden in ("execute_anything", "run_python", "run_shell",
                      "arbitrary_command", "powershell", "cmd"):
        assert forbidden not in catalog


def test_catalog_prompt_lists_names_and_parameters():
    section = catalog_prompt_section(build_catalog(include_terminal=False))
    for name in ("create_file", "write_file", "read_file"):
        assert name in section
    assert "path: string (obrigatório)" in section
    assert "content: string (obrigatório)" in section


def test_spec_for_returns_known_tools_only():
    assert spec_for("create_file") is not None
    assert spec_for("run_pytest") is not None  # 11D
    assert spec_for("execute_anything") is None


# ------------------------------------------------- validação de protocolo
@pytest.mark.parametrize("tool,parameters,expect_problem", [
    ("create_file", {"path": "a.txt", "content": "x"}, False),
    ("write_file", {"path": "a.txt", "content": "x"}, False),
    ("read_file", {"path": "a.txt"}, False),
    ("list_directory", {"path": "."}, False),
    ("delete_file", {"path": "a.txt"}, False),
    ("file_exists", {"path": "a.txt"}, False),
    ("run_command", {"command": "git", "args": ["status"]}, False),
    # 11D: run_pytest (tool de terminal — catálogo com terminal habilitado)
    ("run_pytest", {"path": "tests"}, False),
    ("run_pytest", {"path": "tests", "k": "smoke", "maxfail": 2,
                    "timeout_s": 120}, False),
    ("run_pytest", {}, True),                                    # sem path
    ("run_pytest", {"path": "tests", "maxfail": "2"}, True),     # não-int
    # tool vazia/ausente/fora da allowlist
    ("", {}, True),
    (None, None, True),
    ("execute_anything", {"cmd": "rm"}, True),
    ("Create_File", {"path": "a.txt", "content": "x"}, True),  # case exato
    # parâmetros: ausentes, desconhecidos, tipos errados
    ("create_file", {"path": "a.txt"}, True),                    # sem content
    ("create_file", None, True),                                 # sem params
    ("create_file", "texto", True),                              # não-objeto
    ("create_file", {"path": "a.txt", "content": "x", "modo": 7}, True),
    ("create_file", {"path": 42, "content": "x"}, True),         # path int
    ("create_file", {"path": "   ", "content": "x"}, True),      # vazio
    ("create_file", {"path": "a.txt", "content": ""}, True),     # vazio
    ("run_command", {"command": "git", "args": "status"}, True), # args não-lista
    ("run_command", {"command": "git", "args": [1, 2]}, True),   # não-str
    ("run_command", {}, True),                                   # sem command
])
def test_validate_task_tool_matrix(tool, parameters, expect_problem):
    problem = validate_task_tool(
        tool, parameters, build_catalog(include_terminal=True)
    )
    assert (problem is not None) is expect_problem
    if expect_problem:
        assert problem.strip()  # motivo claro, sempre


@pytest.mark.parametrize("path", [
    "/etc/passwd", "C:\\Windows\\system32\\x.txt", "\\\\servidor\\x",
    "../fora.txt", "docs/../../fora.txt", "..\\fora.txt",
])
def test_protocol_rejects_paths_trying_to_escape_workspace(path):
    problem = validate_task_tool(
        "create_file", {"path": path, "content": "x"},
        build_catalog(include_terminal=False),
    )
    assert problem is not None and "workspace" in problem


def test_protocol_accepts_relative_paths_inside_workspace():
    assert validate_task_tool(
        "create_file", {"path": "docs/sub/nota.txt", "content": "x"},
        build_catalog(include_terminal=False),
    ) is None


# ------------------------------------------------- Planner em modo tools
def test_planner_produces_tool_and_parameters():
    result = make_planner(tool_json(
        "create_file", {"path": "teste_lumen.txt", "content": "TESTE 0.6.3"},
    )).create_tool_plan("crie um arquivo")
    assert isinstance(result, ToolPlanResult) and result.kind == "plan"
    assert result.plan.status is PlanStatus.READY
    task = result.plan.tasks[0]
    assert task.tool == "create_file"
    assert task.parameters == {
        "path": "teste_lumen.txt", "content": "TESTE 0.6.3",
    }
    assert task.id == "T1" and task.order == 1


def test_planner_conversation_type_does_not_create_plan():
    import json

    result = make_planner(
        json.dumps({"type": "conversation"})
    ).create_tool_plan("olá")
    assert result.kind == "conversation"
    assert result.plan.tasks == ()  # nenhum plano, nenhuma tarefa


def test_planner_rejects_invented_tool_with_clear_reason():
    result = make_planner(tool_json("execute_anything", {"cmd": "rm"})) \
        .create_tool_plan("apague tudo")
    assert result.kind == "invalid"
    assert "allowlist" in (result.reason or "")
    assert result.plan.status is PlanStatus.FAILED  # falha controlada
    assert result.plan.tasks == ()


def test_planner_rejects_empty_and_missing_tool():
    import json

    no_tool = json.dumps({
        "type": "plan", "objective": "x", "analysis": [],
        "tasks": [{"id": 1, "description": "vaga", "dependencies": []}],
    })
    result = make_planner(no_tool).create_tool_plan("faça algo")
    assert result.kind == "invalid"
    assert "sem ferramenta" in (result.reason or "")


def test_planner_rejects_bad_parameters():
    result = make_planner(tool_json("create_file", {"path": "a.txt"})) \
        .create_tool_plan("crie a.txt")
    assert result.kind == "invalid"
    assert "ausente" in (result.reason or "")


def test_planner_rejects_out_of_protocol_response():
    result = make_planner("vou criar o arquivo, deixa comigo!") \
        .create_tool_plan("crie a.txt")
    assert result.kind == "invalid"
    assert result.plan.status is PlanStatus.FAILED


def test_planner_rejects_escape_path_in_tool_mode():
    result = make_planner(tool_json(
        "create_file", {"path": "../../fora.txt", "content": "x"},
    )).create_tool_plan("crie fora")
    assert result.kind == "invalid"
    assert "workspace" in (result.reason or "")


def test_planner_without_catalog_is_programming_error():
    with pytest.raises(ValueError):
        Planner(FixedProvider("{}")).create_tool_plan("x")


def test_tool_plan_is_immutable():
    result = make_planner(tool_json(
        "create_file", {"path": "a.txt", "content": "x"},
    )).create_tool_plan("crie a.txt")
    task = result.plan.tasks[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        task.tool = "write_file"
    with pytest.raises(dataclasses.FrozenInstanceError):
        task.parameters = {}


def test_tool_prompt_contains_allowlist_and_rules():
    planner = make_planner(tool_json("read_file", {"path": "a.txt"}))
    planner.create_tool_plan("leia a.txt")
    prompt = planner._provider.calls[0]
    assert "Allowlist de ferramentas disponiveis" in prompt
    assert "- create_file" in prompt and "- read_file" in prompt
    assert "run_command" not in prompt  # terminal não habilitado
    assert "run_pytest" not in prompt  # 11D: também tool de terminal
    assert "nunca invente" in prompt


def test_tool_prompt_includes_run_command_only_with_terminal():
    planner = make_planner(tool_json("read_file", {"path": "a.txt"}),
                           terminal=True)
    planner.create_tool_plan("leia a.txt")
    assert "- run_command" in planner._provider.calls[0]
    assert "- run_pytest" in planner._provider.calls[0]  # 11D
