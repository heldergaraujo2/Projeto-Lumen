"""Testes do sandbox de filesystem (política de workspace) e da auditoria.

Tudo offline, em diretórios temporários — nenhum acesso fora do
workspace autorizado.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.filesystem import (
    DeleteNotAllowedError,
    FilesystemAudit,
    FilesystemError,
    InvalidPathError,
    PathOutsideWorkspaceError,
    WorkspaceSandbox,
    WriteNotAllowedError,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "sub").mkdir()
    (root / "sub" / "dado.txt").write_text("conteudo", encoding="utf-8")
    return root


# ------------------------------------------------------------ construção
def test_sandbox_rejects_relative_root():
    with pytest.raises(ValueError):
        WorkspaceSandbox(["relativa"])


def test_sandbox_requires_at_least_one_root():
    with pytest.raises(ValueError):
        WorkspaceSandbox([])


def test_sandbox_defaults_to_read_only(workspace):
    sandbox = WorkspaceSandbox([workspace])
    assert sandbox.roots == (workspace.resolve(),)
    assert sandbox.writable is False
    assert sandbox.allow_delete is False


# ------------------------------------------------------------- resolução
def test_resolve_relative_path_inside_workspace(workspace):
    sandbox = WorkspaceSandbox([workspace])
    resolved = sandbox.resolve("sub/dado.txt")
    assert resolved == (workspace / "sub" / "dado.txt").resolve()


def test_resolve_dot_lists_root(workspace):
    sandbox = WorkspaceSandbox([workspace])
    assert sandbox.resolve(".") == workspace.resolve()


def test_resolve_absolute_path_inside_workspace_is_allowed(workspace):
    sandbox = WorkspaceSandbox([workspace])
    absolute = str(workspace / "sub" / "dado.txt")
    assert sandbox.resolve(absolute) == Path(absolute).resolve()


def test_resolve_absolute_path_outside_workspace_is_blocked(workspace, tmp_path):
    sandbox = WorkspaceSandbox([workspace])
    outside = tmp_path / "fora.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(PathOutsideWorkspaceError):
        sandbox.resolve(str(outside))
    with pytest.raises(PathOutsideWorkspaceError):
        sandbox.resolve("/etc")


def test_resolve_blocks_dotdot_escape_attempt(workspace):
    sandbox = WorkspaceSandbox([workspace])
    with pytest.raises(PathOutsideWorkspaceError):
        sandbox.resolve("../fora.txt")
    with pytest.raises(PathOutsideWorkspaceError):
        sandbox.resolve("sub/../../escape.txt")


def test_resolve_blocks_dotdot_even_staying_inside(workspace):
    """Traversal é bloqueado SEMPRE — até se o caminho final ficaria dentro."""
    sandbox = WorkspaceSandbox([workspace])
    with pytest.raises(PathOutsideWorkspaceError):
        sandbox.resolve("sub/../dado.txt")


def test_resolve_rejects_invalid_paths(workspace):
    sandbox = WorkspaceSandbox([workspace])
    for bad in ("", "   ", None, 42, b"bytes", "path\x00nul", "ctl\x1bchar"):
        with pytest.raises(InvalidPathError):
            sandbox.resolve(bad)


def test_resolve_blocks_symlink_escape(workspace, tmp_path):
    target = tmp_path / "alvo-externo.txt"
    target.write_text("secreto", encoding="utf-8")
    link = workspace / "atalho"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):  # pragma: no cover - sem symlink
        pytest.skip("symlink indisponível neste ambiente")
    sandbox = WorkspaceSandbox([workspace])
    with pytest.raises(PathOutsideWorkspaceError):
        sandbox.resolve("atalho")


def test_multi_workspace_relative_resolves_in_root_order(tmp_path):
    first = tmp_path / "ws1"
    second = tmp_path / "ws2"
    first.mkdir()
    second.mkdir()
    sandbox = WorkspaceSandbox([first, second])
    assert sandbox.resolve("arquivo.txt") == (first / "arquivo.txt").resolve()
    absolute = str(second / "arquivo.txt")
    assert sandbox.resolve(absolute) == Path(absolute).resolve()


# --------------------------------------------------------------- política
def test_policy_read_only_blocks_write_operations(workspace):
    sandbox = WorkspaceSandbox([workspace])  # writable=False
    sandbox.assert_operation_allowed("read")  # leitura sempre ok
    with pytest.raises(WriteNotAllowedError):
        sandbox.assert_operation_allowed("write")
    with pytest.raises(WriteNotAllowedError):
        sandbox.assert_operation_allowed("delete")  # delete exige writable também


def test_policy_writable_blocks_delete_without_flag(workspace):
    sandbox = WorkspaceSandbox([workspace], writable=True)
    sandbox.assert_operation_allowed("write")
    with pytest.raises(DeleteNotAllowedError):
        sandbox.assert_operation_allowed("delete")


def test_policy_delete_requires_double_opt_in(workspace):
    sandbox = WorkspaceSandbox([workspace], writable=True, allow_delete=True)
    sandbox.assert_operation_allowed("delete")


def test_policy_rejects_unknown_operation(workspace):
    sandbox = WorkspaceSandbox([workspace], writable=True)
    with pytest.raises(FilesystemError):
        sandbox.assert_operation_allowed("execute")  # execução NÃO existe


# --------------------------------------------------------------- auditoria
def test_audit_record_carries_context_and_metadata():
    audit = FilesystemAudit()
    with audit.scoped(task_id="T1", plan_id="PLN-0001"):
        audit.record(
            tool="write_file", operation="write",
            requested_path="a.txt", resolved_path="/ws/a.txt",
            bytes_written=10,
        )
    record = audit.records[0]
    assert record.tool == "write_file"
    assert record.operation == "write"
    assert record.requested_path == "a.txt"
    assert record.resolved_path == "/ws/a.txt"
    assert record.success is True
    assert record.error is None
    assert record.task_id == "T1"
    assert record.plan_id == "PLN-0001"
    assert record.detail == {"bytes_written": 10}
    assert record.timestamp  # ISO preenchido
    # contexto restaurado após o escopo
    audit.record(tool="read_file", operation="read", requested_path="b.txt")
    assert audit.records[1].task_id is None
    assert audit.records[1].plan_id is None


def test_audit_sink_receives_dicts_and_failures_do_not_break():
    received = []

    def sink(payload: dict) -> None:
        received.append(payload)

    audit = FilesystemAudit(sink=sink)
    audit.record(tool="read_file", operation="read", requested_path="x",
                 success=False, error="bloqueado")
    assert len(received) == 1
    assert received[0]["error"] == "bloqueado"

    def broken_sink(payload: dict) -> None:
        raise RuntimeError("sink quebrado")

    audit2 = FilesystemAudit(sink=broken_sink)
    audit2.record(tool="read_file", operation="read", requested_path="y")
    assert len(audit2.records) == 1  # registro mantido em memória


def test_audit_records_are_immutable_snapshot():
    audit = FilesystemAudit()
    audit.record(tool="read_file", operation="read", requested_path="x")
    snapshot = audit.records
    audit.record(tool="read_file", operation="read", requested_path="y")
    assert len(snapshot) == 1 and len(audit.records) == 2
    assert audit.to_dicts()[0]["requested_path"] == "x"
