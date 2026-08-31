"""Testes das ferramentas de filesystem (contratos, erros, permissões).

Offline + diretórios temporários; permissões concedidas explicitamente
nos cenários que precisam delas (padrão continua sendo apenas CHAT).
"""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from app.security.permissions import (
    PermissionDeniedError,
    PermissionLevel,
    PermissionManager,
)
from app.tools.base import ToolRegistry
from app.tools.filesystem import (
    FILESYSTEM_TOOLS,
    FilesystemAudit,
    WorkspaceSandbox,
    build_filesystem_registry,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "docs" / "leia.txt").write_text("conteúdo do arquivo", encoding="utf-8")
    return root


def make_permissions(*levels: str) -> PermissionManager:
    permissions = PermissionManager()
    for level in levels:
        permissions.grant(level)
    return permissions


def make_registry(root: Path, *, levels: tuple[str, ...] = ("READ", "WRITE"),
                  writable: bool = True, allow_delete: bool = True,
                  audit: FilesystemAudit | None = None) -> ToolRegistry:
    sandbox = WorkspaceSandbox([root], writable=writable, allow_delete=allow_delete)
    return build_filesystem_registry(make_permissions(*levels), sandbox, audit)


def run_tool(registry: ToolRegistry, name: str, **kwargs):
    """Executa via registry (JSON textual) e devolve o dict estruturado."""
    return json.loads(registry.execute(name, **kwargs))


# ------------------------------------------------------------- registro
def test_factory_registers_the_seven_filesystem_tools(workspace):
    registry = make_registry(workspace)
    listing = registry.list_tools()
    names = {item["name"] for item in listing}
    assert names == set(FILESYSTEM_TOOLS) == {
        "list_directory", "read_file", "write_file",
        "create_file", "delete_file", "file_exists",
        "search_files", "edit_file",
    }
    permissions = {item["name"]: item["required_permission"] for item in listing}
    assert permissions["read_file"] == "READ"
    assert permissions["list_directory"] == "READ"
    assert permissions["file_exists"] == "READ"
    assert permissions["search_files"] == "READ"
    assert permissions["write_file"] == "WRITE"
    assert permissions["create_file"] == "WRITE"
    assert permissions["delete_file"] == "WRITE"
    assert permissions["edit_file"] == "WRITE"


def test_fresh_registry_stays_empty_until_explicit_build():
    # Nada é registrado globalmente no import/startup.
    assert ToolRegistry().list_tools() == []


# ------------------------------------------------------- list_directory
def test_list_directory_returns_sorted_entries(workspace):
    (workspace / "alpha.txt").write_text("a", encoding="utf-8")
    result = run_tool(make_registry(workspace), "list_directory", path="docs")
    assert result["ok"] is True
    names = [entry["name"] for entry in result["data"]["entries"]]
    assert names == ["leia.txt"]
    assert result["data"]["count"] == 1
    result_root = run_tool(make_registry(workspace), "list_directory", path=".")
    assert [entry["name"] for entry in result_root["data"]["entries"]] == [
        "alpha.txt", "docs",
    ]
    types = {e["name"]: e["type"] for e in result_root["data"]["entries"]}
    assert types == {"alpha.txt": "file", "docs": "dir"}


def test_list_directory_missing_and_not_a_directory(workspace):
    registry = make_registry(workspace)
    missing = run_tool(registry, "list_directory", path="inexistente")
    assert missing["ok"] is False and "não existe" in missing["error"]
    not_dir = run_tool(registry, "list_directory", path="docs/leia.txt")
    assert not_dir["ok"] is False and "não é um diretório" in not_dir["error"]


# ------------------------------------------------------------- read_file
def test_read_file_returns_content_and_size(workspace):
    result = run_tool(make_registry(workspace), "read_file", path="docs/leia.txt")
    assert result["ok"] is True
    assert result["data"]["content"] == "conteúdo do arquivo"
    assert result["data"]["size_bytes"] > 0
    assert result["data"]["resolved_path"].startswith(str(workspace.resolve()))


def test_read_file_missing_directory_and_binary(workspace):
    registry = make_registry(workspace)
    missing = run_tool(registry, "read_file", path="sumiu.txt")
    assert missing["ok"] is False and "não existe" in missing["error"]
    is_dir = run_tool(registry, "read_file", path="docs")
    assert is_dir["ok"] is False and "diretório" in is_dir["error"]
    (workspace / "binario.bin").write_bytes(b"\x00\xff\xfe\x81")
    binary = run_tool(registry, "read_file", path="binario.bin")
    assert binary["ok"] is False and "UTF-8" in binary["error"]


def test_read_file_size_limit(workspace):
    (workspace / "grande.txt").write_text("x" * 100, encoding="utf-8")
    registry = make_registry(workspace)
    blocked = run_tool(registry, "read_file", path="grande.txt", max_bytes=10)
    assert blocked["ok"] is False and "limite" in blocked["error"]
    allowed = run_tool(registry, "read_file", path="grande.txt", max_bytes=200)
    assert allowed["ok"] is True
    invalid = run_tool(registry, "read_file", path="grande.txt", max_bytes=-1)
    assert invalid["ok"] is False


# ------------------------------------------------------------ write/create
def test_write_file_creates_then_overwrites(workspace):
    registry = make_registry(workspace)
    first = run_tool(registry, "write_file", path="notas.txt", content="v1")
    assert first["ok"] is True and first["data"]["overwritten"] is False
    second = run_tool(registry, "write_file", path="notas.txt", content="versão 2")
    assert second["ok"] is True and second["data"]["overwritten"] is True
    assert (workspace / "notas.txt").read_text(encoding="utf-8") == "versão 2"
    assert second["data"]["bytes_written"] == len("versão 2".encode("utf-8"))


def test_write_file_requires_content_and_existing_parent(workspace):
    registry = make_registry(workspace)
    no_content = run_tool(registry, "write_file", path="a.txt")
    assert no_content["ok"] is False and "'content'" in no_content["error"]
    wrong_type = run_tool(registry, "write_file", path="a.txt", content=7)
    assert wrong_type["ok"] is False
    no_parent = run_tool(registry, "write_file", path="novo_dir/a.txt", content="x")
    assert no_parent["ok"] is False and "pai não existe" in no_parent["error"]


def test_create_file_new_and_refuses_overwrite(workspace):
    registry = make_registry(workspace)
    created = run_tool(registry, "create_file", path="novo.txt", content="dados")
    assert created["ok"] is True and created["data"]["created"] is True
    again = run_tool(registry, "create_file", path="novo.txt", content="outros")
    assert again["ok"] is False and "não sobrescreve" in again["error"]
    assert (workspace / "novo.txt").read_text(encoding="utf-8") == "dados"


def test_write_to_os_read_only_file_fails_controlled(workspace):
    target = workspace / "somente-leitura.txt"
    target.write_text("original", encoding="utf-8")
    original_mode = target.stat().st_mode
    target.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    try:
        result = run_tool(make_registry(workspace), "write_file",
                          path="somente-leitura.txt", content="novo")
        assert result["ok"] is False
        assert "Erro de filesystem" in result["error"]
        assert target.read_text(encoding="utf-8") == "original"
    finally:
        target.chmod(original_mode)


# ------------------------------------------------------------- delete/exists
def test_delete_file_removes_only_files(workspace):
    registry = make_registry(workspace)
    deleted = run_tool(registry, "delete_file", path="docs/leia.txt")
    assert deleted["ok"] is True and deleted["data"]["deleted"] is True
    assert not (workspace / "docs" / "leia.txt").exists()
    missing = run_tool(registry, "delete_file", path="docs/leia.txt")
    assert missing["ok"] is False and "não existe" in missing["error"]
    is_dir = run_tool(registry, "delete_file", path="docs")
    assert is_dir["ok"] is False and "apenas arquivos" in is_dir["error"]
    assert (workspace / "docs").is_dir()  # diretório intocado


def test_delete_blocked_when_policy_disallows(workspace):
    registry = make_registry(workspace, allow_delete=False)
    result = run_tool(registry, "delete_file", path="docs/leia.txt")
    assert result["ok"] is False and "allow_delete" in result["error"]
    assert (workspace / "docs" / "leia.txt").exists()  # bloqueado, não executado


def test_file_exists_true_false_and_directory(workspace):
    registry = make_registry(workspace)
    yes = run_tool(registry, "file_exists", path="docs/leia.txt")
    assert yes["ok"] is True and yes["data"]["exists"] is True
    assert yes["data"]["is_dir"] is False
    folder = run_tool(registry, "file_exists", path="docs")
    assert folder["data"]["exists"] is True and folder["data"]["is_dir"] is True
    no = run_tool(registry, "file_exists", path="nunca.txt")
    assert no["data"]["exists"] is False and no["data"]["is_dir"] is None


# -------------------------------------------------------- bloqueios de segurança
def test_escape_attempts_are_blocked_not_executed(workspace, tmp_path):
    registry = make_registry(workspace)
    for bad_path in ("../fora.txt", "docs/../../escape.txt", str(tmp_path / "abs.txt"), "/etc"):
        result = run_tool(registry, "write_file", path=bad_path, content="vazamento")
        assert result["ok"] is False, bad_path
    assert not (tmp_path / "fora.txt").exists()
    assert not (tmp_path / "abs.txt").exists()
    assert not (tmp_path / "escape.txt").exists()


def test_write_blocked_in_read_only_policy(workspace):
    registry = make_registry(workspace, writable=False)
    result = run_tool(registry, "write_file", path="negado.txt", content="x")
    assert result["ok"] is False and "somente leitura" in result["error"]
    assert not (workspace / "negado.txt").exists()
    # leitura continua funcionando
    ok_read = run_tool(registry, "read_file", path="docs/leia.txt")
    assert ok_read["ok"] is True


def test_permission_gate_blocks_tools_before_they_run(workspace):
    # Sem READ: ferramentas de leitura bloqueadas pelo porteiro.
    registry = make_registry(workspace, levels=())
    with pytest.raises(PermissionDeniedError) as exc:
        registry.execute("read_file", path="docs/leia.txt")
    assert PermissionLevel.READ.name in str(exc.value)
    # Sem WRITE (com READ): leitura ok, escrita bloqueada.
    registry_ro = make_registry(workspace, levels=("READ",))
    assert run_tool(registry_ro, "file_exists", path="docs")["ok"] is True
    with pytest.raises(PermissionDeniedError) as exc_write:
        registry_ro.execute("write_file", path="x.txt", content="y")
    assert PermissionLevel.WRITE.name in str(exc_write.value)
    assert not (workspace / "x.txt").exists()


def test_permission_grant_unlocks_progressively(workspace):
    permissions = make_permissions("READ")
    sandbox = WorkspaceSandbox([workspace], writable=True)
    registry = build_filesystem_registry(permissions, sandbox)
    with pytest.raises(PermissionDeniedError):
        registry.execute("write_file", path="liberado.txt", content="agora sim")
    permissions.grant(PermissionLevel.WRITE)  # concessão explícita
    result = run_tool(registry, "write_file", path="liberado.txt", content="agora sim")
    assert result["ok"] is True
    permissions.revoke(PermissionLevel.WRITE)  # revogação imediata
    with pytest.raises(PermissionDeniedError):
        registry.execute("write_file", path="outro.txt", content="x")


# ------------------------------------------------------------- auditoria
def test_audit_trails_success_and_blocks_with_metadata(workspace):
    audit = FilesystemAudit()
    registry = make_registry(workspace, audit=audit)
    run_tool(registry, "write_file", path="rastreavel.txt", content="secreto-interno")
    run_tool(registry, "read_file", path="../fora.txt")
    records = audit.to_dicts()
    assert [r["tool"] for r in records] == ["write_file", "read_file"]
    success, blocked = records
    assert success["success"] is True
    assert success["requested_path"] == "rastreavel.txt"
    assert success["resolved_path"] == str((workspace / "rastreavel.txt").resolve())
    assert success["operation"] == "write"
    assert success["timestamp"]
    assert success["detail"] == {"bytes_written": 15, "overwritten": False}
    assert blocked["success"] is False and blocked["resolved_path"] is None
    assert "traversal" in blocked["error"]
    # Conteúdo do arquivo NUNCA é registrado na auditoria.
    assert "secreto-interno" not in json.dumps(records, ensure_ascii=False)
