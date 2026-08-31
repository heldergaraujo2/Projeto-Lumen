"""Data-flow entre tarefas (0.6.x FASE 8B) — referências ${Tn.data.campo}.

O Executor resolve referências a resultados de tarefas anteriores ANTES
do checkpoint (o humano aprova o valor REAL, nunca o template), com
allowlist de campos por ferramenta, dependência explícita obrigatória,
limites de tamanho/contagem e resolução em passo único. A coleira de
segurança (permissões → sandbox → checkpoint → tool → auditoria) segue
idêntica por tarefa: data-flow não herda nem bypassa autorizações.
"""
from __future__ import annotations

from pathlib import Path

from app.ai.mock import MockProvider
from app.core.agent import Agent
from app.core.bridge import RequestState
from app.executor.executor import _EXPORTABLE_FIELDS
from app.memory.store import MemoryStore
from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus
from app.security.permissions import PermissionManager
from app.tools.control import ToolsController

SECRET = "SEGREDO-123"


# ---------------------------------------------------------------- helpers
def controller_setup(tmp_path: Path, *, writable: bool = True,
                     allow_delete: bool = True, corrections: bool = False,
                     label: str = "s"):
    """Controller real (registry+gates+checkpoints) com workspace em /tmp."""
    ws = tmp_path / f"ws-{label}"
    ws.mkdir()
    (ws / "a.txt").write_text(SECRET, encoding="utf-8")
    (ws / "b.txt").write_text("CONTEUDO B", encoding="utf-8")
    perms = PermissionManager()
    controller = ToolsController(
        perms,
        workspaces_file=tmp_path / f"w-{label}.json",
        audit_file=tmp_path / f"audit-{label}" / "a.jsonl",
        terminal_file=tmp_path / f"t-{label}.json",
    )
    controller.add_workspace(str(ws), writable=writable,
                             allow_delete=writable and allow_delete)
    controller.grant_permission("READ")
    if writable:
        controller.grant_permission("WRITE")
    if corrections:
        controller.enable_corrections()
    return controller, ws


def make_plan(*tasks: PlannedTask, plan_id: str = "PLN-DF") -> Plan:
    return Plan(id=plan_id, objective="dataflow", status=PlanStatus.READY,
                tasks=tasks)


def read_task(task_id: str, order: int, path: str = "a.txt",
              dependencies: tuple[str, ...] = ()) -> PlannedTask:
    return PlannedTask(task_id, f"ler {path}", order, dependencies=dependencies,
                       tool="read_file", parameters={"path": path})


def write_task(task_id: str, order: int, path: str, content: str,
               dependencies: tuple[str, ...] = ()) -> PlannedTask:
    return PlannedTask(task_id, f"gravar {path}", order,
                       dependencies=dependencies, tool="write_file",
                       parameters={"path": path, "content": content})


# --------------------------------------------------------- resolução (1–2)
def test_referencia_simples_resolvida(tmp_path):
    """Referência única vira o valor real (tipo textual preservado)."""
    controller, ws = controller_setup(tmp_path)
    plan = make_plan(
        read_task("T1", 1),
        write_task("T2", 2, "copia.txt", "${T1.data.content}", ("T1",)),
    )
    controller.run_plan(plan)                      # pausa no write (T2)
    report = controller.approve("ok")
    assert report.status is PlanStatus.COMPLETED
    assert report.task_run("T1").status is PlannedTaskStatus.DONE
    assert report.task_run("T2").status is PlannedTaskStatus.DONE
    assert (ws / "copia.txt").read_text(encoding="utf-8") == SECRET


def test_interpolacao_com_dependencia_declarada(tmp_path):
    """Referência no MEIO do texto, com dependência explícita T2←T1."""
    controller, ws = controller_setup(tmp_path)
    plan = make_plan(
        read_task("T1", 1),
        write_task("T2", 2, "copia.txt", "X-${T1.data.content}-Y", ("T1",)),
    )
    controller.run_plan(plan)
    report = controller.approve("ok")
    assert report.status is PlanStatus.COMPLETED
    assert plan.tasks[1].dependencies == ("T1",)
    assert (ws / "copia.txt").read_text(encoding="utf-8") == f"X-{SECRET}-Y"


# ----------------------------------------------------- validações (3–7)
def test_referencia_sem_dependencia_falha(tmp_path):
    """Referência sem dependência declarada ⇒ falha controlada, nada executa."""
    controller, ws = controller_setup(tmp_path)
    plan = make_plan(
        read_task("T1", 1),
        write_task("T2", 2, "copia.txt", "${T1.data.content}"),  # sem deps!
    )
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.FAILED
    error = report.task_run("T2").error or ""
    assert "sem dependência declarada" in error
    assert report.task_run("T1").status is PlannedTaskStatus.DONE
    assert not (ws / "copia.txt").exists()


def test_referencia_a_tarefa_nao_concluida_falha(tmp_path):
    """Referir uma tarefa que AINDA não rodou (não-DONE) falha com segurança.

    T3 existe no plano mas executaria DEPOIS de T2: a referência a ela é
    inválida no momento da resolução de T2 — a tarefa falha antes de
    qualquer gate/execução e as seguintes ficam SKIPPED.
    """
    controller, ws = controller_setup(tmp_path)
    plan = make_plan(
        read_task("T1", 1),
        write_task("T2", 2, "copia.txt", "${T3.data.content}", ("T1",)),
        read_task("T3", 3, "b.txt", ("T2",)),
    )
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.FAILED
    error = report.task_run("T2").error or ""
    assert "dependência declarada" in error or "não está concluída" in error
    assert not (ws / "copia.txt").exists()
    assert report.task_run("T3").status is PlannedTaskStatus.SKIPPED


def test_campo_fora_da_allowlist_falha(tmp_path):
    """size_bytes EXISTE no payload mas não é exportável (allowlist)."""
    controller, ws = controller_setup(tmp_path)
    plan = make_plan(
        read_task("T1", 1),
        write_task("T2", 2, "n.txt", "${T1.data.size_bytes}", ("T1",)),
    )
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.FAILED
    assert "não é exportável (allowlist)" in (report.task_run("T2").error or "")
    assert not (ws / "n.txt").exists()


def test_tamanho_excedido_falha(tmp_path):
    """Valor resolvido acima de 16 KiB ⇒ falha clara, nada gravado."""
    controller, ws = controller_setup(tmp_path)
    (ws / "grande.txt").write_text("G" * (16 * 1024 + 1), encoding="utf-8")
    plan = make_plan(
        read_task("T1", 1, "grande.txt"),
        write_task("T2", 2, "n.txt", "${T1.data.content}", ("T1",)),
    )
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.FAILED
    assert "excede o limite" in (report.task_run("T2").error or "")
    assert not (ws / "n.txt").exists()


def test_mais_de_quatro_referencias_falha(tmp_path):
    """Acima de 4 referências no mesmo parâmetro ⇒ falha clara."""
    controller, ws = controller_setup(tmp_path)
    content = "-".join(["${T1.data.content}"] * 5)
    plan = make_plan(
        read_task("T1", 1),
        write_task("T2", 2, "n.txt", content, ("T1",)),
    )
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.FAILED
    assert "referências de dados (máximo 4)" in (report.task_run("T2").error or "")
    assert not (ws / "n.txt").exists()


# --------------------------------------------------- passo único (8–9)
def test_resolucao_em_passo_unico_sem_cascata(tmp_path):
    """Valor resolvido que CONTÉM uma referência não é re-resolvido."""
    controller, ws = controller_setup(tmp_path)
    (ws / "alvo.txt").write_text("${T1.data.content}", encoding="utf-8")
    plan = make_plan(
        read_task("T1", 1, "alvo.txt"),
        write_task("T2", 2, "copia.txt", "${T1.data.content}", ("T1",)),
    )
    controller.run_plan(plan)
    report = controller.approve("ok")
    assert report.status is PlanStatus.COMPLETED
    # o literal vindo do arquivo permanece LITERAL — sem injeção em cascata
    assert (ws / "copia.txt").read_text(encoding="utf-8") == "${T1.data.content}"


def test_checkpoint_ve_valor_resolvido_nao_template(tmp_path):
    """A aprovação exibe o valor REAL (content_preview resolvido)."""
    controller, ws = controller_setup(tmp_path)
    plan = make_plan(
        read_task("T1", 1),
        write_task("T2", 2, "copia.txt", "X-${T1.data.content}-Y", ("T1",)),
    )
    controller.run_plan(plan)                      # pausa no write
    pending = controller.pending_approval()
    assert pending is not None
    assert pending["task_id"] == "T2"
    assert pending["content_preview"] == f"X-{SECRET}-Y"   # RESOLVIDO
    controller.approve("ok")
    assert (ws / "copia.txt").read_text(encoding="utf-8") == f"X-{SECRET}-Y"


# ------------------------------------------------------ segurança (10–12)
def test_run_command_nao_exportavel(tmp_path):
    """stdout jamais é resolvível: run_command fora da allowlist."""
    assert "run_command" not in _EXPORTABLE_FIELDS        # ausência estrutural
    controller, ws = controller_setup(tmp_path)
    plan = make_plan(
        read_task("T1", 1),
        write_task("T2", 2, "n.txt", "${T1.data.stdout}", ("T1",)),
    )
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.FAILED
    assert "não é exportável (allowlist)" in (report.task_run("T2").error or "")
    assert not (ws / "n.txt").exists()


def test_sandbox_valida_caminho_resolvido(tmp_path):
    """Caminho final pós-resolução segue pelo sandbox (sem bypass)."""
    controller, ws = controller_setup(tmp_path)
    (ws / "mal.txt").write_text("../../fora.txt", encoding="utf-8")

    # (a) conteúdo que tenta ESCAPAR do workspace: sandbox bloqueia.
    plan = make_plan(
        read_task("T1", 1, "mal.txt"),
        write_task("T2", 2, "sub/${T1.data.content}", ("T1",)),
    )
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.FAILED
    assert not (tmp_path / "fora.txt").exists()
    assert not (ws / "sub").exists()

    # (b) resolved_path (allowlisted) aponta DENTRO do workspace: válido.
    plan_ok = make_plan(
        read_task("T1", 1, "b.txt"),
        write_task("T2", 2, "novo.txt", "${T1.data.content}", ("T1",)),
    )
    plan_ok = Plan(id="PLN-DF-OK", objective="ok", status=PlanStatus.READY, tasks=(
        PlannedTask("T1", "ler b", 1, tool="read_file",
                    parameters={"path": "b.txt"}),
        PlannedTask("T2", "gravar b", 2, dependencies=("T1",),
                    tool="write_file",
                    parameters={"path": "${T1.data.resolved_path}",
                                "content": "NOVO-B"}),
    ))
    controller.run_plan(plan_ok)
    report = controller.approve("ok")
    assert report.status is PlanStatus.COMPLETED
    assert (ws / "b.txt").read_text(encoding="utf-8") == "NOVO-B"


def test_permissoes_preservadas_com_dataflow(tmp_path):
    """Sem WRITE concedida: T2(write) bloqueada mesmo com dados de T1."""
    controller, ws = controller_setup(tmp_path, writable=False)
    plan = make_plan(
        read_task("T1", 1),
        write_task("T2", 2, "n.txt", "${T1.data.content}", ("T1",)),
    )
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.FAILED
    assert "WRITE" in (report.task_run("T2").error or "")
    assert not (ws / "n.txt").exists()


# ------------------------------------------------------ regressões (13–15)
def test_regressao_caminho_classico_sem_referencias(tmp_path):
    """Plano sem referências: comportamento 0.6.x intacto."""
    controller, ws = controller_setup(tmp_path)
    plan = make_plan(read_task("T1", 1, "b.txt"))
    report = controller.run_plan(plan)
    assert report.status is PlanStatus.COMPLETED      # READ direto, sem CP

    plan2 = make_plan(
        write_task("T1", 1, "n.txt", "TEXTO"),
    )
    plan2 = Plan(id="PLN-CL", objective="classico", status=PlanStatus.READY,
                 tasks=(PlannedTask("T1", "gravar n", 1, tool="write_file",
                                    parameters={"path": "n.txt",
                                                "content": "TEXTO"}),))
    report2 = controller.run_plan(plan2)
    assert report2.status is PlanStatus.RUNNING      # pausa no checkpoint
    report2 = controller.approve("ok")
    assert report2.status is PlanStatus.COMPLETED
    assert (ws / "n.txt").read_text(encoding="utf-8") == "TEXTO"


def test_regressao_multitask_via_chat(tmp_path):
    """Multi-task do chat (FASE 7) continua 2/2 COMPLETED."""
    ws = tmp_path / "ws-chat"
    ws.mkdir()
    (ws / "a.txt").write_text(SECRET, encoding="utf-8")
    (ws / "b.txt").write_text("CONTEUDO B", encoding="utf-8")
    perms = PermissionManager()
    agent = Agent(MockProvider(), MemoryStore(tmp_path / "mem.json"),
                  permissions=perms)
    controller = ToolsController(
        perms, workspaces_file=tmp_path / "w-chat.json",
        audit_file=tmp_path / "audit-chat" / "a.jsonl",
        terminal_file=tmp_path / "t-chat.json",
    )
    agent.set_tools_controller(controller)
    controller.add_workspace(str(ws), writable=True, allow_delete=True)
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")
    outcome = agent.process_message(
        "Leia o arquivo a.txt e depois leia o arquivo b.txt"
    )
    assert outcome.state is RequestState.COMPLETED
    assert "2/2 tarefa(s)" in outcome.text


def test_regressao_correcao_e_retry(tmp_path):
    """Correção mid-plan (plano sucessor) e retry seguem funcionando."""
    controller, ws = controller_setup(tmp_path, corrections=True)
    plan = make_plan(
        read_task("T1", 1),
        PlannedTask("T2", "criar a.txt (vai falhar)", 2, dependencies=("T1",),
                    tool="create_file",
                    parameters={"path": "a.txt", "content": "NOVO"}),
        read_task("T3", 3, "a.txt", ("T2",)),
    )
    controller.run_plan(plan)                       # CP de T2
    controller.approve("exec")                      # falha: já existe
    assert controller.pending_approval()["kind"] == "correction"
    controller.approve("aplicar")                   # write_file proposto
    report = controller.approve("exec corrigida")   # executa + T3
    assert report.status is PlanStatus.COMPLETED
    statuses = [entry["status"] for entry in controller.correction_history()]
    assert "APPLIED" in statuses and "RETRIED" in statuses
    assert statuses[-1] == "SUCCEEDED"
    assert (ws / "a.txt").read_text(encoding="utf-8") == "NOVO"
