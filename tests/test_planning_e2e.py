"""Fluxo completo Fase 1 + Fase 2 + execução real (teste de ponta a ponta).

Prova que o caminho pedido no objetivo realmente funciona:

    objetivo → pesquisa (mock) → plano → aprovação → arquivos criados no disco

Usa as ferramentas de filesystem **reais** do LUMEN, com workspace real em
``tmp_path``, e passa pela cadeia de segurança existente (permissões →
sandbox → checkpoint). Nada é mockado exceto o provedor de LLM e a busca.

O ponto central destes testes é a **fronteira de autoridade**: sem
aprovação, nenhum arquivo aparece no disco.
"""
from __future__ import annotations

import json

import pytest

from app.ai.types import AIResponse
from app.planning import ApprovalGate, FeaturePlanner, PlanNotApprovedError
from app.planning.planner import extract_research_blocks
from app.research.models import SearchResult, WebSearchResponse
from app.research.tool import WebSearchTool
from app.research.client import TavilySearchProvider
from app.security.permissions import PermissionLevel, PermissionManager
from app.tools.control import ToolsController

OBJECTIVE = "crie um sistema de inventário para RPG em mundo aberto, usando C++ e Blueprints"

PLAN_PAYLOAD = {
    "summary": "Componente de inventário em C++ com UDataAsset para definição de itens [1].",
    "artifacts": [
        {
            "path": "Source/MeuJogo/Public/InventoryComponent.h",
            "kind": "create",
            "description": "Declara UInventoryComponent com TArray de FInventorySlot [1]",
            "language": "cpp",
            "content": "#pragma once\n\n#include \"CoreMinimal.h\"\n#include \"Components/ActorComponent.h\"\n"
                       "#include \"InventoryComponent.generated.h\"\n\n"
                       "UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))\n"
                       "class MEUJOGO_API UInventoryComponent : public UActorComponent\n{\n"
                       "    GENERATED_BODY()\npublic:\n"
                       "    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category=\"Inventory\")\n"
                       "    int32 MaxSlots = 20;\n};\n",
        },
        {
            "path": "Source/MeuJogo/Private/InventoryComponent.cpp",
            "kind": "create",
            "description": "Implementação do componente [1]",
            "language": "cpp",
            "content": "#include \"InventoryComponent.h\"\n",
        },
    ],
    "commands": [
        {
            "argv": ["UnrealBuildTool", "-projectfiles", "-project=MeuJogo.uproject"],
            "description": "Regenera os project files para incluir os novos headers",
            "timeout_s": 600,
            "is_build": True,
        }
    ],
    "validation_steps": ["Compilar no editor e confirmar ausência de erros de UHT"],
    "risks": ["A macro MEUJOGO_API depende do nome do módulo no Build.cs"],
}


class FakeProvider:
    name = "fake"
    model_name = "fake-planner-1"

    def __init__(self, payload):
        self._text = payload if isinstance(payload, str) else json.dumps(payload)
        self.prompts: list[str] = []

    def chat(self, message, context=None, *, system_prompt=None, on_delta=None, max_tokens=None):
        self.prompts.append(message)
        return AIResponse(content=self._text, model=self.model_name)


def tavily_stub(results):
    body = json.dumps({"results": list(results)}).encode()

    def transport(method, url, payload, headers, timeout):
        return 200, body

    return TavilySearchProvider(api_key="tvly-test", transport=transport)


SEARCH_RESULTS = [
    {
        "title": "Inventory Systems in UE5",
        "url": "https://dev.epicgames.com/community/learning/inventory",
        "content": "Use UActorComponent with a TArray<FInventorySlot> and BlueprintReadWrite.",
        "score": 0.95,
    },
    {
        "title": "UDataAsset for item definitions",
        "url": "https://dev.epicgames.com/documentation/udataasset",
        "content": "Define UPrimaryDataAsset subclasses for each item archetype.",
        "score": 0.88,
    },
]


def drive_to_completion(controller, plan, *, approve=True, max_steps=20):
    """Executa aprovando (ou recusando) cada checkpoint destrutivo.

    O LUMEN pausa em cada operação destrutiva: aprovar o PLANO (Fase 2)
    não é aprovar as OPERAÇÕES. O loop abaixo simula o usuário decidindo
    em cada pausa — que é exatamente o comportamento pretendido.
    """
    report = controller.run_plan(plan)
    decisions = []
    for _ in range(max_steps):
        if controller.pending_approval() is None:
            break
        decisions.append(controller.pending_approval()["tool"])
        report = controller.approve(note="ok") if approve else controller.refuse(reason="não")
    return report, decisions


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "project"
    (root / "Source" / "MeuJogo").mkdir(parents=True)
    return root


@pytest.fixture
def controller(tmp_path, workspace):
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.CHAT)
    permissions.grant(PermissionLevel.READ)
    permissions.grant(PermissionLevel.WRITE)
    permissions.grant(PermissionLevel.TERMINAL)
    c = ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )
    c.add_workspace(str(workspace), writable=True)
    # Terminal é opt-in explícito, com allowlist: exatamente como o
    # integrador do LUMEN liga `run_command`. O binário do Unreal não
    # existe neste sandbox Linux — o que importa aqui é que o comando
    # atravessa o portão de checkpoint e chega ao executor.
    c.enable_terminal(["UnrealBuildTool"])
    return c


# ---------------------------------------------------------------- pesquisa
def test_research_step_produces_citable_evidence():
    tool = WebSearchTool(tavily_stub(SEARCH_RESULTS))

    result = tool.run(query="unreal engine 5 inventory system c++ UDataAsset")

    assert result.ok is True
    block = extract_research_blocks([result.data])[0]
    assert "[1]" in block
    assert "https://dev.epicgames.com/community/learning/inventory" in block
    assert "[2]" in block


def test_research_evidence_is_reachable_from_the_response_object():
    provider = tavily_stub(SEARCH_RESULTS)
    response: WebSearchResponse = provider.search("q")
    assert len(response.results) == 2
    assert isinstance(response.results[0], SearchResult)


# ------------------------------------------------- planejar → aprovar → executar
def test_full_flow_creates_the_files_on_disk(controller, workspace):
    """O caminho completo: pesquisa → plano → aprovação → arquivos no disco."""
    # 1. pesquisa
    evidence = extract_research_blocks([WebSearchTool(tavily_stub(SEARCH_RESULTS)).run(
        query="ue5 inventory component"
    ).data])

    # 2. planejamento (LLM fake)
    planner = FeaturePlanner(FakeProvider(PLAN_PAYLOAD))
    plan = planner.create_plan(OBJECTIVE, research=evidence)
    assert len(plan.artifacts) == 2

    # 3. aprovação
    gate = ApprovalGate()
    gate.submit(plan)
    approved = gate.approve(plan.plan_id, note="ok, pode criar")

    # 4. conversão para o formato executável e execução pela cadeia real
    planner_plan = approved.to_planner_plan()
    report = controller.run_plan(planner_plan)

    # 5. SEGUNDO PORTÃO: o checkpoint do LUMEN pausa antes de escrever.
    #    A aprovação da Fase 2 autoriza o PLANO; o checkpoint autoriza
    #    cada OPERAÇÃO destrutiva. São gates independentes — a camada
    #    nova não encurta a cadeia de segurança existente.
    header = workspace / "Source" / "MeuJogo" / "Public" / "InventoryComponent.h"
    assert not header.exists(), "nada pode ser escrito antes do checkpoint"
    pending = controller.pending_approval()
    assert pending is not None, "esperado um checkpoint pedindo aprovação"
    assert pending["tool"] == "create_directory", (
        "o primeiro checkpoint deve ser a criação do diretório pai"
    )
    assert pending["status"] == "PENDING_APPROVAL"

    # 6. o usuário libera os checkpoints até o plano terminar
    report, decisions = drive_to_completion(controller, planner_plan)

    # 7. TODA operação destrutiva passou por checkpoint, na ordem do plano
    assert decisions == [
        "create_directory",   # Source/MeuJogo/Public
        "create_file",        # InventoryComponent.h
        "create_directory",   # Source/MeuJogo/Private
        "create_file",        # InventoryComponent.cpp
        "run_command",        # UnrealBuildTool
    ], decisions

    # 8. os arquivos existem, com o conteúdo revisado e aprovado
    source = workspace / "Source" / "MeuJogo" / "Private" / "InventoryComponent.cpp"
    assert header.is_file(), f"esperado {header}"
    assert source.is_file(), f"esperado {source}"
    text = header.read_text(encoding="utf-8")
    assert "UInventoryComponent" in text
    assert "UPROPERTY(EditAnywhere, BlueprintReadWrite" in text
    # O comentário de briefing não pode vazar para o código gerado
    assert "[1]" not in text
    assert report is not None

    # Nada escapou do workspace
    assert not (workspace.parent / "outside").exists()


def test_refusing_the_checkpoint_writes_nothing(controller, workspace):
    """Recusar o checkpoint garante que nenhum arquivo é criado."""
    plan = FeaturePlanner(FakeProvider(PLAN_PAYLOAD)).create_plan(OBJECTIVE)
    gate = ApprovalGate()
    gate.submit(plan)
    approved = gate.approve(plan.plan_id)

    report, _ = drive_to_completion(
        controller, approved.to_planner_plan(), approve=False
    )

    header = workspace / "Source" / "MeuJogo" / "Public" / "InventoryComponent.h"
    assert not header.exists()
    assert (workspace / "Source" / "MeuJogo").exists(), "diretório pai já não pôde subir"


def test_without_approval_nothing_is_written(controller, workspace):
    """A fronteira de autoridade: plano pendente não toca o disco."""
    plan = FeaturePlanner(FakeProvider(PLAN_PAYLOAD)).create_plan(OBJECTIVE)

    with pytest.raises(PlanNotApprovedError):
        plan.to_planner_plan()

    assert not (workspace / "Source" / "MeuJogo" / "Public").exists()


def test_rejected_plan_writes_nothing(controller, workspace):
    plan = FeaturePlanner(FakeProvider(PLAN_PAYLOAD)).create_plan(OBJECTIVE)
    gate = ApprovalGate()
    gate.submit(plan)

    rejected = gate.reject(plan.plan_id, reason="não quero sobrescrever nada")

    with pytest.raises(PlanNotApprovedError):
        rejected.to_planner_plan()
    assert not (workspace / "Source" / "MeuJogo" / "Public" / "InventoryComponent.h").exists()


def test_plan_requires_read_permission_for_research(controller):
    """Sem READ, a própria pesquisa é bloqueada — o plano não nasce."""
    from app.security.permissions import PermissionDeniedError

    controller.disable_read() if hasattr(controller, "disable_read") else None
    permissions = PermissionManager()  # só CHAT
    registry = WebSearchTool(tavily_stub(SEARCH_RESULTS))
    # A tool em si não aplica a permissão — quem aplica é o registry:
    from app.tools.base import ToolRegistry

    gated = ToolRegistry(permissions)
    gated.register(registry)
    with pytest.raises(PermissionDeniedError):
        gated.execute("web_search", query="q")


def test_write_without_permission_is_blocked_and_no_file_appears(tmp_path, workspace):
    """Plano aprovado, mas sem permissão WRITE → bloqueio real, sem arquivo."""
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.CHAT)
    permissions.grant(PermissionLevel.READ)  # sem WRITE
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "w.json",
        audit_file=tmp_path / "a.jsonl",
        terminal_file=tmp_path / "t.json",
    )
    controller.add_workspace(str(workspace), writable=True)

    plan = FeaturePlanner(FakeProvider(PLAN_PAYLOAD)).create_plan(OBJECTIVE)
    gate = ApprovalGate()
    gate.submit(plan)
    approved = gate.approve(plan.plan_id)

    controller.run_plan(approved.to_planner_plan())

    assert not (workspace / "Source" / "MeuJogo" / "Public" / "InventoryComponent.h").exists()


def test_plan_never_escapes_the_workspace(controller, workspace, tmp_path):
    """Mesmo aprovado, um path com '..' não passa da validação do plano."""
    from app.planning import FeaturePlanningError

    evil = {
        "artifacts": [
            {
                "path": "../outside/evil.cpp",
                "kind": "create",
                "content": "malicioso",
            }
        ],
        "commands": [],
    }
    planner = FeaturePlanner(FakeProvider(evil))

    with pytest.raises(FeaturePlanningError, match="inválido"):
        planner.create_plan("escapar do workspace")

    assert not (tmp_path / "outside").exists()


def test_digest_is_stable_across_the_flow(controller, workspace):
    plan = FeaturePlanner(FakeProvider(PLAN_PAYLOAD)).create_plan(OBJECTIVE)
    gate = ApprovalGate()
    gate.submit(plan)
    approved = gate.approve(plan.plan_id)

    assert approved.digest == plan.digest
    assert approved.to_planner_plan().id == plan.plan_id


def test_plan_id_is_used_as_the_lumen_plan_id(controller):
    plan = FeaturePlanner(FakeProvider(PLAN_PAYLOAD)).create_plan(OBJECTIVE)
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve(plan.plan_id).to_planner_plan()
    assert planner_plan.id == plan.plan_id


def test_build_command_survives_conversion_as_argv(controller):
    plan = FeaturePlanner(FakeProvider(PLAN_PAYLOAD)).create_plan(OBJECTIVE)
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve(plan.plan_id).to_planner_plan()

    command_task = [t for t in planner_plan.tasks if t.tool == "run_command"][0]
    assert command_task.parameters["command"] == "UnrealBuildTool"
    assert command_task.parameters["args"] == [
        "-projectfiles", "-project=MeuJogo.uproject"
    ]


def test_artifacts_are_created_before_commands_run(controller):
    """Ordem: arquivos primeiro, comando de build depois."""
    plan = FeaturePlanner(FakeProvider(PLAN_PAYLOAD)).create_plan(OBJECTIVE)
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve(plan.plan_id).to_planner_plan()

    tools = [t.tool for t in planner_plan.tasks]
    assert tools.index("create_directory") < tools.index("create_file")
    assert tools.index("create_file") < tools.index("run_command")


def test_prompt_receives_objective_and_evidence_together():
    provider = FakeProvider(PLAN_PAYLOAD)
    evidence = extract_research_blocks([WebSearchTool(tavily_stub(SEARCH_RESULTS)).run(
        query="q"
    ).data])

    FeaturePlanner(provider).create_plan(OBJECTIVE, research=evidence)

    prompt = provider.prompts[0]
    assert OBJECTIVE in prompt
    assert "EVIDÊNCIAS DE PESQUISA" in prompt
    assert "inventory" in prompt.lower()
