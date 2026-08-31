"""Testes dos workspaces autorizados (store + sandbox multi-workspace).

Offline, diretórios temporários — nada fora do autorizado é acessível.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.filesystem import (
    DeleteNotAllowedError,
    PathOutsideWorkspaceError,
    WriteNotAllowedError,
)
from app.tools.workspaces import (
    MultiWorkspaceSandbox,
    WorkspaceEntry,
    WorkspaceStore,
    WorkspaceStoreError,
)


@pytest.fixture()
def store(tmp_path: Path) -> WorkspaceStore:
    return WorkspaceStore(tmp_path / "workspaces.json")


@pytest.fixture()
def ws_dir(tmp_path: Path) -> Path:
    root = tmp_path / "projetos"
    root.mkdir()
    return root


# --------------------------------------------------------------- validação
def test_add_requires_absolute_existing_directory(store, tmp_path):
    with pytest.raises(ValueError):
        store.add("relativo/ao/nada")
    with pytest.raises(ValueError):
        store.add(str(tmp_path / "inexistente"))
    file_path = tmp_path / "arquivo.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        store.add(str(file_path))


def test_add_rejects_filesystem_root_anchor(store, tmp_path):
    with pytest.raises(ValueError, match="raiz do disco"):
        store.add(str(Path(tmp_path.resolve().anchor)))
    with pytest.raises(ValueError):
        store.add("")


def test_add_rejects_delete_without_write(store, ws_dir):
    with pytest.raises(ValueError, match="exige permitir escrita"):
        store.add(str(ws_dir), writable=False, allow_delete=True)


def test_add_normalizes_and_deduplicates(store, ws_dir):
    entry = store.add(str(ws_dir))
    assert entry.root == ws_dir.resolve()
    sub = ws_dir / "sub"
    sub.mkdir()
    with pytest.raises(ValueError, match="já autorizado"):
        store.add(str(sub / ".."))  # normaliza p/ o mesmo root


def test_store_file_created_only_on_first_authorization(store, ws_dir):
    assert not store.path.exists()  # nada no "startup"
    store.add(str(ws_dir))
    assert store.path.exists()
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert data == [{"root": str(ws_dir.resolve()),
                     "writable": False, "allow_delete": False}]


def test_load_missing_file_returns_empty_without_creating(store):
    assert store.load() == []
    assert not store.path.exists()


def test_load_rejects_corrupt_or_invalid(store, tmp_path):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")
    with pytest.raises(WorkspaceStoreError):
        store.load()
    store.path.write_text('{"root": "/x"}', encoding="utf-8")  # não-lista
    with pytest.raises(WorkspaceStoreError):
        store.load()
    store.path.write_text(
        json.dumps([{"root": "/a", "allow_delete": True, "writable": False}]),
        encoding="utf-8",
    )
    with pytest.raises(WorkspaceStoreError):  # invariante delete⊃write
        store.load()


def test_remove_and_set_flags(store, ws_dir):
    entry = store.add(str(ws_dir))
    updated = store.set_flags(str(ws_dir), writable=True, allow_delete=True)
    assert updated.mode_label == "escrita + exclusão"
    removed = store.remove(str(ws_dir))
    assert removed.root == entry.root
    assert store.load() == []
    with pytest.raises(ValueError):
        store.remove(str(ws_dir))


def test_mode_labels():
    assert WorkspaceEntry(root=Path("/a")).mode_label == "somente leitura"
    assert WorkspaceEntry(root=Path("/a"), writable=True).mode_label == "escrita"
    assert WorkspaceEntry(root=Path("/a"), writable=True,
                          allow_delete=True).mode_label == "escrita + exclusão"


# ------------------------------------------------------- multi-sandbox
def test_multi_resolve_in_authorization_order(tmp_path):
    first, second = tmp_path / "w1", tmp_path / "w2"
    first.mkdir()
    second.mkdir()
    sandbox = MultiWorkspaceSandbox([
        WorkspaceEntry(first), WorkspaceEntry(second, writable=True),
    ])
    assert sandbox.resolve("doc.txt") == (first / "doc.txt").resolve()
    absolute = str(second / "doc.txt")
    assert sandbox.resolve(absolute) == Path(absolute).resolve()


def test_multi_empty_blocks_everything():
    sandbox = MultiWorkspaceSandbox([])
    with pytest.raises(PathOutsideWorkspaceError, match="Nenhum workspace"):
        sandbox.resolve("qualquer.txt")


def test_multi_policy_is_per_root_not_weakest_link(tmp_path):
    """Workspace somente-leitura bloqueia escrita NELE mesmo que outro
    workspace permita escrita (política por raiz)."""
    readonly, writable = tmp_path / "ro", tmp_path / "rw"
    readonly.mkdir()
    writable.mkdir()
    sandbox = MultiWorkspaceSandbox([
        WorkspaceEntry(readonly), WorkspaceEntry(writable, writable=True),
    ])
    ro_file = sandbox.resolve("arquivo.txt")          # cai no primeiro (ro)
    rw_file = sandbox.resolve(str(writable / "arquivo.txt"))
    sandbox.check_operation("read", ro_file)           # leitura livre
    with pytest.raises(WriteNotAllowedError):
        sandbox.check_operation("write", ro_file)      # ro é ro
    sandbox.check_operation("write", rw_file)          # rw permite


def test_multi_delete_needs_per_root_opt_in(tmp_path):
    writable_no_delete, full = tmp_path / "rw", tmp_path / "full"
    writable_no_delete.mkdir()
    full.mkdir()
    sandbox = MultiWorkspaceSandbox([
        WorkspaceEntry(writable_no_delete, writable=True),
        WorkspaceEntry(full, writable=True, allow_delete=True),
    ])
    with pytest.raises(DeleteNotAllowedError):
        sandbox.check_operation(
            "delete", sandbox.resolve(str(writable_no_delete / "x.txt"))
        )
    sandbox.check_operation("delete", sandbox.resolve(str(full / "x.txt")))


def test_multi_escape_and_traversal_still_blocked(tmp_path):
    outside = tmp_path / "fora"
    outside.mkdir()
    inside = tmp_path / "ws"
    inside.mkdir()
    sandbox = MultiWorkspaceSandbox([WorkspaceEntry(inside, writable=True)])
    with pytest.raises(PathOutsideWorkspaceError):
        sandbox.resolve("../escape.txt")
    with pytest.raises(PathOutsideWorkspaceError):
        sandbox.resolve(str(outside / "alvo.txt"))


def test_multi_symlink_escape_blocked(tmp_path):
    inside = tmp_path / "ws"
    inside.mkdir()
    target = tmp_path / "alvo.txt"
    target.write_text("s", encoding="utf-8")
    link = inside / "atalho"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):  # pragma: no cover
        pytest.skip("symlink indisponível")
    sandbox = MultiWorkspaceSandbox([WorkspaceEntry(inside, writable=True)])
    with pytest.raises(PathOutsideWorkspaceError):
        sandbox.resolve("atalho")


def test_multi_entry_for_and_summaries(tmp_path):
    ro, full = tmp_path / "ro", tmp_path / "full"
    ro.mkdir()
    full.mkdir()
    sandbox = MultiWorkspaceSandbox([
        WorkspaceEntry(ro), WorkspaceEntry(full, writable=True, allow_delete=True),
    ])
    assert sandbox.entry_for((ro / "x").resolve()).root == ro.resolve()
    assert sandbox.entry_for((tmp_path / "nada").resolve()) is None
    assert sandbox.writable is True and sandbox.allow_delete is True
    assert MultiWorkspaceSandbox([WorkspaceEntry(ro)]).writable is False


def test_multi_assert_summary_and_unknown_operation(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    empty = MultiWorkspaceSandbox([])
    with pytest.raises(WriteNotAllowedError):
        empty.assert_operation_allowed("write")
    sandbox = MultiWorkspaceSandbox([WorkspaceEntry(root)])
    with pytest.raises(WriteNotAllowedError):
        sandbox.assert_operation_allowed("write")
    sandbox.assert_operation_allowed("read")
    with pytest.raises(Exception):
        sandbox.assert_operation_allowed("execute")
