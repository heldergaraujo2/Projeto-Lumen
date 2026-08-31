"""Execution State persistido (9B) — bundles sanitizados em app/memory.

ExecutionBundleStore grava plan + ExecutionReport (+ correções) em JSON
atômico: redact_secrets em toda string, truncamento 16 KiB, remoção de
stdout/stderr e do content integral de read_file, result JSON
parse→sanitize→re-dumps. Integração OPT-IN (default OFF) e best-effort
via _maybe_persist_execution_state (control.py) — falha do sink jamais
mascara o resultado. Sem execução de ferramentas reais nestes testes.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from app.config.settings import Settings
from app.memory.execution_store import (
    ExecutionBundleStore,
    sanitize_any,
    sanitize_result_string,
)
from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus
from app.executor.executor import ExecutionReport, TaskRun
from app.tools.control import ToolsController, _maybe_persist_execution_state

LIMIT = 16 * 1024
SECRET = "sk-abcdefgh12345678"


# ---------------------------------------------------------------- helpers
class FakeReport:
    """Report sintético (to_dict) — sem executar nada."""

    def __init__(self, result: str | None = None, description: str = "ler a.txt"):
        self.plan_id = "PLN-9B"
        self._result = result
        self._description = description

    def to_dict(self) -> dict:
        return {
            "plan_id": "PLN-9B",
            "status": "COMPLETED",
            "tasks": [{
                "id": "T1", "description": self._description, "order": 1,
                "dependencies": [], "status": "DONE",
                "result": self._result, "error": None,
            }],
        }


def make_plan() -> Plan:
    return Plan(id="PLN-9B", objective="teste 9B", status=PlanStatus.READY, tasks=(
        PlannedTask("T1", "ler a.txt", 1, tool="read_file",
                    parameters={"path": "a.txt"}),
    ))


def make_report(result: str | None = None, description: str = "ler a.txt") -> ExecutionReport:
    return ExecutionReport(
        plan_id="PLN-9B", objective="teste 9B", status=PlanStatus.COMPLETED,
        tasks=(TaskRun(id="T1", description=description, order=1,
                       dependencies=(), status=PlannedTaskStatus.DONE,
                       result=result),),
        events=(), started_at="t0", finished_at="t1",
    )


def persisted_result(path: Path) -> str:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    return bundle["execution_report"]["tasks"][0]["result"]


# --------------------------------------------- store puro (1–8)
def test_bundle_criado_e_valido(tmp_path):
    """(1) save_bundle cria JSON válido com metadados + plan + report."""
    path = ExecutionBundleStore(tmp_path).save_bundle(
        plan=make_plan(), report=make_report(), lumen_version="0.6.7",
    )
    assert path == tmp_path / "PLN-9B.json" and path.exists()
    bundle = json.loads(path.read_text(encoding="utf-8"))
    assert bundle["version"] == 1
    assert bundle["lumen_version"] == "0.6.7"
    assert bundle["plan_id"] == "PLN-9B"
    assert bundle["saved_at"]
    assert bundle["plan"]["id"] == "PLN-9B"
    assert bundle["execution_report"]["status"] == "COMPLETED"


def test_redact_secrets_aplicado(tmp_path):
    """(2) segredo é redigido em toda string persistida."""
    report = make_report(description=f"anotar chave {SECRET}")
    path = ExecutionBundleStore(tmp_path).save_bundle(
        plan=make_plan(), report=report,
    )
    raw = path.read_text(encoding="utf-8")
    assert SECRET not in raw
    assert "***" in raw


def test_truncamento_16kib(tmp_path):
    """(3) string > 16 KiB é truncada com marcador."""
    big = "A" * (LIMIT + 5000)
    report = make_report(description=big)
    path = ExecutionBundleStore(tmp_path).save_bundle(plan=make_plan(), report=report)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    description = persisted["execution_report"]["tasks"][0]["description"]
    assert len(description.encode("utf-8")) <= LIMIT
    assert description.endswith("…[truncado]")


def test_stdout_ausente_no_bundle(tmp_path):
    """(4) stdout presente no resultado NÃO vai para o bundle."""
    result = json.dumps({"ok": True, "data": {
        "stdout": "SAIDA-SENSIVEL", "exit_code": 0,
    }, "error": None})
    path = ExecutionBundleStore(tmp_path).save_bundle(
        plan=make_plan(), report=make_report(result),
    )
    raw = path.read_text(encoding="utf-8")
    assert "stdout" not in raw and "SAIDA-SENSIVEL" not in raw


def test_stderr_ausente_no_bundle(tmp_path):
    """(5) stderr presente no resultado NÃO vai para o bundle."""
    result = json.dumps({"ok": True, "data": {
        "stderr": "ERRO-SENSIVEL", "exit_code": 1,
    }, "error": None})
    path = ExecutionBundleStore(tmp_path).save_bundle(
        plan=make_plan(), report=make_report(result),
    )
    raw = path.read_text(encoding="utf-8")
    assert "stderr" not in raw and "ERRO-SENSIVEL" not in raw


def test_read_file_content_ausente_no_bundle(tmp_path):
    """(6) content integral de read_file é removido; metadados ficam."""
    result = json.dumps({"ok": True, "data": {
        "content": "CONTEUDO-INTEGRAL-SECRETO", "size_bytes": 27,
        "resolved_path": "/tmp/ws/a.txt",
    }, "error": None})
    path = ExecutionBundleStore(tmp_path).save_bundle(
        plan=make_plan(), report=make_report(result),
    )
    data = json.loads(persisted_result(path))["data"]
    assert "content" not in data
    assert data["size_bytes"] == 27
    assert data["resolved_path"].endswith("a.txt")
    assert "CONTEUDO-INTEGRAL-SECRETO" not in path.read_text(encoding="utf-8")


def test_result_json_sanitizado_e_resserializado(tmp_path):
    """(7) TaskRun.result JSON: parse → sanitize (stdout/content fora,
    secret redigido) → re-dumps JSON válido; e >16 KiB truncado."""
    result = json.dumps({"ok": True, "data": {
        "note": f"chave {SECRET} aqui", "stdout": "x", "content": "y",
    }, "error": None})
    path = ExecutionBundleStore(tmp_path).save_bundle(
        plan=make_plan(), report=make_report(result),
    )
    persisted = json.loads(persisted_result(path))  # JSON re-válido
    assert persisted["data"]["note"] == "chave *** aqui"
    assert "stdout" not in persisted["data"] and "content" not in persisted["data"]

    # resultado gigante: string final truncada ao limite
    huge = json.dumps({"ok": True, "data": {"note": "B" * (LIMIT * 2)}, "error": None})
    path2 = ExecutionBundleStore(tmp_path).save_bundle(
        plan=make_plan(), report=make_report(huge),
    )
    assert len(persisted_result(path2).encode("utf-8")) <= LIMIT


def test_escrita_atomica_sem_tmp(tmp_path):
    """(8) nenhum .tmp sobra após save_bundle."""
    ExecutionBundleStore(tmp_path).save_bundle(
        plan=make_plan(), report=make_report(),
    )
    assert not list(tmp_path.glob("*.tmp"))
    assert list(tmp_path.glob("*.json")) == [tmp_path / "PLN-9B.json"]


# ------------------------------------------------- configuração (9)
def test_persistencia_desligada_por_padrao():
    """(9) Settings.persist_execution_state default False + execution_dir."""
    settings = Settings()
    assert settings.persist_execution_state is False
    assert str(settings.execution_dir).endswith("executions")


# ------------------------------------------ integração helper (10–12)
def test_helper_off_nao_cria_on_cria(tmp_path):
    """(10) OFF: nada criado; ON: bundle criado (objetos sintéticos)."""
    # OFF — nem diretório nasce
    off_dir = tmp_path / "exec-off"
    _maybe_persist_execution_state(
        SimpleNamespace(persist_execution_state=False, execution_dir=off_dir),
        make_plan(), FakeReport(),
    )
    assert not off_dir.exists()

    # ON — bundle criado no diretório indicado
    on_dir = tmp_path / "exec-on"
    _maybe_persist_execution_state(
        SimpleNamespace(persist_execution_state=True, execution_dir=on_dir),
        make_plan(), FakeReport(), correction=[{"status": "APPLIED"}],
    )
    bundles = list(on_dir.glob("*.json"))
    assert bundles == [on_dir / "PLN-9B.json"]
    bundle = json.loads(bundles[0].read_text(encoding="utf-8"))
    assert bundle["correction"] == [{"status": "APPLIED"}]


def test_helper_best_effort_nao_propaga_falha(tmp_path):
    """(extra) sink quebrado (dir = arquivo) não levanta exceção."""
    blocker = tmp_path / "blocker"
    blocker.write_text("sou um arquivo", encoding="utf-8")
    _maybe_persist_execution_state(  # não deve raise
        SimpleNamespace(persist_execution_state=True, execution_dir=blocker),
        make_plan(), FakeReport(),
    )


def test_result_nao_json_recebe_marcador_seguro(tmp_path):
    """(extra) result não-JSON: redigido+truncado + <unparseable ToolResult>."""
    path = ExecutionBundleStore(tmp_path).save_bundle(
        plan=make_plan(), report=make_report(result=f"texto solto {SECRET}"),
    )
    persisted = persisted_result(path)
    assert persisted.endswith("<unparseable ToolResult>")
    assert SECRET not in persisted and "***" in persisted


def test_wiring_todos_retornos_terminais_envolvem_final():
    """(extra/contrato) run_plan, approve e refuse passam por _final (8 pts)."""
    for method in ("run_plan", "approve", "refuse"):
        source = inspect.getsource(getattr(ToolsController, method))
        assert "_final(" in source, method


def test_sanitize_any_puro():
    """(extra) sanitize_any: shape ToolResult ⇒ campos proibidos removidos."""
    value = {"ok": True, "data": {"stdout": "s", "stderr": "e", "content": "c",
                                  "n": 1}, "error": None}
    assert sanitize_any(value) == {"ok": True, "data": {"n": 1}, "error": None}
    assert sanitize_result_string("não sou json") .endswith(
        "<unparseable ToolResult>",
    )
