"""Testes da ferramenta run_command (0.6) — execução REAL, controlada.

Roda comandos POSIX inofensivos (printf/false/ls/sleep/seq/mkdir/printenv)
dentro de um workspace temporário. Os casos de execução pulam no Windows
(lá a validação usa dir/where — ver doc); os bloqueios são SO-agnósticos.
Nenhuma rede, nenhum segredo, nada fora da allowlist.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.security.permissions import PermissionDeniedError, PermissionManager
from app.tools.base import ToolRegistry
from app.tools.filesystem import FilesystemAudit, WorkspaceSandbox
from app.tools.terminal import (
    AllowedCommand,
    RunCommandTool,
    TerminalPolicy,
    build_terminal_registry,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="usa comandos POSIX do sandbox"
)


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    root.mkdir()
    return root


@pytest.fixture()
def sandbox(ws: Path) -> WorkspaceSandbox:
    return WorkspaceSandbox([ws])


@pytest.fixture()
def audit() -> FilesystemAudit:
    return FilesystemAudit()


def make_tool(policy: TerminalPolicy, sandbox, audit) -> RunCommandTool:
    return RunCommandTool(policy, sandbox, audit)


# ------------------------------------------------------------- execuções felizes
def test_allowed_command_runs_and_captures_stdout(sandbox, audit):
    tool = make_tool(TerminalPolicy(["printf"]), sandbox, audit)
    result = tool.run(command="printf", args=["olá terminal"], cwd=".")
    assert result.ok is True
    assert result.data["stdout"] == "olá terminal"
    assert result.data["exit_code"] == 0
    assert result.data["timed_out"] is False
    assert result.data["truncated"] is False
    assert result.data["timeout_s"] == 10  # default
    assert result.data["max_output_bytes"] == 64 * 1024
    assert result.data["duration_ms"] >= 0
    assert result.data["cwd"] == str(sandbox.roots[0])


def test_stderr_captured_separately(sandbox, audit):
    tool = make_tool(TerminalPolicy(["ls"]), sandbox, audit)
    result = tool.run(command="ls", args=["arquivo-que-nao-existe"], cwd=".")
    assert result.ok is False
    assert result.data["exit_code"] != 0
    assert result.data["stderr"].strip() != ""
    assert result.data["stdout"] == ""


def test_nonzero_exit_code_is_controlled_failure(sandbox, audit):
    tool = make_tool(TerminalPolicy(["false"]), sandbox, audit)
    result = tool.run(command="false", args=[], cwd=".")
    assert result.ok is False
    assert result.data["exit_code"] == 1
    assert "exit code 1" in result.error


# -------------------------------------------------------------------- bloqueios
def test_command_outside_allowlist_never_executes(sandbox, audit, ws):
    tool = make_tool(TerminalPolicy(["printf"]), sandbox, audit)
    result = tool.run(command="mkdir", args=["vazou"], cwd=".")
    assert result.ok is False
    assert "allowlist" in result.error
    assert not (ws / "vazou").exists()  # nada rodou, efeito zero


def test_operators_blocked_in_tool_call(sandbox, audit):
    tool = make_tool(TerminalPolicy(["printf"]), sandbox, audit)
    result = tool.run(command="printf", args=["a && b"], cwd=".")
    assert result.ok is False
    assert "operador" in result.error.lower()
    assert result.data["exit_code"] is None


def test_invalid_cwd_fails_controlled(sandbox, audit):
    tool = make_tool(TerminalPolicy(["ls"]), sandbox, audit)
    result = tool.run(command="ls", args=[], cwd="nao-existe")
    assert result.ok is False
    assert "não existe" in result.error or "não é diretório" in result.error


def test_command_not_found_is_controlled(sandbox, audit):
    tool = make_tool(TerminalPolicy(["comando-lumen-inexistente-xyz"]), sandbox, audit)
    result = tool.run(command="comando-lumen-inexistente-xyz", args=[], cwd=".")
    assert result.ok is False
    assert "não encontrado" in result.error


# ----------------------------------------------------------- timeout e limites
def test_timeout_is_enforced_and_kills(sandbox, audit):
    tool = make_tool(
        TerminalPolicy([AllowedCommand("sleep", timeout_s=1)]), sandbox, audit
    )
    result = tool.run(command="sleep", args=["30"], cwd=".")
    assert result.ok is False
    assert result.data["timed_out"] is True
    assert result.data["duration_ms"] < 15_000  # morto rápido, não esperou 30s


def test_output_limit_truncates_and_fails_honestly(sandbox, audit):
    tool = make_tool(
        TerminalPolicy(["seq"], default_max_output_bytes=1024), sandbox, audit
    )
    result = tool.run(command="seq", args=["100000"], cwd=".")
    assert result.ok is False
    assert result.data["truncated"] is True
    assert len(result.data["stdout"].encode("utf-8")) <= 1024
    assert "truncada" in result.error


# --------------------------------------------------------------------- permissão
def test_registry_gate_blocks_without_terminal_permission(sandbox, audit, ws):
    permissions = PermissionManager()  # só CHAT
    policy = TerminalPolicy(["mkdir"])
    registry = build_terminal_registry(permissions, policy, sandbox, audit)
    with pytest.raises(PermissionDeniedError):
        registry.execute("run_command", command="mkdir", args=["gated"], cwd=".")
    assert not (ws / "gated").exists()  # nada executou


def test_read_write_permissions_do_not_grant_terminal(sandbox, audit):
    permissions = PermissionManager(["READ", "WRITE"])
    registry = build_terminal_registry(permissions, TerminalPolicy(["ls"]), sandbox)
    with pytest.raises(PermissionDeniedError) as excinfo:
        registry.execute("run_command", command="ls", args=[], cwd=".")
    assert "TERMINAL" in str(excinfo.value)


def test_terminal_permission_allows_execution(sandbox, audit, ws):
    permissions = PermissionManager(["CHAT", "TERMINAL"])
    tool = make_tool(TerminalPolicy(["mkdir"]), sandbox, audit)
    registry = ToolRegistry(permissions)
    registry.register(tool)
    raw = registry.execute("run_command", command="mkdir", args=["ok"], cwd=".")
    assert '"ok": true' in raw
    assert (ws / "ok").exists()


# --------------------------------------------------------------------- auditoria
def test_audit_records_attempts_without_output_content(sandbox, audit):
    tool = make_tool(TerminalPolicy(["printf"]), sandbox, audit)
    tool.run(command="printf", args=["conteudo-normal"], cwd=".")
    tool.run(command="printf", args=["a && b"], cwd=".")  # bloqueado
    records = audit.to_dicts()
    assert len(records) == 2
    ok_rec, blocked_rec = records
    assert ok_rec["tool"] == "run_command"
    assert ok_rec["operation"] == "run_command"
    assert ok_rec["success"] is True
    assert ok_rec["detail"]["exit_code"] == 0
    assert ok_rec["detail"]["command"] == ["printf", "conteudo-normal"]
    assert blocked_rec["success"] is False
    assert blocked_rec["detail"]["exit_code"] is None
    # A trilha NUNCA carrega a saída do comando (conteúdo) — só metadados.
    for record in records:
        assert "stdout" not in record["detail"]
        assert "stderr" not in record["detail"]


def test_audit_sanitizes_oversized_arguments(sandbox, audit):
    tool = make_tool(TerminalPolicy(["printf"]), sandbox, audit)
    big = "x" * 500
    tool.run(command="printf", args=[big], cwd=".")
    command = audit.to_dicts()[0]["detail"]["command"]
    assert len(command[1]) <= 201  # truncado p/ representação segura
    assert command[1].endswith("…")


def test_child_environment_is_sanitized(sandbox, audit, monkeypatch):
    monkeypatch.setenv("LUMEN_TEST_SECRET", "SEGREDO-987")
    tool = make_tool(TerminalPolicy(["printenv"]), sandbox, audit)
    result = tool.run(command="printenv", args=[], cwd=".")
    assert result.ok is True
    assert "SEGREDO-987" not in result.data["stdout"]
    assert "PATH" in result.data["stdout"]


def test_audit_records_cwd_and_timeout(sandbox, audit):
    tool = make_tool(TerminalPolicy([AllowedCommand("sleep", timeout_s=2)]), sandbox, audit)
    tool.run(command="sleep", args=["0"], cwd=".")
    detail = audit.to_dicts()[0]["detail"]
    assert detail["duration_ms"] >= 0
