"""Testes da correção automática integrada às ferramentas (0.6.2).

Estratégia conservadora (unit) + cadeia real pelo ToolsController:
proposta → aprovação → checkpoint da operação corrigida → execução →
auditoria; recusa; invalidação; limites; sem bypass de permissões.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.planner.models import Plan, PlanStatus, PlannedTask
from app.security.permissions import PermissionManager
from app.tools.control import ToolsControlError, ToolsController
from app.tools.correction import (
    EvidenceCorrectionStrategy,
    ToolCorrectionStrategy,
)

# --------------------------------------------------------- estratégia (unit)


def run_of(tool: str, error: str):
    from app.executor.executor import TaskRun
    from app.planner.models import PlannedTaskStatus
    return TaskRun(id="T1", description="d", order=1, dependencies=(),
                   status=PlannedTaskStatus.FAILED, error=error)


def task_of(tool: str = "create_file", **parameters) -> PlannedTask:
    return PlannedTask(id="T1", description="gravar", order=1,
                       tool=tool, parameters=parameters or {"path": "a.txt"})


def test_strategy_proposes_write_file_when_create_file_hits_existing():
    proposal = ToolCorrectionStrategy().propose_correction(
        task_of("create_file", path="a.txt", content="x"),
        run_of("create_file",
               "O arquivo já existe (create_file não sobrescreve): /ws/a.txt"),
    )
    assert proposal is not None
    assert proposal.corrected_task.tool == "write_file"
    assert proposal.corrected_task.parameters == {"path": "a.txt", "content": "x"}
    assert proposal.requires_approval is True  # controle: sempre aprovação
    assert proposal.corrected_task.id == "T1"  # mesmo id (deps preservadas)


@pytest.mark.parametrize("error", [
    "Ferramenta 'create_file' bloqueada: Permissão negada: 'WRITE' …",
    "Comando 'mkdir' não está na allowlist de terminal — bloqueado",
    "Comando 'sh' é proibido (política permanente)",
    "Escrita bloqueada: a política do workspace está em modo somente leitura",
    "Exclusão bloqueada: … allow_delete=False",
    "Caminho fora do workspace autorizado: '../../etc'",
    "Caminho bloqueado: componente '..' (tentativa de traversal)",
    "Argumento contém operador de shell '&&' (não permitido)",
])
def test_strategy_never_proposes_bypass_for_security_errors(error):
    assert ToolCorrectionStrategy().propose_correction(
        task_of("create_file", path="a.txt"), run_of("create_file", error),
    ) is None


def test_strategy_proposes_nothing_for_unknown_or_other_errors():
    strategy = ToolCorrectionStrategy()
    assert strategy.propose_correction(
        task_of("read_file", path="sumiu.txt"),
        run_of("read_file", "Arquivo não existe: /ws/sumiu.txt"),
    ) is None
    assert strategy.propose_correction(task_of(), run_of("t", "qualquer")) is None


# ---------------------------------------------------- controller (integração)
@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "nota.txt").write_text("ORIGINAL", encoding="utf-8")
    return root


@pytest.fixture()
def controller(tmp_path: Path) -> ToolsController:
    return ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )


def armed(controller: ToolsController, ws: Path) -> None:
    controller.add_workspace(str(ws), writable=True)
    controller.grant_permission("READ")
    controller.grant_permission("WRITE")


def create_plan(path: str = "nota.txt", content: str = "NOVO") -> Plan:
    return Plan(
        id="PLN-CC", objective="gravar nota", status=PlanStatus.READY,
        tasks=(PlannedTask(id="T1", description="criar nota", order=1,
                           tool="create_file",
                           parameters={"path": path, "content": content}),),
    )


def test_corrections_disabled_by_default_and_startup_is_clean(controller):
    assert controller.corrections_enabled is False
    assert controller.correction_history() == []


def test_legacy_failure_without_corrections(controller, ws):
    armed(controller, ws)
    controller.run_plan(create_plan())
    report = controller.approve("rodar original")  # create_file pausa (destrutiva)
    assert report.status is PlanStatus.FAILED  # arquivo já existe
    assert not controller.has_pending


def test_full_cycle_approve_correction_then_operation(controller, ws):
    """EXISTENTE → proposta → aprovar correção → checkpoint → executar ✔."""
    armed(controller, ws)
    controller.enable_corrections()
    controller.run_plan(create_plan())
    assert controller.pending_approval()["tool"] == "create_file"  # checkpoint
    report = controller.approve("executar original")  # roda e FALHA (existe)
    assert report.status is PlanStatus.FAILED
    assert controller.has_pending  # agora é a CORREÇÃO pendente
    pending = controller.pending_approval()
    assert pending["kind"] == "correction"
    assert pending["original_tool"] == "create_file"
    assert pending["tool"] == "write_file"
    assert pending["description"].startswith("O arquivo já existe")
    assert pending["failure_kind"] == "execution"
    assert pending["corrected_parameters"] == {"path": "nota.txt",
                                               "content": "NOVO"}
    assert (ws / "nota.txt").read_text(encoding="utf-8") == "ORIGINAL"

    report = controller.approve("correção ok")     # aplica e retoma…
    assert controller.has_pending                  # …e pausa no checkpoint
    operation = controller.pending_approval()
    assert operation.get("kind") is None           # card de OPERAÇÃO normal
    assert operation["tool"] == "write_file"
    assert operation["plan_id"].endswith("#C1")    # plano sucessor
    assert (ws / "nota.txt").read_text(encoding="utf-8") == "ORIGINAL"

    report = controller.approve("operação ok")     # executa de verdade
    assert report.status is PlanStatus.COMPLETED
    assert (ws / "nota.txt").read_text(encoding="utf-8") == "NOVO"
    statuses = [c["status"] for c in controller.correction_history()]
    assert statuses == ["PROPOSED", "APPROVED", "APPLIED", "RETRIED",
                        "SUCCEEDED"]


def test_refused_correction_changes_nothing(controller, ws):
    armed(controller, ws)
    controller.enable_corrections()
    controller.run_plan(create_plan())
    controller.approve("executar original")  # falha "já existe"
    report = controller.refuse("não sobrescreva")
    assert report.status is PlanStatus.FAILED
    assert (ws / "nota.txt").read_text(encoding="utf-8") == "ORIGINAL"
    statuses = [c["status"] for c in controller.correction_history()]
    assert statuses == ["PROPOSED", "REFUSED"]
    assert not controller.has_pending


def test_invalid_correction_is_blocked_and_audited(controller, ws):
    """Proposta de ferramenta não registrada: INVALID — nunca aplicada."""
    from app.executor.correction import CorrectionProposal

    class GhostToolStrategy(ToolCorrectionStrategy):
        def propose_correction(self, task, run):
            corrected = replace(task, tool="nao_existe_tool")
            return CorrectionProposal(suggestion="usar tool fantasma",
                                      corrected_task=corrected)

    armed(controller, ws)
    controller.enable_corrections(GhostToolStrategy())
    controller.run_plan(create_plan())
    report = controller.approve("executar original")
    assert report.status is PlanStatus.FAILED
    assert not controller.has_pending  # inválida nem pausa
    statuses = [c["status"] for c in controller.correction_history()]
    assert statuses == ["PROPOSED", "INVALID"]
    audit = [r for r in controller.audit_records()
             if r["tool"] == "correction"]
    assert any(r["operation"] == "correction_invalid" and not r["success"]
               for r in audit)


def test_correction_never_bypasses_missing_permission(controller, ws):
    """Sem WRITE: falha é de permissão — estratégia NÃO propõe nada."""
    controller.add_workspace(str(ws), writable=True)  # sem grant de WRITE
    controller.enable_corrections()
    report = controller.run_plan(create_plan())
    assert report.status is PlanStatus.FAILED
    assert "WRITE" in (report.task_run("T1").error or "")
    statuses = [c["status"] for c in controller.correction_history()]
    assert statuses == ["NO_PROPOSAL"]  # marcador de segurança → nada proposto
    assert not controller.has_pending


def test_correction_without_viable_path_is_invalid(controller, ws, tmp_path):
    """Correção para caminho FORA do workspace: validator bloqueia."""
    from app.executor.correction import CorrectionProposal

    class EvilPathStrategy(ToolCorrectionStrategy):
        def propose_correction(self, task, run):
            corrected = replace(
                task, parameters={"path": "../../fora.txt", "content": "x"},
            )
            return CorrectionProposal(suggestion="escrever fora",
                                      corrected_task=corrected)

    armed(controller, ws)
    controller.enable_corrections(EvilPathStrategy())
    controller.run_plan(create_plan())
    report = controller.approve("executar original")
    assert report.status is PlanStatus.FAILED
    statuses = [c["status"] for c in controller.correction_history()]
    assert statuses == ["PROPOSED", "INVALID"]
    assert not (tmp_path / "fora.txt").exists()


def test_max_cycles_zero_disables_loop_entirely(controller, ws):
    armed(controller, ws)
    controller.enable_corrections(max_cycles=0)
    controller.run_plan(create_plan())
    report = controller.approve("executar original")
    assert report.status is PlanStatus.FAILED
    statuses = [c["status"] for c in controller.correction_history()]
    assert statuses == ["EXHAUSTED"]
    assert not controller.has_pending


def test_loop_is_bounded_no_infinite_retry(controller, ws):
    """Correção que sempre reproposta: para no max_cycles (execuções ﬁnitas)."""
    from app.executor.correction import CorrectionProposal

    class AlwaysWrongStrategy(ToolCorrectionStrategy):
        def propose_correction(self, task, run):
            corrected = replace(task, tool="create_file")  # falha de novo
            return CorrectionProposal(suggestion="tentar de novo",
                                      corrected_task=corrected,
                                      requires_approval=False)

    armed(controller, ws)
    controller.enable_corrections(AlwaysWrongStrategy(), max_cycles=3)
    controller.run_plan(create_plan())
    report = controller.approve("executar original")
    approvals = 1
    while report.status is PlanStatus.RUNNING:  # checkpoint de cada retry
        assert approvals < 12, "loop não terminou: retry infinito?"
        report = controller.approve("seguir retry")
        approvals += 1
    assert report.status is PlanStatus.FAILED
    assert approvals < 12  # parou em número finito de decisões
    statuses = [c["status"] for c in controller.correction_history()]
    assert statuses.count("APPLIED") == 3
    assert statuses[-1] == "EXHAUSTED"
    execuções = [c for c in statuses if c in ("RETRIED",)]
    assert len(execuções) == 3  # 1 original + 3 correções = finito


def test_correction_cycle_is_audited_in_jsonl(controller, ws, tmp_path):
    armed(controller, ws)
    controller.enable_corrections()
    controller.run_plan(create_plan())
    controller.approve("executar original")  # falha → proposta
    controller.approve("ok")                 # aplica correção
    controller.approve("ok 2")               # executa write_file
    text = (tmp_path / "audit" / "audit.jsonl").read_text(encoding="utf-8")
    for operation in ("correction_proposed", "correction_applied",
                      "correction_retried"):
        assert operation in text
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    correction = [r for r in records if r["tool"] == "correction"]
    assert all((r.get("detail") or {}).get("task_id") == "T1" for r in correction)
    # sem conteúdo sensível além do necessário (suggestion/parametros não vão)
    assert all("content" not in (r.get("detail") or {}) for r in correction)


def test_disable_corrections_restores_direct_mode(controller, ws):
    armed(controller, ws)
    controller.enable_corrections()
    assert controller.corrections_enabled is True
    controller.disable_corrections()
    controller.run_plan(create_plan())
    report = controller.approve("executar original")
    assert report.status is PlanStatus.FAILED
    assert controller.correction_history() == []


def test_enable_corrections_validates_limits(controller):
    with pytest.raises(ToolsControlError):
        controller.enable_corrections(max_cycles=-1)
    with pytest.raises(ToolsControlError):
        controller.enable_corrections(max_total_attempts=0)


def test_original_plan_object_stays_immutable(controller, ws):
    armed(controller, ws)
    controller.enable_corrections()
    plan = create_plan()
    frozen = plan.tasks[0].tool, dict(plan.tasks[0].parameters or {})
    controller.run_plan(plan)
    controller.approve("executar original")
    controller.approve("ok")
    controller.approve("ok 2")
    assert (plan.tasks[0].tool, dict(plan.tasks[0].parameters or {})) == frozen
    assert plan.id == "PLN-CC"


# ------------------------------------------------------------------- UI
def test_dialog_shows_correction_card_and_approves_chain(tmp_path, ws):
    import app.ui.tools_dialog as tools_dialog_module
    from tests.fake_tk import FakeMessagebox, FakeRoot, FakeTkModule

    controller = ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )
    armed(controller, ws)
    controller.enable_corrections()
    controller.run_plan(create_plan())

    original_tk = tools_dialog_module.tk
    tools_dialog_module.tk = FakeTkModule()
    tools_dialog_module.messagebox = FakeMessagebox(True)
    try:
        dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
        assert "CORREÇÃO PROPOSTA" not in dialog.pending_label.cget("text")
        dialog._approve()  # executa create_file → falha (já existe) → proposta
        text = dialog.pending_label.cget("text")
        assert "CORREÇÃO PROPOSTA" in text
        assert "create_file → write_file" in text
        assert "Falha de execução" in text
        dialog._approve()  # aprova correção → pausa no checkpoint
        assert controller.has_pending
        operation = controller.pending_approval()
        assert operation.get("kind") is None and operation["tool"] == "write_file"
        dialog._approve()  # aprova operação → executa
        assert (ws / "nota.txt").read_text(encoding="utf-8") == "NOVO"
        assert "CORREÇÃO PROPOSTA" not in dialog.pending_label.cget("text")
    finally:
        tools_dialog_module.tk = original_tk


def test_dialog_refused_correction_keeps_file(tmp_path, ws):
    import app.ui.tools_dialog as tools_dialog_module
    from tests.fake_tk import FakeMessagebox, FakeRoot, FakeTkModule

    controller = ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )
    armed(controller, ws)
    controller.enable_corrections()
    controller.run_plan(create_plan())

    original_tk = tools_dialog_module.tk
    tools_dialog_module.tk = FakeTkModule()
    tools_dialog_module.messagebox = FakeMessagebox(True)
    try:
        dialog = tools_dialog_module.ToolsDialog(FakeRoot(), controller)
        dialog._approve()  # executa create_file → falha → correção pendente
        dialog._refuse()
        assert (ws / "nota.txt").read_text(encoding="utf-8") == "ORIGINAL"
        assert not controller.has_pending
        assert "NÃO foi executada" in dialog.status_label.cget("text")
    finally:
        tools_dialog_module.tk = original_tk


# ------------------------------------------------- 11G etapa 0 (verifier no modo corrections)
def mini_suite_fail(ws: Path) -> None:
    """Cria a mini-suite VERMELHA (1 teste que falha) no workspace."""
    suite = ws / "mini_tests"
    suite.mkdir()
    (suite / "test_fail.py").write_text(
        "def test_fail():\n    assert False, 'falha de propósito'\n",
        encoding="utf-8",
    )


def pytask(task_id: str, order: int = 2,
           dependencies: tuple[str, ...] = ()) -> PlannedTask:
    """Task run_pytest sobre a mini-suite do workspace."""
    return PlannedTask(
        id=task_id,
        description="rodar pytest (mini_tests)",
        order=order,
        dependencies=dependencies,
        tool="run_pytest",
        parameters={"path": "mini_tests", "maxfail": 1, "timeout_s": 60},
    )


def green_suite(ws: Path, name: str) -> None:
    """Cria uma mini-suite VERDE (1 teste que passa) em ``ws/<name>``."""
    suite = ws / name
    suite.mkdir()
    (suite / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8",
    )


def test_11g_corrections_branch_respects_verifier_for_run_pytest_red(tmp_path, ws):
    """11G etapa 0: corrections ON + verificação ON + pytest VERMELHO ⇒
    task REJECTED (verified=False), não DONE — o verifier 11E aplica em
    modo corrections (bypass corrigido no branch de corrections)."""
    permissions = PermissionManager()
    permissions.grant("TERMINAL")  # concessão programática (padrão 11E)
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )
    armed(controller, ws)
    controller.enable_terminal()
    controller.enable_verification("pytest_result")
    controller.enable_corrections()
    mini_suite_fail(ws)
    plan = Plan(
        id="PLN-11G", objective="11G: pytest vermelho em modo corrections",
        status=PlanStatus.READY,
        tasks=(
            PlannedTask(id="T1", description="criar x.txt", order=1,
                        tool="create_file",
                        parameters={"path": "x.txt", "content": "ok"}),
            pytask("T2", order=2, dependencies=("T1",)),
        ),
    )
    controller.run_plan(plan)
    assert controller.has_pending  # checkpoint do T1 (destrutiva)
    controller.approve("T1 ok")
    assert controller.has_pending  # checkpoint do T2 (TERMINAL, 11D)
    report = controller.approve("rodar pytest")  # pytest roda e FALHA
    # Verifier aplicado no modo corrections (etapa 0): vermelho ⇒ REJECTED.
    assert report.status is PlanStatus.FAILED
    assert not controller.has_pending  # sem proposta p/ run_pytest (falha honesta)
    run = report.task_run("T2")
    assert run.status.value == "REJECTED"
    assert run.verified is False
    assert run.error  # motivo claro (resumo do pytest preservado)
    assert report.task_run("T1").status.value == "DONE"  # rodou antes da evidência


def test_11g_successor_c_appends_run_pytest_when_root_had_pytest_earlier(tmp_path, ws):
    """11G etapa 1: root com run_pytest NÃO último (11F não anexa no root);
    o sucessor #C — com WRITE e sem run_pytest herdado — recebe 1 task
    final run_pytest via plan_transform, executada por último e verificada."""
    from app.executor.correction import CorrectionProposal

    permissions = PermissionManager()
    permissions.grant("TERMINAL")  # concessão programática (padrão 11E/11G)
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )

    class RewriteExistingStrategy(ToolCorrectionStrategy):
        def propose_correction(self, task, run):
            if task.tool == "create_file":
                return CorrectionProposal(
                    suggestion="gravar por cima (write_file)",
                    corrected_task=replace(task, tool="write_file"),
                    requires_approval=True,
                )
            return None

    armed(controller, ws)
    controller.enable_terminal()
    controller.enable_verification("pytest_result")
    controller.enable_corrections(RewriteExistingStrategy())
    green_suite(ws, "mini_tests")  # alvo do T1
    green_suite(ws, "tests")       # alvo do anexo 11F (path="tests")
    (ws / "x.txt").write_text("original", encoding="utf-8")  # T2 falha

    plan = Plan(
        id="PLN-11G2", objective="11G: anexar run_pytest ao sucessor #C",
        status=PlanStatus.READY,
        tasks=(
            pytask("T1", order=1),  # run_pytest mini_tests — NÃO é último
            PlannedTask(id="T2", description="criar x.txt", order=2,
                        dependencies=("T1",), tool="create_file",
                        parameters={"path": "x.txt", "content": "novo"}),
        ),
    )
    controller.run_plan(plan)
    # 11F NÃO anexa no root (run_pytest já está no plano — idempotência)
    assert [t.id for t in controller._plan.tasks] == ["T1", "T2"]

    assert controller.has_pending  # checkpoint T1 (run_pytest, TERMINAL)
    controller.approve("T1 ok")    # verde ⇒ DONE + verified=True
    assert controller.has_pending  # checkpoint T2 (create_file, destrutiva)
    controller.approve("T2 rodar") # roda e FALHA (arquivo já existe)
    assert controller.has_pending  # correção pendente
    assert controller.pending_approval()["kind"] == "correction"

    controller.approve("corrigir")  # aplica o #C1 (com plan_transform)
    # Sucessor #C1: T2 corrigida (write_file) + run_pytest ANEXADA ao final.
    successor = controller._engine.current_plan
    assert successor.id.endswith("#C1")
    attached = successor.tasks[-1]
    assert attached.tool == "run_pytest"
    assert attached.id not in ("T1", "T2")
    assert attached.parameters == {"path": "tests"}
    assert attached.dependencies == ("T2",)
    assert controller.has_pending  # checkpoint T2' (write_file)

    controller.approve("escrita ok")         # T2' roda ⇒ DONE
    assert controller.has_pending            # checkpoint T3 (run_pytest anexada)
    report = controller.approve("pytest ok")  # verde ⇒ DONE + verified=True

    # Asserts finais
    assert report.status is PlanStatus.COMPLETED
    assert not controller.has_pending
    assert [t.id for t in report.tasks] == ["T2", "T3"]
    assert report.task_run("T2").status.value == "DONE"
    assert (ws / "x.txt").read_text(encoding="utf-8") == "novo"
    final = report.task_run("T3")
    assert final.status.value == "DONE"
    assert final.verified is True  # evidência verde real no sucessor
    assert final.dependencies == ("T2",)
    statuses = [c["status"] for c in controller.correction_history()]
    assert statuses[-1] == "SUCCEEDED"


# ------------------------------------------------- 11J (advice-only com evidência)
def test_11j_pytest_failure_records_evidence_advice_in_cycle(tmp_path, ws):
    """11J MVP: pytest VERMELHO + corrections (strategy default) ⇒ o ciclo
    registra conselho com evidência (NO_PROPOSAL) e encerra **sem pausa**
    (advice-only: corrected_task=None → nada aplicado, sem pending)."""
    permissions = PermissionManager()
    permissions.grant("TERMINAL")  # concessão programática (padrão 11E/11G)
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit" / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )
    armed(controller, ws)
    controller.enable_terminal()
    controller.enable_verification("pytest_result")
    controller.enable_corrections()  # default: EvidenceCorrectionStrategy
    assert isinstance(
        controller._corrections["strategy"], EvidenceCorrectionStrategy
    )
    mini_suite_fail(ws)
    plan = Plan(
        id="PLN-11J", objective="11J: conselho com evidência no pytest vermelho",
        status=PlanStatus.READY,
        tasks=(
            PlannedTask(id="T1", description="criar x.txt", order=1,
                        tool="create_file",
                        parameters={"path": "x.txt", "content": "ok"}),
            pytask("T2", order=2, dependencies=("T1",)),
        ),
    )
    controller.run_plan(plan)
    assert controller.has_pending  # checkpoint do T1 (destrutiva)
    controller.approve("T1 ok")
    assert controller.has_pending  # checkpoint do T2 (TERMINAL, 11D)
    report = controller.approve("rodar pytest")  # vermelho ⇒ REJECTED

    # advice-only: loop encerra sem pausa / sem pending correction.
    assert report.status is PlanStatus.FAILED
    assert not controller.has_pending
    run = report.task_run("T2")
    assert run.status.value == "REJECTED"
    assert run.verified is False

    # Ciclo com conselho enriquecido (evidência) — sem tarefa corrigida.
    cycles = controller.correction_history()
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle["task_id"] == "T2"
    assert cycle["status"] in ("NO_PROPOSAL", "FAILED")
    assert "pytest" in (cycle.get("suggestion") or "")
    assert "somente conselho" in (cycle.get("decision_note") or "")
    assert cycle.get("replacement_tool") is None  # corrected_task=None (MVP)
