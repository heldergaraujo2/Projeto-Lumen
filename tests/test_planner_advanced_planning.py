"""Advanced Planning MVP (10B) — guardrails R5, Stage 2 R1, data-flow R3,
success_criteria R2 (metadado) — replanning automático R4 PROIBIDO/não
implementado.

Contratos testados (com providers FAKE determinísticos; nenhuma tool é
executada, exceto o teste operacional que usa workspace em tmp_path):
- R5: exceder limites REJEITA o plano com erro explícito (nunca trunca,
  nunca executa parcialmente); limites configuráveis (Settings/PlannerLimits).
- R1: Stage 2 é refinador CONSERVADOR com fallback obrigatório; qualquer
  violação semântica descarta o refino; desligado por padrão.
- R3: ${Tn.data.<campo>} exige tarefa existente + dependência declarada;
  sem exportable_fields no Planner (autoridade segue no Executor).
- R2: success_criteria é metadado puramente informativo.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from app.ai.types import AIResponse, ResponseType
from app.config.settings import Settings
from app.planner.catalog import build_catalog
from app.planner.planner import Planner, PlannerLimits
from app.planner.models import Plan, PlanStatus, PlannedTask
from app.security.permissions import PermissionManager
from app.tools.control import ToolsController

CATALOG = build_catalog(include_terminal=False)
PROJECT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- helpers
class ScriptedProvider:
    """Devolve planos fixos: stage 1 (pedido) e stage 2 (opcional)."""

    name = "fake"
    model_name = "fake"

    def __init__(self, stage1: str, stage2: str | None = None) -> None:
        self._stage1 = stage1
        self._stage2 = stage2
        self.calls: list[str] = []

    def chat(self, message, context=None, **kwargs):
        self.calls.append(message)
        is_refine = "estagio 1" in message
        if is_refine and self._stage2 is None:
            content = "lixo total, não é JSON"
        else:
            content = self._stage2 if is_refine else self._stage1
        return AIResponse(
            content, "fake", None, "stop", ResponseType.FINAL_RESPONSE,
        )


def plan_json(tasks: list[dict], objective: str = "objetivo") -> str:
    return json.dumps(
        {"type": "plan", "objective": objective, "analysis": [],
         "tasks": tasks},
        ensure_ascii=False,
    )


def read_task(task_id: int, path: str = "a.txt", deps: list[int] | None = None,
              **extra) -> dict:
    return {"id": task_id, "description": f"ler {path}",
            "dependencies": deps or [], "tool": "read_file",
            "parameters": {"path": path}, **extra}


def write_task(task_id: int, deps: list[int], content: str,
               path: str = "b.txt", **extra) -> dict:
    return {"id": task_id, "description": f"gravar {path}",
            "dependencies": deps, "tool": "write_file",
            "parameters": {"path": path, "content": content}, **extra}


def chain(n: int) -> list[dict]:
    return [read_task(i + 1, deps=([i] if i else [])) for i in range(n)]


# --------------------------------------------------- R5 — guardrails (1–7)
def test_guardrail_max_tasks_rejeita():
    """13 tarefas (> 12) ⇒ invalid com motivo; nada executa."""
    result = Planner(ScriptedProvider(plan_json(chain(13))),
                     catalog=CATALOG).create_tool_plan("objetivo")
    assert result.kind == "invalid"
    assert "máximo 12" in result.reason
    assert result.plan.status is PlanStatus.FAILED


def test_guardrail_plan_limits_configuraveis():
    """PlannerLimits custom redefine o teto (3 tarefas com max_tasks=2)."""
    limits = PlannerLimits(max_tasks=2)
    result = Planner(ScriptedProvider(plan_json(chain(3))), catalog=CATALOG,
                     limits=limits).create_tool_plan("objetivo")
    assert result.kind == "invalid"
    assert "máximo 2" in result.reason


def test_guardrail_dependency_depth_rejeita():
    """Cadeia de 7 (> 6) ⇒ invalid com profundidade no motivo."""
    result = Planner(ScriptedProvider(plan_json(chain(7))),
                     catalog=CATALOG).create_tool_plan("objetivo")
    assert result.kind == "invalid"
    assert "profundidade de dependências é 7" in result.reason


def test_guardrail_text_field_rejeita():
    """Descrição > 16 KiB ⇒ invalid (rejeção, nunca truncamento)."""
    huge = read_task(1, description="A" * (16 * 1024 + 1))
    result = Planner(ScriptedProvider(plan_json([huge])),
                     catalog=CATALOG).create_tool_plan("objetivo")
    assert result.kind == "invalid"
    assert "excede o limite de 16384 bytes" in result.reason


def test_guardrail_objetivo_grande_rejeita():
    """Objetivo > 16 KiB ⇒ invalid controlado."""
    result = Planner(ScriptedProvider(plan_json([read_task(1)])),
                     catalog=CATALOG).create_tool_plan("o" * (16 * 1024 + 1))
    assert result.kind == "invalid"
    assert "excede o limite" in result.reason


def test_guardrail_dataflow_refs_por_parametro():
    """5 referências no mesmo parâmetro (> 4) ⇒ invalid."""
    content = "-".join(["${T1.data.content}"] * 5)
    tasks = [read_task(1), write_task(2, [1], content)]
    result = Planner(ScriptedProvider(plan_json(tasks)),
                     catalog=CATALOG).create_tool_plan("objetivo")
    assert result.kind == "invalid"
    assert "5 referências de data-flow (máximo 4)" in result.reason


def test_guardrails_settings_defaults_e_env():
    """Defaults oficiais + configuráveis por ambiente (LUMEN_PLANNER_*)."""
    settings = Settings()
    assert settings.planner_max_tasks == 12
    assert settings.planner_max_dependency_depth == 6
    assert settings.planner_max_text_field_bytes == 16 * 1024
    assert settings.planner_max_dataflow_refs_per_param == 4
    assert settings.planner_refine_enabled is False
    # PlannerLimits espelha os defaults (fonte dupla consciente p/ 10B).
    assert PlannerLimits() == PlannerLimits(12, 6, 16 * 1024, 4)
    env = Settings.load(env_file="/tmp/inexistente.env", environ={
        "LUMEN_PLANNER_MAX_TASKS": "3",
        "LUMEN_PLANNER_REFINE": "1",
    })
    assert env.planner_max_tasks == 3
    assert env.planner_refine_enabled is True


# --------------------------------------------------- R3 — data-flow (8–12)
def test_dataflow_ref_com_dependencia_valida():
    """${T1.data.content} com deps [1] ⇒ plano válido, literal preservado."""
    tasks = [read_task(1), write_task(2, [1], "x-${T1.data.content}-y")]
    result = Planner(ScriptedProvider(plan_json(tasks)),
                     catalog=CATALOG).create_tool_plan("copiar")
    assert result.kind == "plan"
    assert result.plan.tasks[1].dependencies == ("T1",)
    assert result.plan.tasks[1].parameters["content"] == "x-${T1.data.content}-y"


def test_dataflow_ref_sem_dependencia_rejeita():
    """Ref sem dependência declarada ⇒ invalid (consistência R3)."""
    tasks = [read_task(1), write_task(2, [], "${T1.data.content}")]
    result = Planner(ScriptedProvider(plan_json(tasks)),
                     catalog=CATALOG).create_tool_plan("copiar")
    assert result.kind == "invalid"
    assert "sem dependência declarada" in result.reason


def test_dataflow_ref_tarefa_inexistente_rejeita():
    """${T9...} em plano de 2 tarefas ⇒ invalid."""
    tasks = [read_task(1), write_task(2, [1], "${T9.data.content}")]
    result = Planner(ScriptedProvider(plan_json(tasks)),
                     catalog=CATALOG).create_tool_plan("x")
    assert result.kind == "invalid"
    assert "T9, que não existe no plano" in result.reason


def test_dataflow_autoreferencia_rejeita():
    """T1 referenciando a si mesma ⇒ invalid (deps em si = ciclo)."""
    tasks = [read_task(1), write_task(2, [], "${T2.data.content}")]
    result = Planner(ScriptedProvider(plan_json(tasks)),
                     catalog=CATALOG).create_tool_plan("x")
    assert result.kind == "invalid"
    assert "dela mesma" in result.reason


def test_planner_sem_exportable_fields_e_sem_tools():
    """R3: NÃO existe exportable_fields no Planner; pacote segue agnóstico."""
    for name in ("planner.py", "catalog.py", "models.py"):
        source = (PROJECT / "app" / "planner" / name).read_text(encoding="utf-8")
        assert "exportable" not in source.lower(), name
    for path in (PROJECT / "app" / "planner").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(a.name.startswith("app.tools") for a in node.names)
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("app.tools")


# ------------------------------------------- R2 — success_criteria (13–15)
def test_success_criteria_parseado_como_metadado():
    """Critérios chegam em PlannedTask + to_dict (metadado opcional)."""
    tasks = [read_task(1, success_criteria=["arquivo legível", "utf-8 válido"])]
    result = Planner(ScriptedProvider(plan_json(tasks)),
                     catalog=CATALOG).create_tool_plan("ler")
    assert result.kind == "plan"
    task = result.plan.tasks[0]
    assert task.success_criteria == ("arquivo legível", "utf-8 válido")
    assert task.to_dict()["success_criteria"] == ["arquivo legível", "utf-8 válido"]


def test_success_criteria_invalido_rejeita():
    """success_criteria sem texto ⇒ invalid (protocolo estrito)."""
    tasks = [read_task(1, success_criteria=["   "])]
    result = Planner(ScriptedProvider(plan_json(tasks)),
                     catalog=CATALOG).create_tool_plan("ler")
    assert result.kind == "invalid"
    assert "success_criteria" in result.reason


def test_success_criteria_sem_efeito_operacional(tmp_path):
    """R2: critérios NÃO alteram execução — plano roda igual com/sem eles."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("OK", encoding="utf-8")
    controller = ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / "w.json",
        audit_file=tmp_path / "audit" / "a.jsonl",
        terminal_file=tmp_path / "t.json",
    )
    controller.add_workspace(str(ws), writable=False)
    controller.grant_permission("READ")
    plan = Plan(id="PLN-CRIT", objective="ler", status=PlanStatus.READY, tasks=(
        PlannedTask("T1", "ler a.txt", 1, tool="read_file",
                    parameters={"path": "a.txt"},
                    success_criteria=("conteúdo obtido",)),))
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.COMPLETED  # metadado não cria gate


# ----------------------------------------------- R1 — Stage 2 (16–20)
def test_stage2_planner_refine_aplicado():
    """Refino conservador: descrição/critérios melhorados + dep adicionada
    (ref sem dep no stage 1); tool/params/id/objetivo intactos."""
    stage1 = plan_json([read_task(1), write_task(2, [], "${T1.data.content}")])
    stage2 = plan_json([
        read_task(1, description="Ler a.txt com cuidado",
                  success_criteria=["conteúdo obtido"]),
        write_task(2, [1], "${T1.data.content}", description="Gravar cópia",
                   success_criteria=["cópia fiel"]),
    ])
    provider = ScriptedProvider(stage1, stage2)
    result = Planner(provider, catalog=CATALOG,
                     refine_enabled=True).create_tool_plan("copiar")
    assert result.kind == "plan"
    plan = result.plan
    assert plan.id == "PLN-0001"                    # mesmo plano (mesmo id)
    assert plan.tasks[0].description == "Ler a.txt com cuidado"
    assert plan.tasks[0].success_criteria == ("conteúdo obtido",)
    assert plan.tasks[1].dependencies == ("T1",)    # dep adicionada (regra)
    assert plan.tasks[1].tool == "write_file"       # inalterada
    assert plan.tasks[1].parameters["content"] == "${T1.data.content}"
    assert len(provider.calls) == 2                 # stage 1 + stage 2


def test_stage2_violacao_troca_tool_descarta_refino():
    """Stage 2 que troca tool ⇒ descartado; plano do Stage 1 (válido) segue."""
    stage1 = plan_json([read_task(1), write_task(2, [1], "${T1.data.content}")])
    stage2 = plan_json([  # troca read_file → write_file na T1 (proibido)
        {"id": 1, "description": "hack", "dependencies": [],
         "tool": "write_file", "parameters": {"path": "a.txt", "content": "X"}},
        write_task(2, [1], "${T1.data.content}"),
    ])
    provider = ScriptedProvider(stage1, stage2)
    result = Planner(provider, catalog=CATALOG,
                     refine_enabled=True).create_tool_plan("copiar")
    assert result.kind == "plan"
    assert result.plan.tasks[0].tool == "read_file"     # stage 1 intacto
    assert result.plan.tasks[0].description == "ler a.txt"


def test_stage2_parametros_alterados_descarta_refino():
    """Stage 2 que altera parameters ⇒ descartado (conservadorismo)."""
    stage1 = plan_json([read_task(1), write_task(2, [1], "${T1.data.content}")])
    stage2 = plan_json([
        read_task(1),
        write_task(2, [1], "CONTEÚDO INJETADO"),   # parameters alterados
    ])
    result = Planner(ScriptedProvider(stage1, stage2), catalog=CATALOG,
                     refine_enabled=True).create_tool_plan("copiar")
    assert result.kind == "plan"
    assert result.plan.tasks[1].parameters["content"] == "${T1.data.content}"


def test_stage2_lixo_faz_fallback_e_sem_correcao_rejeita():
    """Stage 2 ilegível ⇒ fallback; stage 1 com ref sem dep ⇒ invalid final."""
    stage1 = plan_json([read_task(1), write_task(2, [], "${T1.data.content}")])
    provider = ScriptedProvider(stage1, stage2=None)  # refine = lixo
    result = Planner(provider, catalog=CATALOG,
                     refine_enabled=True).create_tool_plan("copiar")
    assert result.kind == "invalid"                     # consistência final
    assert "sem dependência declarada" in result.reason
    assert len(provider.calls) == 2


def test_stage2_desligado_por_padrao_uma_chamada():
    """Sem refine_enabled ⇒ UMA única chamada ao provider (Stage 1 only)."""
    provider = ScriptedProvider(plan_json([read_task(1)]))
    result = Planner(provider, catalog=CATALOG).create_tool_plan("ler")
    assert result.kind == "plan"
    assert len(provider.calls) == 1


# ----------------------------------------------- R4 — proibido (contrato)
def test_r4_replanning_automatico_nao_implementado():
    """R4 (ADIADO): nenhum loop/ciclo de replanejamento no Planner."""
    source = (PROJECT / "app" / "planner" / "planner.py").read_text(encoding="utf-8")
    assert "replan" not in source.lower()
    assert "max_cycles" not in source
    # e o prompt do refinador é conservador (sem autonomia adicional)
    assert "PROIBIDO" in source
