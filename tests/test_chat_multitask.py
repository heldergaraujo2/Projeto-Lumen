"""Plano multi-tarefa via chat (0.6.7) — evolução FASE A/B da auditoria.

O MockProvider reconhece pedidos compostos por conectores sequenciais
("crie X e depois leia X") e emite um plano com múltiplas tarefas
encadeadas por dependências. Toda a cadeia real (Planner → Controller
→ Registry → Permissões → Sandbox → Tools → Executor → Bridge) segue
inalterada: CADA tarefa é validada individualmente — allowlist,
permissões, sandbox, checkpoint e auditoria. Pedidos simples continuam
gerando exatamente uma tarefa (compatibilidade 0.6.6).
"""
from __future__ import annotations

import ast
from pathlib import Path

from app.ai.mock import MockProvider
from app.core.agent import Agent
from app.core.bridge import RequestState, ToolCallingBridge
from app.memory.store import MemoryStore
from app.planner.catalog import build_catalog
from app.planner.models import PlanStatus, PlannedTaskStatus
from app.planner.planner import Planner
from app.security.permissions import PermissionManager
from app.tools.control import ToolsController

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- helpers
def plan_of(message: str):
    """Resultado do planejamento (protocolo completo) para a mensagem."""
    planner = Planner(
        MockProvider(), catalog=build_catalog(include_terminal=False),
    )
    return planner.create_tool_plan(message)


def chat_setup(tmp_path: Path, *, writable: bool = True,
               allow_delete: bool = True, corrections: bool = False,
               label: str = "s"):
    """Cadeia real (Agent+Bridge+Controller+Registry) com workspace em /tmp.

    ``label`` diferencia os arquivos de estado quando mais de uma
    montagem é feita no mesmo teste (permissões diferentes).
    """
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    (ws / "a.txt").write_text("CONTEUDO A", encoding="utf-8")
    (ws / "b.txt").write_text("CONTEUDO B", encoding="utf-8")
    perms = PermissionManager()
    agent = Agent(
        MockProvider(), MemoryStore(tmp_path / f"mem-{label}.json"),
        permissions=perms,
    )
    controller = ToolsController(
        perms,
        workspaces_file=tmp_path / f"w-{label}.json",
        audit_file=tmp_path / f"audit-{label}" / "a.jsonl",
        terminal_file=tmp_path / f"t-{label}.json",
    )
    agent.set_tools_controller(controller)
    controller.add_workspace(str(ws), writable=writable,
                             allow_delete=writable and allow_delete)
    controller.grant_permission("READ")
    if writable:
        controller.grant_permission("WRITE")
    if corrections:
        controller.enable_corrections()
    return agent, controller, ws


def _imports_of(path: Path) -> set[str]:
    """Módulos importados por um arquivo (análise AST, sem executar)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    return modules


# --------------------------------------------- protocolo/planner (1–5)
def test_pedido_simpel_gera_exatamente_uma_tarefa():
    """Requisito 1 — pedidos simples continuam com UMA tarefa, sem deps."""
    result = plan_of("Leia o arquivo a.txt")
    assert result.kind == "plan"
    tasks = result.plan.tasks
    assert len(tasks) == 1
    assert tasks[0].tool == "read_file"
    assert tasks[0].dependencies == ()


def test_pedido_composto_gera_duas_tarefas_encadeadas():
    """Requisitos 2, 3 e 4 — duas tarefas, IDs T1/T2, T2 depende de T1."""
    message = ("Crie o arquivo chamado notas.txt contendo: dados "
               "importantes e depois leia o arquivo notas.txt")
    result = plan_of(message)
    assert result.kind == "plan"
    tasks = result.plan.tasks
    assert len(tasks) == 2
    assert [t.id for t in tasks] == ["T1", "T2"]
    assert tasks[0].tool == "create_file"
    assert tasks[0].parameters == {"path": "notas.txt",
                                   "content": "dados importantes"}
    assert tasks[1].tool == "read_file"
    assert tasks[1].parameters == {"path": "notas.txt"}
    assert tasks[1].dependencies == ("T1",)
    # determinismo (contrato do mock)
    again = plan_of(message)
    assert [t.parameters for t in again.plan.tasks] == \
        [t.parameters for t in tasks]


def test_listar_e_depois_ler_gera_duas_tarefas():
    """Requisito 2 (exemplo 2) — listar seguido de ler."""
    result = plan_of("Liste os arquivos e depois leia o arquivo README.md")
    assert result.kind == "plan"
    tasks = result.plan.tasks
    assert [t.tool for t in tasks] == ["list_directory", "read_file"]
    assert tasks[1].dependencies == ("T1",)


def test_tres_tarefas_encadeadas_na_ordem():
    """Requisitos 3 e 4 — cadeia linear T1 ← T2 ← T3 com ordem 1..3."""
    result = plan_of("leia o arquivo a.txt depois leia o arquivo b.txt "
                     "e então leia o arquivo c.txt")
    assert result.kind == "plan"
    tasks = result.plan.tasks
    assert [t.id for t in tasks] == ["T1", "T2", "T3"]
    assert [t.order for t in tasks] == [1, 2, 3]
    assert tasks[1].dependencies == ("T1",)
    assert tasks[2].dependencies == ("T2",)


def test_tarefas_chegam_ao_executor_em_ordem(tmp_path):
    """Requisito 5 — executor respeita a ordem (T2 só após T1 DONE)."""
    agent, controller, ws = chat_setup(tmp_path)
    outcome = agent.process_message(
        "Leia o arquivo a.txt e depois leia o arquivo b.txt"
    )
    assert outcome.state is RequestState.COMPLETED
    assert "2/2 tarefa(s)" in outcome.text
    # A dependência T2←T1 só libera T2 quando T1 está DONE: o executor
    # preservou a ordem e o relatório agregado chega ao chat.
    assert (ws / "a.txt").read_text(encoding="utf-8") == "CONTEUDO A"


def test_read_seguido_de_read_executa_sem_aprovacao(tmp_path):
    """Requisito 6 — READ + READ executa direto, sem checkpoint."""
    agent, controller, ws = chat_setup(tmp_path)
    outcome = agent.process_message(
        "Leia o arquivo a.txt e depois leia o arquivo b.txt"
    )
    assert outcome.state is RequestState.COMPLETED
    assert not controller.has_pending


# --------------------------------------------- checkpoints (7–8)
def test_write_no_meio_exige_checkpoint(tmp_path):
    """Requisito 7 — WRITE no meio do plano pausa ANTES de escrever."""
    agent, controller, ws = chat_setup(tmp_path)
    outcome = agent.process_message(
        "Leia o arquivo a.txt e depois escreva o arquivo novo.txt "
        "contendo: TEXTO NOVO"
    )
    assert outcome.state is RequestState.WAITING_APPROVAL
    assert not (ws / "novo.txt").exists()          # nada antes de aprovar
    pending = controller.pending_approval()
    assert pending["tool"] == "write_file"
    report = controller.approve("ok")               # aprova SÓ a T2
    assert report.status is PlanStatus.COMPLETED
    assert (ws / "novo.txt").read_text(encoding="utf-8") == "TEXTO NOVO"


def test_recusa_do_checkpoint_da_segunda_tarefa(tmp_path):
    """Requisito 8 — recusar o checkpoint da T2 impede a sua execução."""
    agent, controller, ws = chat_setup(tmp_path)
    outcome = agent.process_message(
        "Leia o arquivo a.txt e depois escreva o arquivo novo.txt "
        "contendo: TEXTO NOVO"
    )
    assert outcome.state is RequestState.WAITING_APPROVAL
    report = controller.refuse("não")
    assert report.status is PlanStatus.FAILED
    assert not (ws / "novo.txt").exists()           # T2 não executou
    assert report.task_run("T1").status is PlannedTaskStatus.DONE
    assert report.task_run("T2").status is PlannedTaskStatus.SKIPPED
    assert not controller.has_pending


# --------------------------------------------- falha e correção (9–10)
def test_falha_no_meio_nao_executa_as_seguintes(tmp_path):
    """Requisito 9 — fail-fast: T2 falha ⇒ T3 fica SKIPPED."""
    agent, controller, ws = chat_setup(tmp_path)
    outcome = agent.process_message(
        "leia o arquivo a.txt depois leia o arquivo z_inexistente.txt "
        "e então leia o arquivo b.txt"
    )
    assert outcome.state is RequestState.FAILED
    assert "1/3 tarefa(s)" in outcome.text          # só T1 concluída
    assert "Nada mais foi executado" in outcome.text
    assert (ws / "a.txt").exists()                  # nada foi alterado
    assert (ws / "b.txt").read_text(encoding="utf-8") == "CONTEUDO B"


def test_correcao_no_meio_preserva_as_demais(tmp_path):
    """Requisito 10 — T1✔, T2 create→falha→correção(write)→✔, T3✔."""
    agent, controller, ws = chat_setup(tmp_path, corrections=True)
    outcome = agent.process_message(
        "leia o arquivo a.txt e depois crie o arquivo chamado a.txt "
        "contendo: NOVO A e então leia o arquivo a.txt"
    )
    assert outcome.state is RequestState.WAITING_APPROVAL
    reports = []
    while controller.has_pending:                   # CP, correção, CP…
        reports.append(controller.approve("ok"))
    final = reports[-1]
    assert final.status is PlanStatus.COMPLETED
    # plano sucessor (#C1) carrega as tarefas restantes com os mesmos IDs:
    # a T2 corrigida executou e a T3 seguinte também.
    assert final.task_run("T2").status is PlannedTaskStatus.DONE
    assert final.task_run("T3").status is PlannedTaskStatus.DONE
    # a T1 concluída antes da falha segue preservada no relatório original.
    original = next(r for r in reports if "#" not in r.plan_id)
    assert original.task_run("T1").status is PlannedTaskStatus.DONE
    assert (ws / "a.txt").read_text(encoding="utf-8") == "NOVO A"
    statuses = [entry["status"] for entry in controller.correction_history()]
    assert "APPLIED" in statuses and "RETRIED" in statuses
    assert statuses[-1] == "SUCCEEDED"


# --------------------------------------------- bridge (11)
def test_bridge_informa_total_pausa_e_falha(tmp_path):
    """Requisito 11 — done/total, tarefa atual (pausa) e falha."""
    agent, controller, ws = chat_setup(tmp_path)
    bridge = ToolCallingBridge(agent, controller)

    # concluído: 2/2
    outcome = agent.process_message(
        "Leia o arquivo a.txt e depois leia o arquivo b.txt"
    )
    assert outcome.state is RequestState.COMPLETED
    assert "2/2 tarefa(s)" in outcome.text and "concluído" in outcome.text

    # pausado: informa a operação corrente (T2 = write_file)
    outcome = agent.process_message(
        "Leia o arquivo b.txt e depois escreva o arquivo x.txt "
        "contendo: X"
    )
    assert outcome.state is RequestState.WAITING_APPROVAL
    assert "PAUSADO para a sua aprovação" in outcome.text
    assert "Operação: Gravar o arquivo x.txt" in outcome.text
    report = controller.refuse("não")

    # falha: 1/2 concluída(s), nada mais executado
    final = bridge.outcome_for_report(None, report.plan_id, report)
    assert final.state is RequestState.FAILED
    assert "1/2 tarefa(s) concluída(s)" in final.text
    assert "Nada mais foi executado" in final.text


# --------------------------------------------- segurança (12–13)
def test_sem_bypass_de_permissoes_em_plano_multiplo(tmp_path):
    """Requisito 12 — cada tarefa é gateada individualmente."""
    # (a) sem WRITE: T1 read executa, T2 write é bloqueada.
    agent, controller, ws = chat_setup(tmp_path, writable=False, label="a")
    outcome = agent.process_message(
        "Leia o arquivo a.txt e depois escreva o arquivo novo.txt "
        "contendo: X"
    )
    assert outcome.state is RequestState.FAILED
    assert "WRITE" in outcome.text
    assert not (ws / "novo.txt").exists()

    # (b) allow_delete=False: T2 delete é bloqueada, arquivo intacto.
    agent, controller, ws = chat_setup(tmp_path, allow_delete=False, label="b")
    outcome = agent.process_message(
        "Leia o arquivo a.txt e depois apague o arquivo a.txt"
    )
    assert outcome.state is RequestState.FAILED
    assert (ws / "a.txt").exists()

    # (c) aprovar a T2 NÃO autoriza a T3: write aprovado, delete pausa.
    agent, controller, ws = chat_setup(tmp_path, allow_delete=True, label="c")
    agent.process_message(
        "leia o arquivo a.txt e depois escreva o arquivo c.txt "
        "contendo: C e então apague o arquivo b.txt"
    )
    controller.approve("ok")                        # aprova SÓ o write (T2)
    assert (ws / "c.txt").exists()                  # T2 executou
    assert controller.has_pending                   # T3 (delete) pausou
    assert (ws / "b.txt").exists()                  # T3 não executou
    controller.approve("ok")                        # agora sim, a T3
    assert not (ws / "b.txt").exists()


def test_ast_arquitetura_preservada():
    """Requisito 13 — contratos arquiteturais intactos (AST)."""
    for path in (PROJECT_ROOT / "app" / "executor").glob("*.py"):
        modules = _imports_of(path)
        assert not any(m == "subprocess" for m in modules), path
        assert not any(m.startswith("app.tools") for m in modules), path
    for path in (PROJECT_ROOT / "app" / "planner").glob("*.py"):
        modules = _imports_of(path)
        assert not any(m.startswith("app.tools") for m in modules), path
        assert not any(m == "subprocess" for m in modules), path
    for path in (PROJECT_ROOT / "app" / "ui").glob("*.py"):
        for module in _imports_of(path):
            if module.startswith("app.tools"):
                assert module.startswith("app.tools.control"), path
    terminal_users = sorted(
        path for path in (PROJECT_ROOT / "app").rglob("*.py")
        if "subprocess" in _imports_of(path)
    )
    assert terminal_users == [PROJECT_ROOT / "app" / "tools" / "terminal.py"]


# --------------------------------------------- compatibilidade (14)
def test_pedidos_classicos_continuam_funcionando():
    """Requisito 14 — comportamento 0.6.6 do mock intacto."""
    # pedido simples canônico (parâmetros exatos)
    result = plan_of("Crie um arquivo chamado teste_lumen.txt contendo: "
                     "TESTE LUMEN")
    assert result.kind == "plan"
    assert len(result.plan.tasks) == 1
    assert result.plan.tasks[0].parameters == {
        "path": "teste_lumen.txt", "content": "TESTE LUMEN",
    }

    # listar simples
    result = plan_of("Liste os arquivos do workspace")
    assert result.kind == "plan"
    assert result.plan.tasks[0].tool == "list_directory"
    assert result.plan.tasks[0].parameters == {"path": "."}

    # conteúdo que CITA um conector continua inteiro no caminho clássico
    result = plan_of("Crie o arquivo chamado diario.txt contendo: "
                     "acordei e depois alonguei")
    assert result.kind == "plan"
    assert len(result.plan.tasks) == 1
    assert result.plan.tasks[0].parameters == {
        "path": "diario.txt", "content": "acordei e depois alonguei",
    }

    # pedido composto com segmento vago ⇒ comportamento clássico (1 tarefa)
    result = plan_of("Leia o arquivo a.txt e depois pense sobre a vida")
    assert result.kind == "plan"
    assert len(result.plan.tasks) == 1
    assert result.plan.tasks[0].tool == "read_file"

    # conversa continua conversa
    assert plan_of("bom dia, como você está?").kind == "conversation"
