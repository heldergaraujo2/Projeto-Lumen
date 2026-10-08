"""Testes da camada de planejamento de feature (Fase 2).

Cobrem as três garantias centrais:
1. o gerador produz um plano estruturado válido a partir de objetivo+pesquisa;
2. o loop de aprovação bloqueia execução sem decisão explícita;
3. a conversão para o formato executável do LUMEN preserva a cadeia de
   segurança (nomes de tool e parâmetros corretos, caminhos seguros).

Nenhum teste usa rede: o provedor é sempre um fake em memória.
"""
from __future__ import annotations

import json

import pytest

from app.ai.types import AIResponse
from app.planning import (
    ApprovalGate,
    ApprovalStatus,
    ArtifactKind,
    FeaturePlan,
    FeaturePlanner,
    FeaturePlanningError,
    PlanArtifact,
    PlanCommand,
    PlanNotApprovedError,
    PlanningError,
    extract_research_blocks,
    render_markdown,
)
from app.planning.models import MAX_ARTIFACT_CONTENT_BYTES


# --------------------------------------------------------------------- fakes
class FakeProvider:
    """Provedor de teste: devolve um conteúdo programado e grava o prompt."""

    name = "fake"
    model_name = "fake-1"

    def __init__(self, content: str):
        self._content = content
        self.calls: list[dict] = []

    def chat(self, message, context=None, *, system_prompt=None, on_delta=None, max_tokens=None):
        self.calls.append({"message": message, "system_prompt": system_prompt})
        return AIResponse(content=self._content, model=self.model_name)


class BoomProvider:
    name = "boom"
    model_name = "boom-1"

    def chat(self, *args, **kwargs):
        raise RuntimeError("provider unreachable")


GOOD_PLAN = {
    "summary": "Componente de inventário em C++ com UDataAsset para itens.",
    "artifacts": [
        {
            "path": "Source/MeuJogo/Public/InventoryComponent.h",
            "kind": "create",
            "description": "Declara o componente de inventário [1]",
            "language": "cpp",
            "content": "#pragma once\n#include \"CoreMinimal.h\"\n",
        },
        {
            "path": "Source/MeuJogo/Private/InventoryComponent.cpp",
            "kind": "create",
            "description": "Implementa o componente [1]",
            "language": "cpp",
            "content": "#include \"InventoryComponent.h\"\n",
        },
    ],
    "commands": [
        {
            "argv": ["UnrealBuildTool", "-projectfiles", "-project=Proj.uproject"],
            "description": "Gera os project files",
            "timeout_s": 600,
            "is_build": True,
        }
    ],
    "validation_steps": ["Abrir o editor e confirmar compilação sem erros"],
    "risks": ["O caminho do engine varia por instalação"],
}


def provider_with(payload) -> FakeProvider:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return FakeProvider(text)


# ------------------------------------------------------------------- gerador
def test_planner_builds_plan_from_objective():
    planner = FeaturePlanner(provider_with(GOOD_PLAN))

    plan = planner.create_plan("crie um sistema de inventário para RPG")

    assert isinstance(plan, FeaturePlan)
    assert plan.objective == "crie um sistema de inventário para RPG"
    assert len(plan.artifacts) == 2
    assert len(plan.commands) == 1
    assert plan.summary.startswith("Componente de inventário")
    assert plan.provider == "fake"
    assert plan.model == "fake-1"


def test_planner_assigns_sequential_plan_ids():
    planner = FeaturePlanner(provider_with(GOOD_PLAN))
    first = planner.create_plan("a")
    second = planner.create_plan("b")
    assert first.plan_id == "FPL-0001"
    assert second.plan_id == "FPL-0002"


def test_planner_rejects_empty_objective():
    planner = FeaturePlanner(provider_with(GOOD_PLAN))
    with pytest.raises(ValueError, match="objetivo"):
        planner.create_plan("   ")


def test_planner_surfaces_provider_failure():
    planner = FeaturePlanner(BoomProvider())
    with pytest.raises(FeaturePlanningError, match="provedor"):
        planner.create_plan("qualquer coisa")


def test_planner_rejects_empty_provider_response():
    planner = FeaturePlanner(FakeProvider("   "))
    with pytest.raises(FeaturePlanningError, match="vazia"):
        planner.create_plan("x")


def test_planner_tolerates_markdown_code_fences():
    fenced = "```json\n" + json.dumps(GOOD_PLAN) + "\n```"
    plan = FeaturePlanner(provider_with(fenced)).create_plan("x")
    assert len(plan.artifacts) == 2


def test_planner_tolerates_surrounding_prose():
    noisy = "Claro! Aqui está o plano:\n" + json.dumps(GOOD_PLAN) + "\nEspero ter ajudado."
    plan = FeaturePlanner(provider_with(noisy)).create_plan("x")
    assert len(plan.commands) == 1


def test_planner_rejects_non_json_response():
    planner = FeaturePlanner(provider_with("desculpe, não consegui"))
    with pytest.raises(FeaturePlanningError, match="JSON"):
        planner.create_plan("x")


def test_planner_rejects_invalid_json():
    planner = FeaturePlanner(provider_with("{isso não é json}"))
    with pytest.raises(FeaturePlanningError, match="inválido"):
        planner.create_plan("x")


def test_planner_rejects_plan_without_artifacts_or_commands():
    planner = FeaturePlanner(provider_with({"summary": "nada"}))
    with pytest.raises(FeaturePlanningError, match="nem comandos"):
        planner.create_plan("x")


def test_planner_rejects_artifact_without_content():
    bad = {"artifacts": [{"path": "a.cpp", "kind": "create"}], "commands": []}
    planner = FeaturePlanner(provider_with(bad))
    with pytest.raises(FeaturePlanningError, match="content"):
        planner.create_plan("x")


def test_planner_rejects_absolute_path():
    bad = {
        "artifacts": [{"path": "C:/Windows/evil.cpp", "kind": "create", "content": "x"}],
        "commands": [],
    }
    planner = FeaturePlanner(provider_with(bad))
    with pytest.raises(FeaturePlanningError, match="inválido"):
        planner.create_plan("x")


def test_planner_rejects_parent_traversal():
    bad = {
        "artifacts": [{"path": "../../etc/passwd", "kind": "create", "content": "x"}],
        "commands": [],
    }
    planner = FeaturePlanner(provider_with(bad))
    with pytest.raises(FeaturePlanningError, match="inválido"):
        planner.create_plan("x")


def test_planner_rejects_string_argv():
    """argv como string seria um convite a injeção de shell."""
    bad = {
        "artifacts": [],
        "commands": [{"argv": "rm -rf / && echo done", "description": "x"}],
    }
    planner = FeaturePlanner(provider_with(bad))
    with pytest.raises(FeaturePlanningError, match="LISTA"):
        planner.create_plan("x")


def test_planner_rejects_unknown_artifact_kind():
    bad = {
        "artifacts": [{"path": "a.cpp", "kind": "delete", "content": "x"}],
        "commands": [],
    }
    planner = FeaturePlanner(provider_with(bad))
    with pytest.raises(FeaturePlanningError, match="kind"):
        planner.create_plan("x")


def test_planner_rejects_duplicate_artifact_paths():
    bad = {
        "artifacts": [
            {"path": "a.cpp", "kind": "create", "content": "1"},
            {"path": "a.cpp", "kind": "create", "content": "2"},
        ],
        "commands": [],
    }
    planner = FeaturePlanner(provider_with(bad))
    with pytest.raises(FeaturePlanningError, match="inválido"):
        planner.create_plan("x")


def test_planner_rejects_oversized_artifact():
    bad = {
        "artifacts": [
            {"path": "a.cpp", "kind": "create", "content": "x" * (MAX_ARTIFACT_CONTENT_BYTES + 1)}
        ],
        "commands": [],
    }
    planner = FeaturePlanner(provider_with(bad))
    with pytest.raises(FeaturePlanningError, match="inválido"):
        planner.create_plan("x")


def test_planner_caps_artifact_count():
    many = {
        "artifacts": [
            {"path": f"f{i}.cpp", "kind": "create", "content": "x"} for i in range(100)
        ],
        "commands": [],
    }
    plan = FeaturePlanner(provider_with(many), max_artifacts=5).create_plan("x")
    assert len(plan.artifacts) == 5


def test_planner_keeps_artifact_paths_in_order():
    plan = FeaturePlanner(provider_with(GOOD_PLAN)).create_plan("x")
    assert [a.path for a in plan.artifacts] == [
        "Source/MeuJogo/Public/InventoryComponent.h",
        "Source/MeuJogo/Private/InventoryComponent.cpp",
    ]


def test_planner_sends_artifact_bodies_verbatim():
    """O conteúdo revisado precisa chegar intacto ao disco."""
    plan = FeaturePlanner(provider_with(GOOD_PLAN)).create_plan("x")
    assert "#pragma once" in plan.artifacts[0].content


# -------------------------------------------------------------- prompt/pesq
def test_prompt_includes_research_evidence():
    provider = provider_with(GOOD_PLAN)
    planner = FeaturePlanner(provider)

    planner.create_plan("objetivo X", research=["[1] Fonte A\n    https://a.test"])

    prompt = provider.calls[-1]["message"]
    assert "EVIDÊNCIAS DE PESQUISA" in prompt
    assert "https://a.test" in prompt
    assert "objetivo X" in prompt


def test_prompt_omits_research_section_when_absent():
    provider = provider_with(GOOD_PLAN)
    FeaturePlanner(provider).create_plan("objetivo")
    assert "EVIDÊNCIAS DE PESQUISA" not in provider.calls[-1]["message"]


def test_prompt_truncates_huge_research():
    provider = provider_with(GOOD_PLAN)
    planner = FeaturePlanner(provider)

    planner.create_plan("x", research=["y" * 100_000])

    assert len(provider.calls[-1]["message"]) < 30_000
    assert "truncada" in provider.calls[-1]["message"]


def test_system_prompt_states_the_safety_rules():
    prompt = FeaturePlanner.system_prompt()
    assert "JSON" in prompt
    assert "argv" in prompt
    assert ".." in prompt  # proibição de traversal explicitada


def test_system_prompt_is_forwarded_to_provider():
    provider = provider_with(GOOD_PLAN)
    FeaturePlanner(provider).create_plan("x")
    assert provider.calls[-1]["system_prompt"] == FeaturePlanner.system_prompt()


def test_extract_research_blocks_accepts_dicts():
    blocks = extract_research_blocks(
        [{"query": "q", "results": [{"title": "T", "url": "https://a.test", "content": "c"}]}]
    )
    assert len(blocks) == 1
    assert "https://a.test" in blocks[0]
    assert "[1]" in blocks[0]


def test_extract_research_blocks_accepts_response_objects():
    from app.research.models import SearchResult, WebSearchResponse

    response = WebSearchResponse(
        query="q",
        provider="tavily",
        results=(SearchResult(title="T", url="https://a.test", content="c", score=0.5),),
    )
    blocks = extract_research_blocks([response])
    assert "https://a.test" in blocks[0]


def test_extract_research_blocks_ignores_none():
    assert extract_research_blocks([None, None]) == []


# ------------------------------------------------------------- approval gate
@pytest.fixture
def plan():
    return FeaturePlan(
        plan_id="FPL-0001",
        objective="criar inventário",
        artifacts=(PlanArtifact(path="a/b.cpp", content="int x;"),),
        commands=(PlanCommand(argv=("make", "all")),),
    )


def test_fresh_plan_is_pending(plan):
    assert plan.approval.status is ApprovalStatus.PENDING
    assert plan.is_approved is False


def test_gate_submit_returns_pending_copy(plan):
    gate = ApprovalGate()
    pending = gate.submit(plan)
    assert pending.approval.status is ApprovalStatus.PENDING
    assert gate.has_pending is True
    assert len(gate.pending()) == 1


def test_gate_approve_marks_approved(plan):
    gate = ApprovalGate()
    gate.submit(plan)

    approved = gate.approve("FPL-0001", note="ok")

    assert approved.is_approved is True
    assert approved.approval.decided_at is not None
    assert approved.approval.note == "ok"
    assert gate.has_pending is False


def test_gate_reject_marks_rejected_and_keeps_reason(plan):
    gate = ApprovalGate()
    gate.submit(plan)

    rejected = gate.reject("FPL-0001", reason="não quero esse arquivo")

    assert rejected.approval.status is ApprovalStatus.REJECTED
    assert "não quero" in rejected.approval.note


def test_rejected_plan_cannot_be_converted_for_execution(plan):
    gate = ApprovalGate()
    gate.submit(plan)
    rejected = gate.reject("FPL-0001", reason="no")

    with pytest.raises(PlanNotApprovedError):
        rejected.to_planner_plan()


def test_pending_plan_cannot_be_converted_for_execution(plan):
    gate = ApprovalGate()
    pending = gate.submit(plan)
    with pytest.raises(PlanNotApprovedError):
        pending.to_planner_plan()


def test_gate_rejects_unknown_plan_id():
    with pytest.raises(PlanningError, match="não está pendente"):
        ApprovalGate().approve("FPL-9999")


def test_gate_rejects_double_submission(plan):
    gate = ApprovalGate()
    gate.submit(plan)
    with pytest.raises(PlanningError, match="já está pendente"):
        gate.submit(plan)


def test_gate_rejects_deciding_twice(plan):
    gate = ApprovalGate()
    gate.submit(plan)
    gate.approve("FPL-0001")
    with pytest.raises(PlanningError, match="já foi decidido"):
        gate.reject("FPL-0001")


def test_gate_rejects_resubmission_after_decision(plan):
    gate = ApprovalGate()
    gate.submit(plan)
    gate.approve("FPL-0001")
    with pytest.raises(PlanningError, match="já foi decidido"):
        gate.submit(plan)


def test_gate_refuses_plan_that_arrives_pre_approved(plan):
    from app.planning.models import ApprovalRecord

    approved = plan.with_approval(
        ApprovalRecord(plan_id=plan.plan_id, status=ApprovalStatus.APPROVED)
    )
    with pytest.raises(PlanningError, match="já chega aprovado"):
        ApprovalGate().submit(approved)


def test_gate_records_history(plan):
    gate = ApprovalGate()
    gate.submit(plan)
    gate.approve("FPL-0001")

    assert len(gate.history()) == 1
    assert gate.history()[0].status is ApprovalStatus.APPROVED
    assert gate.decision_for("FPL-0001") is not None


def test_gate_can_expire_a_pending_plan(plan):
    gate = ApprovalGate()
    gate.submit(plan)
    expired = gate.expire("FPL-0001", reason="timeout")
    assert expired.approval.status is ApprovalStatus.EXPIRED


def test_gate_enforces_max_pending():
    gate = ApprovalGate(max_pending=1)
    gate.submit(FeaturePlan(plan_id="A", objective="a", artifacts=(
        PlanArtifact(path="a.cpp", content="x"),)))
    with pytest.raises(PlanningError, match="pendentes"):
        gate.submit(FeaturePlan(plan_id="B", objective="b", artifacts=(
            PlanArtifact(path="b.cpp", content="x"),)))


def test_approval_cannot_be_reused_on_another_plan(plan):
    other = FeaturePlan(plan_id="FPL-0002", objective="outro")
    with pytest.raises(PlanningError, match="não pertence"):
        other.with_approval(plan.approval)


def test_original_plan_is_not_mutated_by_approval(plan):
    """`with_approval` devolve cópia — o pendente original fica intacto."""
    gate = ApprovalGate()
    gate.submit(plan)
    gate.approve("FPL-0001")
    assert plan.approval.status is ApprovalStatus.PENDING


def test_gate_is_iterable_over_pending(plan):
    gate = ApprovalGate()
    gate.submit(plan)
    assert [p.plan_id for p in gate] == ["FPL-0001"]


# ------------------------------------------- conversão para execução LUMEN
def test_approved_plan_converts_to_planner_plan(plan):
    gate = ApprovalGate()
    gate.submit(plan)
    approved = gate.approve("FPL-0001")

    planner_plan = approved.to_planner_plan()

    assert planner_plan.objective == "criar inventário"
    # 1 diretório (pai de a/b.cpp) + 1 artefato + 1 comando
    assert len(planner_plan.tasks) == 3


def test_conversion_uses_existing_lumen_tool_names(plan):
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve("FPL-0001").to_planner_plan()

    tools = [task.tool for task in planner_plan.tasks]
    assert tools == ["create_directory", "create_file", "run_command"]


def test_conversion_creates_parent_directories_first():
    """create_file exige o pai existente — o plano precisa criá-lo antes."""
    plan = FeaturePlan(
        plan_id="P",
        objective="x",
        artifacts=(PlanArtifact(path="Source/G/Public/A.h", content="x"),),
    )
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve("P").to_planner_plan()

    assert [t.tool for t in planner_plan.tasks] == ["create_directory", "create_file"]
    assert planner_plan.tasks[0].parameters == {"path": "Source/G/Public"}


def test_conversion_deduplicates_shared_directories():
    """Dois arquivos na mesma pasta ⇒ um único create_directory."""
    plan = FeaturePlan(
        plan_id="P",
        objective="x",
        artifacts=(
            PlanArtifact(path="Src/A.h", content="1"),
            PlanArtifact(path="Src/B.h", content="2"),
        ),
    )
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve("P").to_planner_plan()

    tools = [t.tool for t in planner_plan.tasks]
    assert tools == ["create_directory", "create_file", "create_file"]


def test_conversion_skips_directory_for_root_level_file():
    """Arquivo na raiz não gera create_directory."""
    plan = FeaturePlan(
        plan_id="P",
        objective="x",
        artifacts=(PlanArtifact(path="README.md", content="x"),),
    )
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve("P").to_planner_plan()

    assert [t.tool for t in planner_plan.tasks] == ["create_file"]


def test_conversion_maps_artifact_parameters(plan):
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve("FPL-0001").to_planner_plan()

    artifact_task = [t for t in planner_plan.tasks if t.tool == "create_file"][0]
    assert artifact_task.parameters == {"path": "a/b.cpp", "content": "int x;"}


def test_conversion_splits_command_into_program_and_args():
    plan = FeaturePlan(
        plan_id="P",
        objective="build",
        commands=(PlanCommand(argv=("UnrealBuildTool", "-projectfiles", "-x")),),
    )
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve("P").to_planner_plan()

    params = [t for t in planner_plan.tasks if t.tool == "run_command"][0].parameters
    assert params["command"] == "UnrealBuildTool"
    assert params["args"] == ["-projectfiles", "-x"]


def test_conversion_write_kind_maps_to_write_file():
    plan = FeaturePlan(
        plan_id="P",
        objective="x",
        artifacts=(PlanArtifact(path="a.txt", content="x", kind=ArtifactKind.WRITE),),
    )
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve("P").to_planner_plan()
    assert planner_plan.tasks[0].tool == "write_file"


def test_conversion_produces_ready_plan_with_ordered_tasks():
    from app.planner.models import PlanStatus

    plan = FeaturePlan(
        plan_id="P",
        objective="x",
        artifacts=(
            PlanArtifact(path="a.txt", content="1"),
            PlanArtifact(path="b.txt", content="2"),
        ),
    )
    gate = ApprovalGate()
    gate.submit(plan)
    planner_plan = gate.approve("P").to_planner_plan()

    assert planner_plan.status is PlanStatus.READY
    assert [t.order for t in planner_plan.tasks] == [1, 2]
    assert [t.id for t in planner_plan.tasks] == ["T1", "T2"]


def test_empty_plan_cannot_be_converted():
    plan = FeaturePlan(plan_id="P", objective="x")
    gate = ApprovalGate()
    gate.submit(plan)
    approved = gate.approve("P")
    with pytest.raises(PlanningError, match="não tem artefatos"):
        approved.to_planner_plan()


# ------------------------------------------------------------------ digest
def test_digest_is_stable_for_same_content(plan):
    assert plan.digest == plan.digest


def test_digest_changes_when_content_changes(plan):
    from dataclasses import replace

    altered = replace(plan, artifacts=(PlanArtifact(path="a/b.cpp", content="OUTRO"),))
    assert altered.digest != plan.digest


def test_digest_changes_when_command_changes(plan):
    from dataclasses import replace

    altered = replace(plan, commands=(PlanCommand(argv=("make", "clean")),))
    assert altered.digest != plan.digest


def test_digest_is_not_affected_by_approval_state(plan):
    """Aprovar não muda o conteúdo revisado — o digest precisa sobreviver."""
    gate = ApprovalGate()
    gate.submit(plan)
    approved = gate.approve("FPL-0001")
    assert approved.digest == plan.digest


# ---------------------------------------------------------------- render
def test_render_markdown_lists_files_and_commands(plan):
    text = render_markdown(plan)
    assert "a/b.cpp" in text
    assert "make all" in text
    assert "criar" in text
    assert "Nada foi executado" in text


def test_render_markdown_shows_pending_state(plan):
    assert "PENDING" in render_markdown(plan)


def test_render_markdown_includes_risks_and_validation():
    plan = FeaturePlan(
        plan_id="P",
        objective="x",
        validation_steps=("rodar o editor",),
        risks=("caminho do engine varia",),
        artifacts=(PlanArtifact(path="a.txt", content="x"),),
    )
    text = render_markdown(plan)
    assert "rodar o editor" in text
    assert "caminho do engine varia" in text


def test_render_markdown_omits_content_by_default(plan):
    """Não despejar o conteúdo no terminal: só metadados."""
    plan_with_body = FeaturePlan(
        plan_id="P",
        objective="x",
        artifacts=(PlanArtifact(path="a.txt", content="SEGREDO_UNICO_XYZ"),),
    )
    assert "SEGREDO_UNICO_XYZ" not in render_markdown(plan_with_body)


def test_render_markdown_can_preview_content_on_demand():
    plan_with_body = FeaturePlan(
        plan_id="P",
        objective="x",
        artifacts=(PlanArtifact(path="a.txt", content="int main(){}"),),
    )
    assert "int main(){}" in render_markdown(plan_with_body, max_content_preview=100)


def test_render_marks_build_commands():
    plan = FeaturePlan(
        plan_id="P",
        objective="x",
        commands=(PlanCommand(argv=("UnrealBuildTool",), is_build=True),),
    )
    assert "🔨" in render_markdown(plan)


# ------------------------------------------------------- modelo / validação
def test_artifact_rejects_absolute_windows_path():
    with pytest.raises(PlanningError, match="relativo"):
        PlanArtifact(path="C:/x.cpp", content="y").validate()


def test_artifact_rejects_backslash_absolute():
    with pytest.raises(PlanningError, match="relativo"):
        PlanArtifact(path="\\\\server\\share\\x.cpp", content="y").validate()


def test_artifact_rejects_traversal():
    with pytest.raises(PlanningError, match="relativo"):
        PlanArtifact(path="a/../../b.cpp", content="y").validate()


def test_artifact_accepts_nested_relative_path():
    PlanArtifact(path="Source/Game/Private/A.cpp", content="y").validate()


def test_command_rejects_empty_argv():
    with pytest.raises(PlanningError, match="argv"):
        PlanCommand(argv=()).validate()


def test_command_rejects_bad_timeout():
    with pytest.raises(PlanningError, match="timeout"):
        PlanCommand(argv=("x",), timeout_s=0).validate()


def test_command_rejects_absolute_cwd():
    with pytest.raises(PlanningError, match="cwd"):
        PlanCommand(argv=("x",), cwd="/etc").validate()


def test_plan_rejects_mismatched_approval_plan_id():
    from app.planning.models import ApprovalRecord

    with pytest.raises(PlanningError, match="não pertence"):
        FeaturePlan(plan_id="A", objective="x").with_approval(
            ApprovalRecord(plan_id="B", status=ApprovalStatus.APPROVED)
        )


def test_plan_validate_rejects_mismatched_approval_id():
    """A validação do próprio plano também barra aprovação cruzada."""
    from app.planning.models import ApprovalRecord

    plan = FeaturePlan(plan_id="A", objective="x")
    object.__setattr__(plan, "approval", ApprovalRecord(plan_id="B"))
    with pytest.raises(PlanningError, match="outro plano"):
        plan.validate()


def test_plan_defaults_approval_to_its_own_id():
    plan = FeaturePlan(plan_id="FPL-0007", objective="x")
    assert plan.approval.plan_id == "FPL-0007"


def test_require_approved_helper_raises_for_pending(plan):
    from app.planning.approval import require_approved

    with pytest.raises(PlanNotApprovedError):
        require_approved(plan)


def test_require_approved_helper_passes_for_approved(plan):
    from app.planning.approval import require_approved

    gate = ApprovalGate()
    gate.submit(plan)
    assert require_approved(gate.approve("FPL-0001")) is not None
