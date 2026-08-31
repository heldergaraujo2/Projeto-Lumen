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
from app.tools.correction import ToolCorrectionStrategy

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
