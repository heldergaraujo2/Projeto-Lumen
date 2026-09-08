"""11B — SearchFilesTool: busca textual READ-ONLY no workspace.

Prova funcional pelo fluxo oficial: ``ToolsController.run_plan`` →
``PlanExecutor``/``ToolTaskHandler`` → ``ToolRegistry`` (porteio de
permissão READ) → ``MultiWorkspaceSandbox`` (resolve/check_operation) →
``SearchFilesTool`` → ``FilesystemAudit``. Nenhum teste instancia a tool
diretamente. Todo estado vive em ``tmp_path`` (nada toca o repositório).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from app.planner.models import Plan, PlanStatus, PlannedTask
from app.security.permissions import PermissionManager
from app.tools.control import ToolsController

# ----------------------------------------------------------------- helpers


def make_controller(tmp_path: Path, *, grant_read: bool = True, tag: str = "a"):
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    controller = ToolsController(
        PermissionManager(),
        workspaces_file=tmp_path / f"workspaces_{tag}.json",
        audit_file=tmp_path / "audit" / f"a_{tag}.jsonl",
        terminal_file=tmp_path / f"terminal_{tag}.json",
    )
    controller.add_workspace(str(ws), writable=False)
    if grant_read:
        controller.grant_permission("READ")
    return controller, ws


def search(controller, ws, tid, path, query, **extra):
    """Executa search_files pelo fluxo oficial (plan → run_plan)."""
    plan = Plan(
        id=f"PLN-{tid}",
        objective="busca",
        status=PlanStatus.READY,
        tasks=(
            PlannedTask(
                tid, "buscar texto", 1,
                tool="search_files",
                parameters={"path": path, "query": query, **extra},
            ),
        ),
    )
    report = controller.run_plan(plan)
    run = report.task_run(tid)
    raw = run.result
    payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return run, payload


def snapshot(ws: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in ws.rglob("*"):
        rel = str(p.relative_to(ws))
        if p.is_symlink():
            out[rel] = "LINK:" + os.readlink(p)
        elif p.is_file():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            out[rel] = "DIR"
    return out


# ------------------------------------------------- registro (fluxo oficial)
def test_registrada_no_registry_default_com_permissao_read(tmp_path):
    controller, ws = make_controller(tmp_path)
    listing = controller.build_registry().list_tools()
    meta = {t["name"]: t["required_permission"] for t in listing}
    assert "search_files" in meta
    assert meta["search_files"] == "READ"


def test_executa_pelo_fluxo_oficial_e_encontra_match(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "a.txt").write_text("lumen alpha token\n", encoding="utf-8")
    run, payload = search(controller, ws, "T1", ".", "alpha")
    assert str(run.status.value).upper() == "DONE"
    assert payload["ok"] is True
    data = payload["data"]
    assert data["operation"] == "search_files"
    match = next(m for m in data["matches"] if m["path"] == "a.txt")
    assert match["line"] == 1
    assert match["col"] == 7  # 1-based: "lumen alpha" → coluna 7
    assert "alpha" in match["line_text"]


def test_schema_estavel_do_resultado(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "a.txt").write_text("alpha\n", encoding="utf-8")
    _, payload = search(controller, ws, "T1", ".", "alpha")
    data = payload["data"]
    for key in (
        "operation", "requested_path", "resolved_path", "query",
        "files_scanned", "matches_returned", "truncated",
        "matches", "skipped",
    ):
        assert key in data, key
    for key in ("binary", "too_large", "errors"):
        assert key in data["skipped"], key
    for key in ("path", "line", "col", "line_text", "snippet"):
        assert key in data["matches"][0], key


# ------------------------------------------------------------- permissões
def test_sem_permissao_read_negada_e_auditada(tmp_path):
    controller, ws = make_controller(tmp_path, grant_read=False, tag="deny")
    (ws / "a.txt").write_text("alpha\n", encoding="utf-8")
    run, payload = search(controller, ws, "T1", ".", "alpha")
    assert str(run.status.value).upper() == "FAILED"
    assert "permiss" in (run.error or "").lower()
    audit = (tmp_path / "audit" / "a_deny.jsonl").read_text(encoding="utf-8")
    assert "search_files" in audit
    assert "permission_gate" in audit


# ---------------------------------------------------- sandbox/confidencial
def test_traversal_com_pontos_bloqueado(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "a.txt").write_text("alpha\n", encoding="utf-8")
    run, payload = search(controller, ws, "T1", "../fora", "x")
    # Contrato do projeto: bloqueio de sandbox = falha honesta da tarefa
    # (handler converte ToolResult ok=False em HandlerError; result=None).
    assert str(run.status.value).upper() == "FAILED"
    assert run.result is None
    assert "traversal" in (run.error or "").lower() or ".." in (run.error or "")
    audit = (tmp_path / "audit" / "a_a.jsonl").read_text(encoding="utf-8")
    assert "search_files" in audit  # bloqueio também é auditado


def test_caminho_absoluto_fora_bloqueado(tmp_path):
    controller, ws = make_controller(tmp_path)
    run, payload = search(controller, ws, "T1", "/etc", "root")
    assert str(run.status.value).upper() == "FAILED"
    assert run.result is None
    assert (run.error or "").strip() != ""


def test_symlink_diretorio_para_fora_nao_e_pesquisado(tmp_path):
    controller, ws = make_controller(tmp_path)
    sub = ws / "subdir"
    sub.mkdir()
    (sub / "b.txt").write_text("conteudo comum\n", encoding="utf-8")
    ext = tmp_path / "external_dir"
    ext.mkdir()
    (ext / "secret.txt").write_text("LUMEN_11B_EXTERNAL_TOKEN", encoding="utf-8")
    try:
        os.symlink(ext, sub / "link_dir", target_is_directory=True)
    except OSError as exc:
        # Windows: symlink may require Developer Mode / SeCreateSymbolicLinkPrivilege
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows sem privilégio para criar symlink (WinError 1314)")
        raise

    _, payload = search(controller, ws, "T1", "subdir", "LUMEN_11B_EXTERNAL_TOKEN")
    data = payload["data"]
    assert data["matches_returned"] == 0
    assert all("secret.txt" not in m["path"] for m in data["matches"])


def test_symlink_arquivo_para_fora_nao_e_pesquisado(tmp_path):
    controller, ws = make_controller(tmp_path)
    ext = tmp_path / "external_dir"
    ext.mkdir()
    (ext / "secret.txt").write_text("LUMEN_11B_EXTERNAL_TOKEN", encoding="utf-8")
    try:
        os.symlink(ext / "secret.txt", ws / "link_file")
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows sem privilégio para criar symlink (WinError 1314)")
        raise

    _, payload = search(controller, ws, "T1", ".", "LUMEN_11B_EXTERNAL_TOKEN")
    data = payload["data"]
    assert data["matches_returned"] == 0
    assert data["skipped"]["errors"] == 0  # escape é pulado, não é erro


def test_busca_interna_em_subdiretorio_funciona(tmp_path):
    controller, ws = make_controller(tmp_path)
    sub = ws / "subdir"
    sub.mkdir()
    (sub / "b.txt").write_text("conteudo comum\n", encoding="utf-8")
    _, payload = search(controller, ws, "T1", "subdir", "comum")
    assert payload["data"]["matches_returned"] == 1


# ------------------------------------------------------------ anti-DoS
def test_max_files_limita_varredura(tmp_path):
    controller, ws = make_controller(tmp_path)
    many = ws / "many"
    many.mkdir()
    for i in range(205):
        (many / f"f{i:03d}.txt").write_text("MANYTOKEN\n", encoding="utf-8")
    _, payload = search(controller, ws, "T1", "many", "MANYTOKEN")
    data = payload["data"]
    assert data["files_scanned"] <= 200
    assert data["matches_returned"] <= 200
    assert data["truncated"] is True


def test_max_matches_limita_resultado(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "many.txt").write_text(
        ("MATCHTOKEN " * 50 + "\n") * 10, encoding="utf-8"
    )  # 500 ocorrências
    _, payload = search(controller, ws, "T1", ".", "MATCHTOKEN")
    data = payload["data"]
    assert data["matches_returned"] == 200
    assert data["truncated"] is True


def test_snippet_e_line_text_limitados_em_bytes(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "long.txt").write_text(
        "A" * 500 + "NEEDLE" + "B" * 500 + "\n", encoding="utf-8"
    )
    _, payload = search(controller, ws, "T1", ".", "NEEDLE")
    for m in payload["data"]["matches"]:
        for field in ("snippet", "line_text"):
            assert len(m[field].encode("utf-8")) <= 200, field


def test_limites_personalizados_so_podem_reduzir(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "m.txt").write_text("tok tok tok tok\n", encoding="utf-8")
    _, payload = search(controller, ws, "T1", ".", "tok", max_matches=3)
    assert payload["data"]["matches_returned"] == 3
    _, payload = search(controller, ws, "T2", ".", "tok", max_matches=10_000)
    assert payload["data"]["matches_returned"] <= 200  # clamp no default


def test_parametro_de_limite_invalido_e_estruturado(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "a.txt").write_text("alpha\n", encoding="utf-8")
    run, _ = search(controller, ws, "T1", ".", "alpha", max_matches=0)
    assert str(run.status.value).upper() == "FAILED"
    assert "max_matches" in (run.error or "")


# ------------------------------------------------- binário / arquivo grande
def test_arquivo_binario_pulado(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "bin.dat").write_bytes(b"\x00\x01\x02BINARY")
    _, payload = search(controller, ws, "T1", ".", "BINARY")
    data = payload["data"]
    assert data["matches_returned"] == 0
    assert data["skipped"]["binary"] >= 1


def test_arquivo_grande_pulado(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "big.txt").write_text("BIGTOKEN" + "X" * (300 * 1024), encoding="utf-8")
    _, payload = search(controller, ws, "T1", ".", "BIGTOKEN")
    data = payload["data"]
    assert all("big.txt" not in m["path"] for m in data["matches"])
    assert data["skipped"]["too_large"] >= 1


# ----------------------------------------------------- read-only / auditoria
def test_workspace_nao_muda_com_varias_buscas(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "a.txt").write_text("alpha\n", encoding="utf-8")
    sub = ws / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("beta\n", encoding="utf-8")
    before = snapshot(ws)
    search(controller, ws, "T1", ".", "alpha")
    search(controller, ws, "T2", "sub", "beta")
    search(controller, ws, "T3", ".", "nao-existe")
    assert before == snapshot(ws)


def test_auditoria_registra_busca_com_sucesso(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "a.txt").write_text("alpha\n", encoding="utf-8")
    search(controller, ws, "T1", ".", "alpha")
    records = [
        json.loads(line)
        for line in (tmp_path / "audit" / "a_a.jsonl")
        .read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    hits = [r for r in records if r.get("tool") == "search_files"]
    assert hits, "busca deve ser auditada"
    assert hits[-1].get("success") is True
    assert hits[-1].get("operation") == "read"


def test_query_ausente_ou_vazia_rejeitada(tmp_path):
    controller, ws = make_controller(tmp_path)
    (ws / "a.txt").write_text("alpha\n", encoding="utf-8")
    run, _ = search(controller, ws, "T1", ".", "")
    assert str(run.status.value).upper() == "FAILED"
    assert "query" in (run.error or "")
    # query ausente (parameters sem 'query')
    plan = Plan(
        id="PLN-T2", objective="busca", status=PlanStatus.READY,
        tasks=(PlannedTask("T2", "sem query", 1, tool="search_files",
                           parameters={"path": "."}),),
    )
    report = controller.run_plan(plan)
    run2 = report.task_run("T2")
    assert str(run2.status.value).upper() == "FAILED"
    assert "query" in (run2.error or "")
