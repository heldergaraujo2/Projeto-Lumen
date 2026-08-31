"""Testes da persistência de auditoria em JSONL (0.5.x)."""
from __future__ import annotations

import json

import pytest

from app.tools.audit_log import JsonlAuditSink, read_audit_tail


def test_sink_appends_jsonl_lines(tmp_path):
    path = tmp_path / "audit" / "audit.jsonl"  # diretório pai não existe
    sink = JsonlAuditSink(path)
    sink({"tool": "read_file", "success": True, "error": None})
    sink({"tool": "write_file", "success": False, "error": "bloqueado"})
    assert path.exists()  # pai criado sob demanda
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert first["tool"] == "read_file" and first["success"] is True
    assert second["error"] == "bloqueado"


def test_read_tail_limit_and_missing_file(tmp_path):
    path = tmp_path / "audit.jsonl"
    sink = JsonlAuditSink(path)
    for index in range(5):
        sink({"n": index})
    assert read_audit_tail(path, limit=3) == [{"n": 2}, {"n": 3}, {"n": 4}]
    assert read_audit_tail(path, limit=10) == [{"n": i} for i in range(5)]
    assert read_audit_tail(tmp_path / "inexistente.jsonl") == []
    with pytest.raises(ValueError):
        read_audit_tail(path, limit=0)


def test_read_tail_skips_corrupt_lines(tmp_path):
    path = tmp_path / "audit.jsonl"
    path.write_text(
        '{"ok": 1}\n'
        'linha corrompida\n'
        '{"ok": 2}\n',
        encoding="utf-8",
    )
    records = read_audit_tail(path)
    assert records == [{"ok": 1}, {"ok": 2}]


def test_end_to_end_registry_writes_audit_without_file_content(tmp_path):
    """Cadeia real → JSONL: metadados completos, ZERO conteúdo de arquivo."""
    from app.security.permissions import PermissionManager
    from app.tools.filesystem import FilesystemAudit, WorkspaceSandbox
    from app.tools.filesystem import build_filesystem_registry

    root = tmp_path / "ws"
    root.mkdir()
    audit_file = tmp_path / "audit" / "audit.jsonl"
    audit = FilesystemAudit(sink=JsonlAuditSink(audit_file))
    permissions = PermissionManager()
    permissions.grant("READ")
    permissions.grant("WRITE")
    registry = build_filesystem_registry(
        permissions, WorkspaceSandbox([root], writable=True), audit
    )
    payload = registry.execute(
        "write_file", path="secreto.txt", content="CONTEUDO-SENSIVEL-XYZ"
    )
    assert json.loads(payload)["ok"] is True
    registry.execute("read_file", path="../fora.txt")  # bloqueio auditado

    records = read_audit_tail(audit_file)
    assert [r["tool"] for r in records] == ["write_file", "read_file"]
    assert records[1]["success"] is False
    assert records[1]["resolved_path"] is None
    # campos exigidos presentes no registro de sucesso
    assert records[0]["requested_path"] == "secreto.txt"
    assert records[0]["resolved_path"].startswith(str(root.resolve()))
    assert records[0]["timestamp"]
    # conteúdo do arquivo JAMAIS na auditoria
    assert "CONTEUDO-SENSIVEL-XYZ" not in audit_file.read_text(encoding="utf-8")
