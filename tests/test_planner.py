"""Testes do Planner (0.4 — fundação) — 100% offline.

O provedor é um fake que devolve JSON scriptado (ou levanta erros); a
memória usa diretórios temporários. Nenhum teste toca rede, arquivos do
sistema ou APIs reais.
"""
from __future__ import annotations

import json

import pytest

from app.ai.provider import (
    AIProvider,
    MissingApiKeyError,
    ModelNotConfiguredError,
    ProviderDependencyError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.ai.types import AIResponse, ResponseType
from app.memory.records import MemoryKind
from app.memory.system import MemorySystem
from app.planner import (
    Plan,
    PlanStatus,
    PlannedTask,
    PlannedTaskStatus,
    Planner,
)


# ------------------------------------------------------------------ fakes
class FakePlanProvider(AIProvider):
    """Provedor falso: devolve conteúdo scriptado e registra as chamadas."""

    name = "fake-plan"

    def __init__(self, content: str = ""):
        self._content = content
        self.calls: list[dict] = []

    def generate(self, message, context=None):  # pragma: no cover
        return self._content

    def chat(self, message, context=None, *, system_prompt=None,
             on_delta=None, max_tokens=None):
        self.calls.append({
            "message": message,
            "context": [dict(item) for item in (context or [])],
            "system_prompt": system_prompt,
        })
        if isinstance(self._content, Exception):
            raise self._content
        return AIResponse(
            content=self._content, model="fake",
            response_type=ResponseType.FINAL_RESPONSE,
        )


def plan_json(tasks, analysis=(), objective="Objetivo"):
    return json.dumps(
        {"objective": objective, "analysis": list(analysis), "tasks": tasks},
        ensure_ascii=False,
    )


GOOD_TASKS = [
    {"id": 1, "description": "Entender os requisitos do sistema", "dependencies": []},
    {"id": 2, "description": "Analisar a estrutura atual do projeto", "dependencies": [1]},
    {"id": 3, "description": "Definir a estrutura de dados necessária", "dependencies": [2]},
    {"id": 4, "description": "Implementar o sistema", "dependencies": [3]},
    {"id": 5, "description": "Implementar as recompensas em pontos", "dependencies": [4]},
    {"id": 6, "description": "Compilar e testar posteriormente", "dependencies": [5]},
]


# ------------------------------------------------------------------ modelos
def test_plan_statuses_exist():
    assert {s.value for s in PlanStatus} == {
        "PLANNING", "READY", "RUNNING", "BLOCKED", "FAILED", "COMPLETED",
    }


def test_plan_defaults_to_planning():
    plan = Plan(id="PLN-0001", objective="fazer algo")
    assert plan.status is PlanStatus.PLANNING
    assert plan.tasks == () and plan.analysis == () and plan.error is None


def test_planned_task_has_full_contract():
    task = PlannedTask(id="T1", description="descrever", order=1)
    # campos mínimos exigidos pela spec 0.4
    for field in ("id", "description", "order", "dependencies", "status",
                  "result", "error"):
        assert hasattr(task, field)
    assert task.dependencies == ()
    assert task.status is PlannedTaskStatus.PENDING  # nada é executado
    assert task.result is None and task.error is None


def test_plan_task_by_id_and_to_dict():
    task = PlannedTask(id="T2", description="etapa", order=2, dependencies=("T1",))
    plan = Plan(id="PLN-0001", objective="obj", status=PlanStatus.READY,
                tasks=(task,))
    assert plan.task_by_id("T2") is task
    assert plan.task_by_id("T9") is None
    data = plan.to_dict()
    assert data["status"] == "READY"
    assert data["tasks"][0]["dependencies"] == ["T1"]


# ------------------------------------------------------------- criação de plano
def test_valid_plan_becomes_ready_with_ordered_tasks():
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    plan = Planner(provider).create_plan("criar sistema de níveis")
    assert plan.status is PlanStatus.READY
    assert plan.ready
    assert plan.error is None
    assert [t.order for t in plan.tasks] == [1, 2, 3, 4, 5, 6]
    assert [t.id for t in plan.tasks] == ["T1", "T2", "T3", "T4", "T5", "T6"]
    assert plan.objective == "criar sistema de níveis"


def test_dependencies_mapped_to_canonical_ids():
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    plan = Planner(provider).create_plan("objetivo")
    assert plan.tasks[1].dependencies == ("T1",)
    assert plan.tasks[5].dependencies == ("T5",)
    assert plan.tasks[0].dependencies == ()


def test_analysis_is_preserved():
    provider = FakePlanProvider(
        plan_json(GOOD_TASKS, analysis=["verificar a estrutura do projeto",
                                        "confirmar o tipo de recompensa"]))
    plan = Planner(provider).create_plan("objetivo")
    assert plan.analysis == ("verificar a estrutura do projeto",
                             "confirmar o tipo de recompensa")


def test_all_tasks_pending_nothing_executed():
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    plan = Planner(provider).create_plan("objetivo")
    assert all(t.status is PlannedTaskStatus.PENDING for t in plan.tasks)
    assert all(t.result is None and t.error is None for t in plan.tasks)


def test_plan_ids_are_sequential_per_planner():
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    planner = Planner(provider)
    assert planner.create_plan("a").id == "PLN-0001"
    assert planner.create_plan("b").id == "PLN-0002"


def test_prompt_demands_json_and_forbids_execution():
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    Planner(provider).create_plan("objetivo")
    prompt = " ".join(provider.calls[0]["system_prompt"].split())
    assert "JSON" in prompt
    assert "NADA será executado agora" in prompt


def test_objective_and_context_forwarded_to_provider():
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    context = [{"role": "user", "content": "contexto anterior"}]
    Planner(provider).create_plan("meu objetivo", context)
    call = provider.calls[0]
    assert call["message"] == "meu objetivo"
    assert call["context"] == [{"role": "user", "content": "contexto anterior"}]


# ------------------------------------------------------------------ tolerância
def test_json_inside_code_fences_is_parsed():
    fenced = "```json\n" + plan_json(GOOD_TASKS) + "\n```"
    plan = Planner(FakePlanProvider(fenced)).create_plan("objetivo")
    assert plan.status is PlanStatus.READY


def test_json_with_surrounding_text_is_parsed():
    noisy = "Claro! Aqui está o plano:\n" + plan_json(GOOD_TASKS) + "\nEspero ajudar."
    plan = Planner(FakePlanProvider(noisy)).create_plan("objetivo")
    assert plan.status is PlanStatus.READY


def test_string_and_numeric_ids_accepted_and_remapped():
    tasks = [
        {"id": "2", "description": "primeira (id estranho)", "dependencies": []},
        {"id": "1", "description": "segunda depende da primeira", "dependencies": ["2"]},
    ]
    plan = Planner(FakePlanProvider(plan_json(tasks))).create_plan("objetivo")
    assert plan.status is PlanStatus.READY
    assert plan.tasks[0].id == "T1"          # ordem de listagem vira canônica
    assert plan.tasks[1].dependencies == ("T1",)


# ------------------------------------------------------------------ planos inválidos
@pytest.mark.parametrize("content,fragment", [
    ("eco: olá, isso não é um plano", "não contém um objeto JSON"),
    ("", "vazia"),  # resposta vazia (tratada antes do parser)
    ('{"objective": "x", "analysis": [], "tasks": []}', "nenhuma tarefa"),
    ('{"objective": "x", "tasks": [{"id": 1, "description": ""}]}', "sem descrição"),
    ('{"tasks": [{"id": 1, "description": "ok", "dependencies": [7]}]}',
     "tarefa inexistente"),
    ('{"objective": "x", "analysis": "não sou lista", "tasks": [{"id": 1, "description": "ok"}]}',
     "analysis"),
])
def test_invalid_plans_fail_with_clear_reason(content, fragment):
    plan = Planner(FakePlanProvider(content)).create_plan("objetivo")
    assert plan.status is PlanStatus.FAILED
    assert plan.error and fragment in plan.error
    assert plan.tasks == ()


def test_circular_dependencies_are_rejected():
    tasks = [
        {"id": 1, "description": "a", "dependencies": [2]},
        {"id": 2, "description": "b", "dependencies": [1]},
    ]
    plan = Planner(FakePlanProvider(plan_json(tasks))).create_plan("objetivo")
    assert plan.status is PlanStatus.FAILED
    assert "ciclo" in plan.error


def test_self_dependency_is_rejected():
    tasks = [{"id": 1, "description": "a", "dependencies": [1]}]
    plan = Planner(FakePlanProvider(plan_json(tasks))).create_plan("objetivo")
    assert plan.status is PlanStatus.FAILED
    assert "ciclo" in plan.error


def test_duplicated_ids_are_rejected():
    tasks = [
        {"id": 1, "description": "a", "dependencies": []},
        {"id": 1, "description": "b", "dependencies": []},
    ]
    plan = Planner(FakePlanProvider(plan_json(tasks))).create_plan("objetivo")
    assert plan.status is PlanStatus.FAILED
    assert "duplicados" in plan.error


# ------------------------------------------------------------------ erros do provider
@pytest.mark.parametrize("exc", [
    MissingApiKeyError("LUMEN_API_KEY não configurada."),
    ModelNotConfiguredError("LUMEN_MODEL não configurado."),
    ProviderDependencyError("Dependência 'openai' não instalada."),
])
def test_environment_prerequisites_block_the_plan(exc):
    plan = Planner(FakePlanProvider(exc)).create_plan("objetivo")
    assert plan.status is PlanStatus.BLOCKED
    assert plan.error and "bloqueado" in plan.error.lower()
    assert plan.tasks == ()


@pytest.mark.parametrize("exc", [
    ProviderRateLimitError("429"),
    ProviderTimeoutError("timeout"),
])
def test_provider_failures_fail_the_plan_without_raising(exc):
    plan = Planner(FakePlanProvider(exc)).create_plan("objetivo")
    assert plan.status is PlanStatus.FAILED
    assert "provedor" in plan.error.lower()


def test_unexpected_provider_error_is_controlled():
    plan = Planner(FakePlanProvider(ValueError("boom"))).create_plan("objetivo")
    assert plan.status is PlanStatus.FAILED
    assert "inesperado" in plan.error.lower()


def test_non_airesponse_return_fails_plan():
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    provider.chat = lambda *a, **k: "não sou AIResponse"  # type: ignore[assignment]
    plan = Planner(provider).create_plan("objetivo")
    assert plan.status is PlanStatus.FAILED
    assert "inesperado" in plan.error.lower()


# ------------------------------------------------------------------ memória (0.3)
def test_memory_hits_enrich_the_prompt(tmp_path):
    memory = MemorySystem(tmp_path)
    memory.remember(MemoryKind.KNOWLEDGE, "Sistema de níveis",
                    "XP acumulado sobe o nível e libera recompensa em pontos")
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    Planner(provider, memory=memory).create_plan("criar sistema de níveis")
    prompt = provider.calls[0]["system_prompt"]
    assert "Sistema de níveis" in prompt
    assert "KNOWLEDGE" in prompt


def test_memory_without_hits_adds_no_section(tmp_path):
    memory = MemorySystem(tmp_path)  # vazia
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    Planner(provider, memory=memory).create_plan("assunto sem relação")
    assert "Contexto relevante recuperado" not in provider.calls[0]["system_prompt"]


def test_planner_without_memory_works():
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    plan = Planner(provider, memory=None).create_plan("objetivo")
    assert plan.status is PlanStatus.READY
    assert "Contexto relevante recuperado" not in provider.calls[0]["system_prompt"]


def test_planner_never_writes_to_memory(tmp_path):
    memory = MemorySystem(tmp_path)
    memory.remember(MemoryKind.KNOWLEDGE, "Sistema de níveis", "contexto")
    before = memory.stats()
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    Planner(provider, memory=memory).create_plan("criar sistema de níveis")
    assert memory.stats() == before  # leitura apenas — nada gravado
    # e nenhum novo arquivo de domínio criado
    assert sorted(p.name for p in (tmp_path / "memory").glob("*.json")) == [
        "knowledge.json",
    ]


def test_broken_memory_does_not_break_planning(tmp_path):
    memory = MemorySystem(tmp_path)
    memory.remember(MemoryKind.KNOWLEDGE, "Sistema de níveis", "contexto")
    # corrompe o arquivo DEPOIS da montagem (visão em memória permanece)
    (tmp_path / "memory" / "knowledge.json").write_text(
        "[{isto não é um registro}]", encoding="utf-8"
    )
    provider = FakePlanProvider(plan_json(GOOD_TASKS))
    plan = Planner(provider, memory=memory).create_plan("objetivo")
    assert plan.status is PlanStatus.READY  # memória é opcional no fluxo


# ------------------------------------------------------------------ entrada
def test_empty_objective_raises_value_error():
    with pytest.raises(ValueError):
        Planner(FakePlanProvider()).create_plan("   ")


def test_max_memory_hits_validation():
    with pytest.raises(ValueError):
        Planner(FakePlanProvider(), max_memory_hits=0)
