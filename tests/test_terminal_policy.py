"""Testes da política de terminal (0.6) — validação SEM executar nada.

Cobrem allowlist/denylist, variações/aliases, operadores, argumentos
perigosos, caminhos (cwd e argumentos), timeouts e entradas malformadas.
Tudo offline; nenhum subprocesso é criado aqui.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.filesystem import WorkspaceSandbox
from app.tools.terminal import (
    AllowedCommand,
    CommandNotAllowlistedError,
    DangerousArgumentError,
    InterpreterForbiddenError,
    InvalidCommandError,
    OperatorForbiddenError,
    TerminalPolicy,
    WorkspacePathBlockedError,
    normalize_command,
)


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "leia.txt").write_text("conteúdo", encoding="utf-8")
    return root


@pytest.fixture()
def sandbox(ws: Path) -> WorkspaceSandbox:
    return WorkspaceSandbox([ws])


def policy(*names: str, **kwargs) -> TerminalPolicy:
    return TerminalPolicy(list(names), **kwargs)


# ------------------------------------------------------------ allowlist/denylist
def test_empty_allowlist_blocks_everything(sandbox):
    with pytest.raises(CommandNotAllowlistedError):
        TerminalPolicy().validate("ls", [], None, sandbox)


def test_allowlisted_command_validates(sandbox, ws):
    result = TerminalPolicy(["git"]).validate("git", ["status"], None, sandbox)
    assert result.argv == ("git", "status")
    assert result.cwd == ws.resolve()
    assert result.requires_approval is True  # default: TODO comando pede aprovação


@pytest.mark.parametrize("forbidden", [
    "sh", "bash", "zsh", "powershell", "pwsh", "cmd",
    "python", "python3", "pip", "node", "npm",
    "sudo", "su", "runas",
    "rm", "del", "shutdown", "chmod", "format",
    "curl", "wget", "ssh", "nc",
    "make", "cmake", "dotnet", "docker",
    "env", "xargs", "nohup", "watch", "gdb",
    "net", "sc", "reg", "schtasks", "taskkill",
    "dd", "mkfs", "mount", "icacls", "vssadmin",
])
def test_forbidden_commands_can_never_be_allowlisted(forbidden):
    """Denylist permanente: registro rejeita, execução bloqueia."""
    with pytest.raises(InterpreterForbiddenError):
        TerminalPolicy([forbidden])
    pol = TerminalPolicy(["git"])
    with pytest.raises(InterpreterForbiddenError):
        pol.allow(forbidden)


@pytest.mark.parametrize("alias", ["python.exe", "PYTHON", "PowerShell.EXE",
                                   "cmd.BAT", "'sh'", "/bin/bash"])
def test_alias_and_variation_bypass_is_rejected(alias):
    """Nem extensões, nem caixa, nem aspas, nem caminho contornam a denylist."""
    with pytest.raises((InterpreterForbiddenError, InvalidCommandError)):
        TerminalPolicy([alias])


def test_unregistered_path_variant_does_not_match_entry(sandbox):
    """/tmp/evil/git não casa com a entrada 'git' (nome simples exigido)."""
    pol = policy("git")
    with pytest.raises(CommandNotAllowlistedError):
        pol.validate("/tmp/evil/git", [], None, sandbox)
    with pytest.raises(CommandNotAllowlistedError):
        pol.validate("./git", [], None, sandbox)


def test_full_path_entry_matches_exactly(sandbox):
    entry = AllowedCommand(name="ferramenta", full_path=Path("/opt/bin/ferramenta"))
    pol = TerminalPolicy([entry])
    result = pol.validate("/opt/bin/ferramenta", ["--versao"], None, sandbox)
    assert result.argv[0] == "/opt/bin/ferramenta"
    with pytest.raises(CommandNotAllowlistedError):
        pol.validate("/opt/outra/ferramenta", [], None, sandbox)


def test_fixed_args_allowlist(sandbox):
    pol = TerminalPolicy([AllowedCommand("git", args_allowlist=("status",))])
    pol.validate("git", ["status"], None, sandbox)  # exato passa
    with pytest.raises(CommandNotAllowlistedError):
        pol.validate("git", ["push"], None, sandbox)
    with pytest.raises(CommandNotAllowlistedError):
        pol.validate("git", [], None, sandbox)


def test_make_entry_rejects_relative_path_and_operators():
    with pytest.raises(InvalidCommandError):
        TerminalPolicy.make_entry("./git")  # caminho relativo não é allowlistável
    with pytest.raises(OperatorForbiddenError):
        TerminalPolicy.make_entry("gi;t")
    with pytest.raises(OperatorForbiddenError):
        TerminalPolicy.make_entry("gi&t")


# ------------------------------------------------------------------ argumentos
@pytest.mark.parametrize("arg", [
    "a && b", "a || b", "a | b", "a;b", ">saida.txt", ">>saida.txt",
    "<entrada", "`id`", "$(id)", "a&b",
])
def test_shell_operators_in_args_are_blocked(sandbox, arg):
    pol = policy("printf")
    with pytest.raises(OperatorForbiddenError):
        pol.validate("printf", [arg], None, sandbox)


def test_control_chars_in_args_are_blocked(sandbox):
    pol = policy("printf")
    with pytest.raises(InvalidCommandError):
        pol.validate("printf", ["linha1\nlinha2"], None, sandbox)
    with pytest.raises(InvalidCommandError):
        pol.validate("printf", ["ta\tb"], None, sandbox)


def test_operators_allowed_only_when_explicit(sandbox):
    pol = policy("printf", allow_operators=True)
    result = pol.validate("printf", ["a && b"], None, sandbox)
    assert result.argv == ("printf", "a && b")


@pytest.mark.parametrize("arg", [
    "-exec", "-execdir", "--exec", "/c", "/k", "-Command",
    "-EncodedCommand", "-enc", "--eval", "--init-command",
])
def test_dangerous_arguments_are_blocked(sandbox, arg):
    pol = policy("find")
    with pytest.raises(DangerousArgumentError):
        pol.validate("find", [arg], None, sandbox)
    pol2 = policy("git")
    with pytest.raises(DangerousArgumentError):
        pol2.validate("git", [arg.lower()], None, sandbox)


@pytest.mark.parametrize("arg", ["../fora", "a/../b", "..\\fora"])
def test_dotdot_in_args_is_blocked(sandbox, arg):
    pol = policy("printf")
    with pytest.raises(WorkspacePathBlockedError):
        pol.validate("printf", [arg], None, sandbox)


@pytest.mark.parametrize("arg", [
    "/etc/passwd", "/tmp", "C:\\Windows\\system32", "\\\\servidor\\compart",
])
def test_absolute_paths_outside_workspace_in_args_are_blocked(sandbox, arg):
    pol = policy("cat")
    with pytest.raises(WorkspacePathBlockedError):
        pol.validate("cat", [arg], None, sandbox)


def test_absolute_path_inside_workspace_in_args_is_allowed(sandbox, ws):
    pol = policy("cat")
    inside = str(ws / "leia.txt")
    pol.validate("cat", [inside], None, sandbox)  # não levanta


def test_relative_path_args_are_allowed(sandbox):
    pol = policy("cat")
    pol.validate("cat", ["docs/leia.txt"], None, sandbox)


# ------------------------------------------------------------------------ cwd
def test_cwd_outside_workspace_is_blocked(sandbox, tmp_path):
    fora = tmp_path / "fora"
    fora.mkdir()
    pol = policy("ls")
    with pytest.raises(WorkspacePathBlockedError):
        pol.validate("ls", [], str(fora), sandbox)
    with pytest.raises(WorkspacePathBlockedError):
        pol.validate("ls", [], "..", sandbox)
    with pytest.raises(WorkspacePathBlockedError):
        pol.validate("ls", [], "sub/../..", sandbox)


def test_cwd_must_exist(sandbox):
    pol = policy("ls")
    with pytest.raises(InvalidCommandError):
        pol.validate("ls", [], "nao-existe", sandbox)


def test_cwd_relative_inside_workspace(sandbox, ws):
    (ws / "sub").mkdir()
    pol = policy("ls")
    result = pol.validate("ls", [], "sub", sandbox)
    assert result.cwd == (ws / "sub").resolve()


# -------------------------------------------------------------------- timeout
def test_timeout_defaults_and_clamp(sandbox):
    pol = policy("sleep", default_timeout_s=10, max_timeout_s=30)
    result = pol.validate("sleep", ["1"], None, sandbox)
    assert result.timeout_s == 10
    pol2 = TerminalPolicy([AllowedCommand("sleep", timeout_s=999)], max_timeout_s=30)
    assert pol2.validate("sleep", ["1"], None, sandbox).timeout_s == 30


@pytest.mark.parametrize("kwargs", [
    {"default_timeout_s": 0},
    {"default_timeout_s": -5},
    {"max_timeout_s": 0},
    {"default_max_output_bytes": 0},
    {"max_timeout_s": 5, "default_timeout_s": 10},
])
def test_policy_configuration_is_validated(kwargs):
    with pytest.raises(InvalidCommandError):
        TerminalPolicy(["git"], **kwargs)


# -------------------------------------------------------------------- entradas
@pytest.mark.parametrize("command,args", [
    (None, []), (123, []), ("", []), ("   ", []), ("gu\tito", []),
    ("'git'", []), ('"git"', []),
])
def test_malformed_command_inputs(sandbox, command, args):
    pol = policy("git")
    with pytest.raises(InvalidCommandError):
        pol.validate(command, args, None, sandbox)


@pytest.mark.parametrize("args", ["não-lista", 42, {"a": 1}, ("ok", 7)])
def test_malformed_args_inputs(sandbox, args):
    pol = policy("git")
    with pytest.raises(InvalidCommandError):
        pol.validate("git", args, None, sandbox)


def test_args_with_non_string_items(sandbox):
    pol = policy("git")
    with pytest.raises(InvalidCommandError):
        pol.validate("git", ["ok", 7], None, sandbox)


def test_args_none_is_empty(sandbox):
    result = policy("git").validate("git", None, None, sandbox)
    assert result.argv == ("git",)


def test_normalize_command_variants():
    assert normalize_command("git") == "git"
    assert normalize_command("Git.EXE") == "git"
    assert normalize_command("/bin/SH") == "sh"
    assert normalize_command("PowerShell.CMD") == "powershell"
    assert normalize_command("  'Python' ") == "python"
