"""Testes de retry + verificação + preparação de correção (0.4.x) — offline.

Cobrem: retry controlado (com sucesso, até o limite, após erro), log de
tentativas, verificação de resultado (sucesso/falha/tarefa reprovada),
determinismo, segurança contra retry infinito e ausência de execução
real / ausência de correção automática.
"""
from __future__ import annotations

import pytest

from app.executor import (
    AttemptRecord,
    CorrectionProposal,
    CorrectionStrategy,
    NoopCorrectionStrategy,
    PlanExecutor,
    RetryPolicy,
    SimulatedHandler,
    SimulatedVerifier,
    TaskHandler,
    TaskVerifier,
    VerificationResult,
)
from app.executor.handlers import HandlerError
from app.planner.models import Plan, PlanStatus, PlannedTask, PlannedTaskStatus


class FlakyHandler(TaskHandler):
    """Falha as N primeiras chamadas por tarefa; depois tem sucesso."""

    name = "flaky"

    def __init__(self, failures_before_success: int, message="instável"):
        self._failures = failures_before_success
        self._message = message
        self.calls: list[str] = []

    def execute(self, task):
        self.calls.append(task.id)
        if len(self.calls) <= self._failures:
            raise HandlerError(f"{self._message} (tentativa {len(self.calls)})")
        return "ok depois de falhar"


class AlwaysFailHandler(TaskHandler):
    name = "always-fail"
    count = 0

    def execute(self, task):
        type(self).count += 1
        raise HandlerError("sempre quebra")


def make_plan(tasks=None):
    specs = tasks or [("a", []), ("b", ["T1"])]
    planned = [
        PlannedTask(id=f"T{i}", description=d, order=i, dependencies=tuple(deps))
        for i, (d, deps) in enumerate(specs, start=1)
    ]
    return Plan(id="PLN-0001", objective="o", status=PlanStatus.READY,
                tasks=tuple(planned))


# ----------------------------------------------------------------- retry
def test_retry_succeeds_after_transient_error():
    handler = FlakyHandler(failures_before_success=2)
    report = PlanExecutor(make_plan([("a", [])]), handler,
                          retry=RetryPolicy(max_attempts=3)).run_all()
    assert report.completed
    run = report.task_run("T1")
    assert run.status is PlannedTaskStatus.DONE
    assert run.attempts == 3                       # 2 falhas + sucesso
    assert run.result == "ok depois de falhar"
    assert [a.error for a in run.attempt_log] == [
        "instável (tentativa 1)", "instável (tentativa 2)", None,
    ]  # resultado de cada tentativa preservado
    assert [a.number for a in run.attempt_log] == [1, 2, 3]
    kinds = [e.kind for e in report.events]
    assert kinds.count("task_retry") == 2


def test_retry_stops_at_limit_and_fails_plan():
    AlwaysFailHandler.count = 0
    report = PlanExecutor(
        make_plan([("a", []), ("b", ["T1"])]), AlwaysFailHandler(),
        retry=RetryPolicy(max_attempts=3),
    ).run_all()
    assert report.status is PlanStatus.FAILED
    run = report.task_run("T1")
    assert run.status is PlannedTaskStatus.FAILED
    assert run.attempts == 3
    assert all(a.error == "sempre quebra" for a in run.attempt_log)
    assert report.task_run("T2").status is PlannedTaskStatus.SKIPPED


def test_retry_cannot_be_infinite():
    """Segurança: tentativas limitadas ao máximo configurado — nada mais roda."""
    AlwaysFailHandler.count = 0
    PlanExecutor(make_plan([("a", [])]), AlwaysFailHandler(),
                 retry=RetryPolicy(max_attempts=5)).run_all()
    assert AlwaysFailHandler.count == 5            # exatamente o limite


def test_retry_policy_validation_rejects_invalid_values():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)                # sem retry infinito/zero
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=-3)
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=2, backoff_seconds=-1)


def test_retry_backoff_is_injectable_and_linear():
    delays: list[float] = []
    handler = FlakyHandler(failures_before_success=2)
    report = PlanExecutor(
        make_plan([("a", [])]), handler,
        retry=RetryPolicy(max_attempts=3, backoff_seconds=0.5),
        sleeper=delays.append,                     # sem dormir de verdade
    ).run_all()
    assert report.completed
    assert delays == [0.5, 1.0]                     # 0,5×1 e 0,5×2 (linear)


def test_unexpected_handler_error_is_not_retried():
    class Buggy(TaskHandler):
        name = "buggy"
        calls = 0
        def execute(self, task):
            Buggy.calls += 1
            raise RuntimeError("bug fora do contrato")

    report = PlanExecutor(make_plan([("a", [])]), Buggy(),
                          retry=RetryPolicy(max_attempts=4)).run_all()
    assert report.status is PlanStatus.FAILED
    assert Buggy.calls == 1                         # inesperado NÃO repete
    assert "inesperado" in (report.error or "")


def test_default_policy_is_single_attempt():
    report = PlanExecutor(make_plan(), SimulatedHandler()).run_all()
    assert all(r.attempts == 1 for r in report.tasks)


# ------------------------------------------------------------ verificação
def test_verification_success_marks_task_done_and_verified():
    handler = SimulatedHandler(results={"T1": "resultado bom"})
    report = PlanExecutor(make_plan([("a", [])]), handler,
                          verifier=SimulatedVerifier()).run_all()
    assert report.completed
    run = report.task_run("T1")
    assert run.status is PlannedTaskStatus.DONE
    assert run.verified is True                     # EXECUTOU→VERIFICOU→SUCESSO
    assert run.result == "resultado bom"
    kinds = [e.kind for e in report.events]
    assert "task_verification_passed" in kinds


def test_verification_failure_rejects_executed_task():
    """EXECUTOU → VERIFICOU → FALHOU: resultado existe, mas foi reprovado."""
    handler = SimulatedHandler(results={"T1": "resultado ruim"})
    report = PlanExecutor(
        make_plan([("a", []), ("b", ["T1"])]), handler,
        verifier=SimulatedVerifier(failures={"T1": "saída não bate com o esperado"}),
    ).run_all()
    assert report.status is PlanStatus.FAILED
    run = report.task_run("T1")
    assert run.status is PlannedTaskStatus.REJECTED
    assert run.verified is False
    assert run.result == "resultado ruim"           # executou (resultado preservado)
    assert "saída não bate" in (run.error or "")
    assert report.task_run("T2").status is PlannedTaskStatus.SKIPPED
    kinds = [e.kind for e in report.events]
    assert "task_verification_failed" in kinds


def test_verification_failure_does_not_consume_retry():
    """Reprovação de verificação NÃO repete (correção automática é futura)."""
    calls: list[str] = []

    class Counting(SimulatedHandler):
        def execute(self, task):
            calls.append(task.id)
            return super().execute(task)

    report = PlanExecutor(
        make_plan([("a", [])]), Counting(),
        verifier=SimulatedVerifier(failures={"T1": "não passou"}),
        retry=RetryPolicy(max_attempts=5),
    ).run_all()
    assert report.status is PlanStatus.FAILED
    assert calls == ["T1"]                          # executou 1× e foi reprovada
    assert report.task_run("T1").attempts == 1


def test_without_verifier_there_is_no_verification():
    report = PlanExecutor(make_plan(), SimulatedHandler()).run_all()
    assert all(r.verified is None for r in report.tasks)
    kinds = [e.kind for e in report.events]
    assert "task_verification_passed" not in kinds
    assert "task_verification_failed" not in kinds


# ------------------------------------------- 11E: flag applied (verificação)
def test_verification_not_applicable_does_not_set_verified():
    """11E: ``applied=False`` = "não aplicável" — sem ``verified``, sem rejeitar."""

    class NotApplicableVerifier(TaskVerifier):
        name = "not-applicable"

        def verify(self, task, result):
            return VerificationResult(True, "not applicable", applied=False)

    handler = SimulatedHandler(results={"T1": "resultado ok"})
    report = PlanExecutor(make_plan([("a", [])]), handler,
                          verifier=NotApplicableVerifier()).run_all()
    assert report.completed
    run = report.task_run("T1")
    assert run.status is PlannedTaskStatus.DONE   # NÃO rejeitada
    assert run.verified is None                   # sem marca de verificação
    assert run.error is None
    kinds = [e.kind for e in report.events]
    assert "task_verification_passed" not in kinds
    assert "task_verification_failed" not in kinds


def test_verification_applied_sets_verified_true():
    """11E: ``applied=True`` + ``passed=True`` ⇒ ``verified=True`` (como antes)."""

    class AppliedVerifier(TaskVerifier):
        name = "applied"

        def verify(self, task, result):
            return VerificationResult(True, "ok", applied=True)

    handler = SimulatedHandler(results={"T1": "resultado ok"})
    report = PlanExecutor(make_plan([("a", [])]), handler,
                          verifier=AppliedVerifier()).run_all()
    assert report.completed
    run = report.task_run("T1")
    assert run.status is PlannedTaskStatus.DONE
    assert run.verified is True


def test_broken_verifier_is_controlled_not_crashing():
    class Broken(TaskVerifier):
        name = "broken"
        def verify(self, task, result):
            raise RuntimeError("bug do verificador")

    report = PlanExecutor(make_plan([("a", [])]), SimulatedHandler(),
                          verifier=Broken()).run_all()
    assert report.status is PlanStatus.FAILED
    assert "verificador falhou" in (report.error or "")


def test_verification_results_serialized_in_report():
    handler = SimulatedHandler(results={"T1": "ok"})
    report = PlanExecutor(make_plan([("a", [])]), handler,
                          verifier=SimulatedVerifier()).run_all()
    data = report.task_run("T1").to_dict()
    assert data["verified"] is True
    assert data["attempt_log"] == [{"number": 1, "result": "ok", "error": None}]


# --------------------------- abstrações de correção (implementada em 0.6.2)
def test_correction_abstractions_exist_and_noop_proposes_nothing():
    proposal = NoopCorrectionStrategy().propose_correction(
        make_plan().tasks[0],
        PlanExecutor(make_plan(), SimulatedHandler(failures={"T1": "x"})).run_all().task_run("T1"),
    )
    assert proposal is None  # Noop segue Noop; correção real: test_correction.py


def test_correction_contract_is_implementable():
    class AlwaysSuggest(CorrectionStrategy):
        def propose_correction(self, task, run):
            return CorrectionProposal(suggestion="revisar dependência",
                                      retry_recommended=True)

    proposal = AlwaysSuggest().propose_correction(None, None)
    assert proposal.retry_recommended and proposal.to_dict()["suggestion"]


def test_executor_does_not_call_correction_automatically():
    """O loop 'falha→análise→correção' NÃO está ligado no Executor."""
    import ast
    import pathlib

    source = pathlib.Path(
        __import__("app.executor.executor", fromlist=["__file__"]).__file__
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    identifiers = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree) if isinstance(node, (ast.Name, ast.Attribute))
    }
    assert "CorrectionStrategy" not in identifiers
    assert "propose_correction" not in identifiers


# ------------------------------------------------- determinismo / execução real
def test_retry_and_verification_flow_is_deterministic():
    def run_once():
        handler = FlakyHandler(failures_before_success=1)
        report = PlanExecutor(
            make_plan([("a", [])]), handler,
            verifier=SimulatedVerifier(failures={}),
            retry=RetryPolicy(max_attempts=2),
        ).run_all()
        return [(r.id, r.status, r.attempts, r.result, r.verified)
                for r in report.tasks]

    assert run_once() == run_once()


def test_attempt_record_shape():
    ok = AttemptRecord(number=1, result="r")
    bad = AttemptRecord(number=2, error="e")
    assert ok.ok and not bad.ok
    assert ok.to_dict() == {"number": 1, "result": "r", "error": None}


def test_verification_result_shape():
    assert VerificationResult(True, "bom").passed
    assert VerificationResult(False).to_dict() == {"passed": False, "detail": ""}


def test_no_real_execution_in_executor_package():
    """AST: nenhum import/identificador de ferramenta real (0.5+; vale p/ executor/)."""
    import ast
    import pathlib

    forbidden_imports = {
        "subprocess", "shutil", "ctypes", "socket", "urllib", "requests",
        "os", "pathlib", "pyautogui", "pynput", "app.tools",
    }
    forbidden_identifiers = {
        "subprocess", "popen", "shutil", "ctypes", "pyautogui", "pynput",
        "send_keys", "unreal", "win32api", "write_text", "write_bytes",
        "mkdir", "unlink",
    }
    root = pathlib.Path(__file__).parent.parent / "app" / "executor"
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_imports, (
                        f"{path.name} importa {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                assert module not in forbidden_imports, f"{path.name} importa {module}"
                assert not (node.module or "").startswith("app.tools"), (
                    f"{path.name} importa app.tools"
                )
            elif isinstance(node, (ast.Name, ast.Attribute)):
                name = node.attr if isinstance(node, ast.Attribute) else node.id
                assert name not in forbidden_identifiers, f"{path.name} usa {name}"
