"""Planner com ferramentas (0.6.3) — allowlist, protocolo e validação.

Cobre a FASE 2/3 da 0.6.3: o Planner emite ``tool``/``parameters`` SOMENTE
para ferramentas da allowlist; saída inválida do "LLM" vira falha
controlada (plano FAILED com motivo) — nunca execução parcial.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from app.ai.provider import ProviderError
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
        self.requests: list[dict] = []

    def chat(self, message, context=None, *, system_prompt=None, **kwargs):
        self.calls.append(system_prompt or "")
        self.requests.append({
            "message": message,
            "context": [dict(item) for item in context or []],
            "system_prompt": system_prompt,
            "options": dict(kwargs),
        })
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
        "web_search", "web_fetch", "web_research",
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
    "../fora.txt", "docs/../../fora.txt", "..\\fora.txt",
])
def test_protocol_rejects_paths_trying_to_escape_workspace(path):
    problem = validate_task_tool(
        "create_file", {"path": path, "content": "x"},
        build_catalog(include_terminal=False),
    )
    assert problem is not None and "workspace" in problem


@pytest.mark.parametrize("path", [
    "/workspace/nota.txt", "D:\\workspace\\nota.txt",
    "\\\\servidor\\workspace\\nota.txt",
])
def test_protocol_accepts_absolute_paths_for_sandbox_validation(path):
    assert validate_task_tool(
        "read_file", {"path": path}, build_catalog(include_terminal=False),
    ) is None


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
    result = make_planner(
        json.dumps({"type": "conversation"})
    ).create_tool_plan("olá")
    assert result.kind == "conversation"
    assert result.plan.tasks == ()  # nenhum plano, nenhuma tarefa


@pytest.mark.parametrize("content", [
    '{"status":"Operação realizada com sucesso.","message":"Estou funcionando."}',
    '{"type":"other","status":"ok"}',
])
def test_planner_rejects_valid_json_outside_protocol(content):
    result = make_planner(content).create_tool_plan("oi")
    assert result.kind == "invalid"
    assert result.plan.status is PlanStatus.FAILED
    assert result.plan.tasks == ()


def test_planner_rejects_extra_fields_on_conversation_result():
    result = make_planner(
        '{"type":"conversation","message":"resposta arbitrária"}'
    ).create_tool_plan("oi")
    assert result.kind == "invalid"
    assert result.plan.tasks == ()


def test_ollama_planner_requests_protocol_json_schema():
    class OllamaFixedProvider(FixedProvider):
        name = "ollama"

    provider = OllamaFixedProvider('{"type":"conversation"}')
    result = Planner(
        provider, catalog=build_catalog(include_terminal=False),
    ).create_tool_plan("oi")

    assert result.kind == "conversation"
    options = provider.requests[0]["options"]
    schema = options["json_schema"]
    assert "json_format" not in options
    assert len(schema["oneOf"]) == 2
    conversation, plan = schema["oneOf"]
    assert conversation["properties"]["type"]["const"] == "conversation"
    assert plan["properties"]["type"]["const"] == "plan"
    assert plan["required"] == ["type", "objective", "analysis", "tasks"]


def test_ollama_plan_only_schema_pins_explicit_read_to_catalog_tool():
    from types import SimpleNamespace
    from app.ai.ollama_provider import OllamaProvider

    requests = []
    planned = tool_json("read_file", {"path": r"D:\Nova pasta (2)\Teste.txt"})

    def transport(method, url, body, timeout):
        requests.append(json.loads(body))
        event = {
            "model": "qwen2.5-coder:7b",
            "message": {"content": planned},
            "done": True,
        }
        return iter([json.dumps(event).encode("utf-8") + b"\n"])

    provider = OllamaProvider(
        SimpleNamespace(
            model="qwen2.5-coder:7b", request_timeout=30,
            ollama_base_url="http://127.0.0.1:11434",
            ollama_keep_alive="5m", ollama_think=False,
        ),
        transport=transport,
    )
    result = Planner(
        provider, catalog=build_catalog(include_terminal=False),
    ).create_tool_plan(
        "Leia o arquivo Teste.txt", require_plan=True,
        required_tool="read_file",
    )

    assert result.kind == "plan"
    assert result.plan.tasks[0].tool == "read_file"
    assert result.plan.tasks[0].parameters == {
        "path": r"D:\Nova pasta (2)\Teste.txt",
    }
    schema = requests[0]["format"]
    assert "oneOf" not in schema
    assert schema["properties"]["type"]["const"] == "plan"
    assert (
        schema["properties"]["tasks"]["items"]["properties"]["tool"]["const"]
        == "read_file"
    )


def test_planner_provider_failure_is_invalid_and_has_no_tasks():
    class FailingProvider(FixedProvider):
        def chat(self, *args, **kwargs):
            raise ProviderError("falha simulada")

    result = Planner(
        FailingProvider(""), catalog=build_catalog(include_terminal=False),
    ).create_tool_plan("oi")
    assert result.kind == "invalid"
    assert result.plan.status is PlanStatus.FAILED
    assert result.plan.tasks == ()
    assert "falhou" in (result.reason or "")


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



def test_tool_planning_prompt_prioritizes_action_requests_and_real_evidence():
    provider = FixedProvider(tool_json(
        "create_file", {"path": "probe.txt", "content": "probe"},
    ))
    planner = Planner(provider, catalog=build_catalog(include_terminal=True))

    result = planner.create_tool_plan("Crie o arquivo probe.txt")

    assert result.kind == "plan"
    prompt = provider.calls[0]
    assert "REGRA PRIORITARIA DE CLASSIFICACAO" in prompt
    assert "NUNCA responda" in prompt
    assert "nao declare sucesso sem evidencia" in prompt
    assert "REA/Ghidra" in prompt
