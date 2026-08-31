"""11C — EditFileTool: edição cirúrgica (ocorrência única) no workspace.

Testes mínimos da Parte 4/5 — mesmo caminho padrão dos testes de
filesystem (``make_registry``/``run_tool`` via ``ToolRegistry``; sem
harness novo). Falha de validação JAMAIS altera o arquivo: cada caso
negativo confere o conteúdo antes/depois.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.security.permissions import PermissionManager
from app.tools.filesystem import (
    FILESYSTEM_TOOLS,
    FilesystemAudit,
    WorkspaceSandbox,
    build_filesystem_registry,
)
from app.tools.base import ToolRegistry


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


def make_registry(root: Path, *, levels: tuple[str, ...] = ("READ", "WRITE"),
                  writable: bool = True) -> ToolRegistry:
    permissions = PermissionManager()
    for level in levels:
        permissions.grant(level)
    sandbox = WorkspaceSandbox([root], writable=writable)
    return build_filesystem_registry(permissions, sandbox, FilesystemAudit())


def run_tool(registry: ToolRegistry, name: str, **kwargs):
    """Executa via registry (JSON textual) e devolve o dict estruturado."""
    return json.loads(registry.execute(name, **kwargs))


def edit(registry, path, old, new):
    return run_tool(registry, "edit_file", path=path,
                    expected_old_text=old, new_text=new)


# ------------------------------------------------------------------ sucesso
def test_edit_file_substitui_ocorrencia_unica(workspace):
    target = workspace / "notas.md"
    target.write_text("titulo\nversao alpha\nfim\n", encoding="utf-8")
    registry = make_registry(workspace)
    result = edit(registry, "notas.md", "versao alpha", "versao beta")
    assert result["ok"] is True
    data = result["data"]
    assert data["operation"] == "edit_file"
    assert data["match_count"] == 1
    assert data["written"] is True
    assert data["replaced_bytes"] == len("versao alpha".encode())
    assert target.read_text(encoding="utf-8") == "titulo\nversao beta\nfim\n"


# ------------------------------------------------------------------ falhas
def test_edit_file_no_match_nao_altera_arquivo(workspace):
    target = workspace / "a.txt"
    target.write_text("conteudo original\n", encoding="utf-8")
    registry = make_registry(workspace)
    result = edit(registry, "a.txt", "trecho inexistente", "novo")
    assert result["ok"] is False
    assert "NO_MATCH" in result["error"]
    assert target.read_text(encoding="utf-8") == "conteudo original\n"


def test_edit_file_multiple_matches_nao_altera_arquivo(workspace):
    target = workspace / "a.txt"
    target.write_text("repete repete\n", encoding="utf-8")
    registry = make_registry(workspace)
    result = edit(registry, "a.txt", "repete", "unico")
    assert result["ok"] is False
    assert "MULTIPLE_MATCHES" in result["error"]
    assert "2 vezes" in result["error"]
    assert target.read_text(encoding="utf-8") == "repete repete\n"


def test_edit_file_ocorrencias_sobrepostas_contam_como_multiplas(workspace):
    # "aa" ocorre 2x em "aaa" (posicoes 0 e 1, sobrepostas) — deve falhar.
    target = workspace / "ov.txt"
    target.write_text("aaa\n", encoding="utf-8")
    registry = make_registry(workspace)
    result = edit(registry, "ov.txt", "aa", "b")
    assert result["ok"] is False
    assert "MULTIPLE_MATCHES" in result["error"]
    assert target.read_text(encoding="utf-8") == "aaa\n"


@pytest.mark.parametrize("old,new", [
    ("", "novo"),          # expected_old_text vazio
    ("alpha", ""),         # new_text vazia
])
def test_edit_file_invalid_input_nao_altera_arquivo(workspace, old, new):
    target = workspace / "a.txt"
    target.write_text("alpha\n", encoding="utf-8")
    registry = make_registry(workspace)
    result = edit(registry, "a.txt", old, new)
    assert result["ok"] is False
    assert "expected_old_text" in result["error"] or "new_text" in result["error"]
    assert target.read_text(encoding="utf-8") == "alpha\n"


def test_edit_file_esta_no_contrato_de_tools():
    # Consistencia com a tuple canonica (registro coberto no teste factory).
    assert "edit_file" in FILESYSTEM_TOOLS
