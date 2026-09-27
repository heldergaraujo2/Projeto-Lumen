"""Ferramentas de terminal da Lumen (0.6) — fundação controlada e auditável.

Segunda camada de **ferramentas reais** (depois do filesystem 0.5): a
execução de comandos, **sempre confinada por uma allowlist explícita**
(:class:`TerminalPolicy`) e **sempre auditada** (:class:`RunCommandTool`).

Modelo de segurança (mesma filosofia do filesystem, adaptada):

- **Allowlist explícita** — nada executa se o comando não foi registrado
  por quem integra (:meth:`TerminalPolicy.allow`). Não existe
  ``execute_any_command("qualquer coisa")``: comando fora da lista é
  **bloqueado antes de qualquer execução** (decisão mais rígida que a do
  ROADMAP original, que sugeria confirmação para comandos fora da lista
  — prevalece a spec 0.6: fora da allowlist = bloqueado).
- **Denylist permanente** (:data:`FORBIDDEN_COMMANDS`) — shells,
  interpretadores, executores de subcomandos, ferramentas de build que
  rodam código arbitrário, comandos destrutivos/administrativos e de
  rede **nunca** podem ser allowlistados (nem como alias/variação:
  ``python.exe``, ``POWERSHELL``, ``/bin/sh`` são rejeitados pela
  normalização). A rede continua **inacessível** às ferramentas.
- **Sem shell** — o comando roda como ``argv`` lista (``shell=False``);
  operadores de shell (``&&``, ``|``, ``;``, ``>``, ``$(``…) e
  redirecionamentos em argumentos são **bloqueados** a menos que a
  política explicitamente permita (:attr:`TerminalPolicy.allow_operators`).
- **Sandbox do diretório de trabalho** — o ``cwd`` é resolvido e
  confinado aos workspaces autorizados (mesmo contrato do filesystem);
  argumentos que pareçam caminhos absolutos fora dos workspaces e
  componentes ``..`` também são bloqueados.
- **Timeout obrigatório** — sempre aplicado (default 10 s, teto 60 s);
  estourar mata o processo e falha de forma controlada.
- **Limite de saída** — ``stdout``/``stderr`` capturados com teto de
  bytes (default 64 KiB); exceder trunca, mata se necessário e falha de
  forma honesta (``truncated=True``).
- **Ambiente sanitizado** — o processo filho recebe apenas variáveis de
  ambiente seguras (``PATH``, localização de sistema…); nada que pareça
  segredo (``*KEY*``/``*TOKEN*``/``*SECRET*``/``*PASSWORD*``) é
  repassado, para que comandos como ``printenv`` nunca vazem credenciais.
- **Permissão** — :attr:`PermissionLevel.TERMINAL` exigida pelo porteiro
  (:class:`~app.tools.base.ToolRegistry`) **antes** de qualquer código da
  ferramenta rodar; READ/WRITE não bastam.
- **Checkpoint** — todo comando allowlistado pede aprovação por padrão
  (:attr:`AllowedCommand.requires_approval`); comandos marcados como
  seguros (ex.: ``git status``) podem dispensar. O pedido só ocorre para
  operações **viáveis** (ver :class:`PrevalidatedTerminalCheckpoints`,
  mesma lógica da 0.5.1 — sem aprovação decorativa).
- **Auditoria** — toda tentativa registra ferramenta, comando
  (representação ``argv`` sanitizada e truncada — nunca saída/entrada
  completa), cwd solicitado/resolvido, exit code, desfecho, erro,
  timestamp e tarefa/plano. Conteúdo sensível de arquivos e segredos
  **nunca** são registrados.

Limites honestos (documentados, sem promessa de isolamento de SO): a
allowlist é um ato de confiança explícita do integrador — um comando
legitimamente allowlistado pode, por natureza, ter efeitos além do cwd
(ex.: escrever em caminho interno fixo). As defesas de argumento
(caminhos fora, ``..``, operadores) são profundidade, não substituto de
sandbox de sistema operacional.

O que NÃO existe aqui (e continua proibido): coding agent, edição
inteligente de código, vision/screenshot, mouse, teclado, computer
control, Unreal, rede das ferramentas, execução irrestrita.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Sequence

from app.security.permissions import PermissionLevel, PermissionManager
from app.tools.base import StructuredTool, ToolRegistry, ToolResult
from app.tools.filesystem import FilesystemAudit, WorkspaceSandbox
from app.tools.handler import ToolCheckpoints

logger = logging.getLogger("lumen.tools.terminal")

#: Nome canônico da ferramenta de terminal.
TERMINAL_TOOL_NAME = "run_command"

#: Rótulo da operação para auditoria/checkpoint.
TERMINAL_OPERATION = "run_command"

#: Comandos que JAMAIS podem ser allowlistados (normalizados: minúsculas,
#: sem extensão executável do Windows). Inclui:
#: shells e interpretadores (rodam código arbitrário), executores de
#: subcomandos (env/nohup/xargs/time/watch…), ferramentas de build
#: (make/cmake/dotnet/cargo/go…), escalonamento de privilégio, comandos
#: destrutivos/administrativos e de rede (a rede segue inacessível).
FORBIDDEN_COMMANDS: frozenset[str] = frozenset({
    # shells / launchers
    "sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh", "fish", "ash",
    "powershell", "pwsh", "cmd", "wscript", "cscript", "mshta", "wsl",
    # interpretadores (código arbitrário)
    "python", "python2", "python3", "py", "pip", "pip2", "pip3",
    "node", "npm", "npx", "yarn", "pnpm", "deno", "bun",
    "ruby", "gem", "perl", "php", "lua", "luajit",
    "java", "javac", "kotlin", "scala", "groovy", "r", "rscript",
    # build/execução de código arbitrário
    "make", "cmake", "ninja", "msbuild", "dotnet", "cargo", "go",
    "gradle", "mvn", "docker", "kubectl", "podman",
    # executores de subcomando / observação intrusiva
    "env", "nohup", "nice", "setsid", "xargs", "parallel", "time",
    "watch", "strace", "ltrace", "gdb",
    # escalonamento de privilégio
    "sudo", "su", "doas", "runas", "pkexec",
    # administrativos / de serviço (Windows e Unix)
    "net", "net1", "sc", "reg", "regedit", "schtasks", "taskkill",
    "netsh", "ip", "ifconfig", "route", "arp",
    # desligamento / init
    "shutdown", "restart", "reboot", "halt", "poweroff",
    "init", "telinit", "systemctl", "service",
    # destrutivos de disco/arquivo em largo alcance
    "diskpart", "format", "del", "erase", "rm", "unlink", "rmdir", "rd",
    "shred", "wipefs", "dd", "mkfs", "fdisk", "sfdisk", "parted",
    "mkswap", "mount", "umount", "vssadmin", "bcdedit", "cipher",
    # permissões / propriedade
    "chmod", "chown", "chgrp", "chattr", "icacls", "cacls", "takeown",
    "attrib", "setacl",
    # rede (a rede das ferramentas continua inexistente)
    "curl", "wget", "ssh", "scp", "sftp", "ftp", "telnet", "nc", "ncat",
    "netcat", "rsync", "ping", "ping6", "nslookup", "dig",
})

#: Argumentos sempre bloqueados (exatos, sem distinção de caixa):
#: escapam por outro caminho para executar código/comandos.
DANGEROUS_ARGUMENTS: frozenset[str] = frozenset({
    "-exec", "-execdir", "--exec",          # find… -exec cmd
    "/c", "/k",                             # cmd /c …
    "-command", "--command",                # powershell -Command …
    "-encodedcommand", "--encodedcommand",  # powershell -EncodedCommand …
    "-enc",                                 # abreviação do anterior
    "--eval", "--execute",                  # opções de eval/execução
    "--init-command",                       # git --init-command=… (eval)
})

#: Tokens de shell/redirecionamento proibidos em argumentos quando a
#: política não permite operadores explicitamente.
OPERATOR_TOKENS: tuple[str, ...] = (
    "&&", "||", "|", ";", "&", ">", "<", "`", "$(", "$[", "\n", "\r",
)

#: Extensões executáveis do Windows (descartadas na normalização).
_WINDOWS_EXE_SUFFIXES = (".exe", ".bat", ".cmd", ".com", ".ps1")

#: Variáveis de ambiente consideradas seguras para o processo filho.
#: Qualquer outra (e anything com KEY/TOKEN/SECRET/PASSWORD) é descartada.
SAFE_ENV_VARS: frozenset[str] = frozenset({
    "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ",
    "HOME", "USER", "TMPDIR", "TEMP", "TMP",
    "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
})

SAFE_ENV_VARS_UPPER: frozenset[str] = frozenset(v.upper() for v in SAFE_ENV_VARS)


#: Marcadores de segredo no NOME de variáveis de ambiente.
_SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


class TerminalSecurityError(Exception):
    """Bloqueio/falha de segurança da camada de terminal (mensagem amigável)."""


class CommandNotAllowlistedError(TerminalSecurityError):
    """Comando fora da allowlist — bloqueado antes de qualquer execução."""


class InterpreterForbiddenError(TerminalSecurityError):
    """Comando proibido (shell/interpretador/destrutivo/administrativo)."""


class OperatorForbiddenError(TerminalSecurityError):
    """Operador de shell/redirecionamento não permitido em argumento."""


class DangerousArgumentError(TerminalSecurityError):
    """Argumento conhecido como via de execução arbitrária (ex.: -exec)."""


class WorkspacePathBlockedError(TerminalSecurityError):
    """Caminho (cwd ou argumento) fora dos workspaces autorizados."""


class InvalidCommandError(TerminalSecurityError):
    """Entrada malformada (tipos errados, vazio, caracteres de controle)."""


class CommandTimeoutError(TerminalSecurityError):
    """O comando excedeu o tempo limite e foi morto."""


def normalize_command(name: str) -> str:
    """Normaliza um nome de comando para comparação de políticas.

    Minúsculas, sem aspas, sem extensão executável do Windows
    (``Git.EXE`` → ``git``). ``/bin/sh`` → ``sh`` (basename) — usado
    apenas para a checagem de denylist; allowlist com caminho exige
    :attr:`AllowedCommand.full_path` exato.
    """
    normalized = name.strip().strip("\"'").lower()
    base = normalized.replace("\\", "/").rsplit("/", 1)[-1]
    for suffix in _WINDOWS_EXE_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base


def _looks_absolute_path(value: str) -> bool:
    """Detecta caminhos absolutos POSIX e estilo Windows (drive)."""
    if value.startswith("/"):
        return True
    try:
        return PureWindowsPath(value).is_absolute()
    except ValueError:  # pragma: no cover - pathlib é tolerante
        return False


def _has_control_chars(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _sanitize_for_audit(argv: Sequence[str], *, limit_args: int = 32,
                        limit_chars: int = 200) -> list[str]:
    """Representação segura do comando para auditoria (sem despejar dados).

    Limita a quantidade de argumentos e o tamanho de cada um — a trilha
    registra o que foi pedido, não conteúdo grande passado como argumento.
    """
    sanitized: list[str] = []
    for arg in list(argv)[:limit_args]:
        if len(arg) > limit_chars:
            sanitized.append(arg[:limit_chars] + "…")
        else:
            sanitized.append(arg)
    if len(argv) > limit_args:
        sanitized.append(f"… (+{len(argv) - limit_args} argumentos)")
    return sanitized


@dataclass(frozen=True)
class AllowedCommand:
    """Um comando explicitamente permitido pela política de terminal.

    Args:
        name: nome canônico (normalizado) — ex.: ``git``.
        full_path: caminho absoluto opcional do binário. Quando definido,
            a chamada deve usar **exatamente** este caminho; quando não,
            a chamada deve usar o nome simples (resolvido pelo ``PATH``)
            — ``/tmp/evil/git`` nunca casa com a entrada ``git``.
        args_allowlist: se definida, os argumentos devem ser exatamente
            esses (na ordem); vazia = qualquer argumento que passe nas
            validações de segurança.
        requires_approval: se o comando exige checkpoint (default ``True``
            — todo comando pede aprovação; marque ``False`` apenas para
            comandos comprovadamente inofensivos, ex.: ``git status``).
        timeout_s: timeout próprio (clampado ao teto da política).
        max_output_bytes: teto próprio de saída.
        description: descrição legível para auditoria/UI.
    """

    name: str
    full_path: Path | None = None
    args_allowlist: tuple[str, ...] = ()
    requires_approval: bool = True
    timeout_s: int | None = None
    max_output_bytes: int | None = None
    description: str = ""


@dataclass(frozen=True)
class ValidatedCommand:
    """Resultado da validação — o que de fato vai rodar."""

    argv: tuple[str, ...]
    cwd: Path
    timeout_s: int
    max_output_bytes: int
    requires_approval: bool
    entry: AllowedCommand


class TerminalPolicy:
    """Allowlist explícita + validação completa antes de qualquer execução.

    Args:
        allowed_commands: comandos permitidos (:class:`AllowedCommand` ou
            nome simples — ``"git"`` vira ``AllowedCommand("git")``).
        default_timeout_s: timeout padrão (obrigatório > 0).
        max_timeout_s: teto de timeout por comando (clamp).
        default_max_output_bytes: teto padrão de stdout/stderr.
        allow_operators: permite operadores de shell/redirecionamento em
            argumentos (default ``False`` — bloqueados).
    """

    def __init__(
        self,
        allowed_commands: Iterable[AllowedCommand | str] = (),
        *,
        default_timeout_s: int = 10,
        max_timeout_s: int = 60,
        default_max_output_bytes: int = 64 * 1024,
        allow_operators: bool = False,
    ) -> None:
        if default_timeout_s <= 0 or max_timeout_s <= 0:
            raise InvalidCommandError("Timeout deve ser positivo (segundos).")
        if max_timeout_s < default_timeout_s:
            raise InvalidCommandError(
                "Teto de timeout menor que o timeout padrão."
            )
        if default_max_output_bytes <= 0:
            raise InvalidCommandError("Limite de saída deve ser positivo.")
        self._allowed: dict[str, AllowedCommand] = {}
        for spec in allowed_commands:
            entry = spec if isinstance(spec, AllowedCommand) else self.make_entry(spec)
            self._register(entry)
        self._default_timeout_s = int(default_timeout_s)
        self._max_timeout_s = int(max_timeout_s)
        self._default_max_output_bytes = int(default_max_output_bytes)
        self._allow_operators = bool(allow_operators)

    # ------------------------------------------------------------- registro
    @staticmethod
    def make_entry(name: str, **kwargs: Any) -> AllowedCommand:
        """Cria :class:`AllowedCommand` validando o nome (sem registrar)."""
        if not isinstance(name, str) or not name.strip():
            raise InvalidCommandError("Nome de comando deve ser texto não vazio.")
        if _has_control_chars(name):
            raise InvalidCommandError("Nome contém caracteres de controle.")
        if any(token in name for token in OPERATOR_TOKENS):
            raise OperatorForbiddenError(
                f"Nome de comando não pode conter operadores: {name!r}."
            )
        # full_path explícito (restauração da persistência) tem prioridade;
        # senão, deriva do nome quando este é um caminho absoluto.
        full_path: Path | None = kwargs.pop("full_path", None)
        if full_path is not None:
            full_path = Path(full_path)
        elif "/" in name or "\\" in name:
            candidate = Path(name)
            if not candidate.is_absolute():
                raise InvalidCommandError(
                    f"Caminho de comando deve ser absoluto: {name!r}."
                )
            full_path = candidate
        normalized = normalize_command(name)
        if normalized in FORBIDDEN_COMMANDS:
            raise InterpreterForbiddenError(
                f"Comando {normalized!r} é proibido por política permanente "
                "(shell/interpretador/execução arbitrária/destrutivo/"
                "administrativo/rede) e não pode ser allowlistado."
            )
        return AllowedCommand(name=normalized, full_path=full_path, **kwargs)

    def allow(self, name: str, **kwargs: Any) -> AllowedCommand:
        """Registra um comando permitido (explícito; denylist rejeita)."""
        entry = self.make_entry(name, **kwargs)
        self._register(entry)
        logger.info("Comando allowlistado: %s (aprovação=%s).",
                    entry.name, entry.requires_approval)
        return entry

    def _register(self, entry: AllowedCommand) -> None:
        if entry.name in FORBIDDEN_COMMANDS:  # defesa extra (entrada direta)
            raise InterpreterForbiddenError(
                f"Comando {entry.name!r} é proibido por política permanente."
            )
        self._allowed[entry.name] = entry

    # ------------------------------------------------------------ consultas
    @property
    def default_timeout_s(self) -> int:
        return self._default_timeout_s

    @property
    def max_timeout_s(self) -> int:
        return self._max_timeout_s

    @property
    def default_max_output_bytes(self) -> int:
        return self._default_max_output_bytes

    @property
    def allowed_names(self) -> tuple[str, ...]:
        return tuple(self._allowed)

    def entries(self) -> tuple[AllowedCommand, ...]:
        """Entradas allowlistadas (ordem de registro)."""
        return tuple(self._allowed.values())

    def remove(self, name: str) -> AllowedCommand:
        """Remove um comando da allowlist (explícito; inexistente é erro)."""
        if not isinstance(name, str) or not name.strip():
            raise InvalidCommandError("Nome de comando deve ser texto não vazio.")
        normalized = normalize_command(name)
        entry = self._allowed.pop(normalized, None)
        if entry is None:
            raise CommandNotAllowlistedError(
                f"Comando {name!r} não está na allowlist."
            )
        logger.info("Comando removido da allowlist: %s.", normalized)
        return entry

    @property
    def allow_operators(self) -> bool:
        return self._allow_operators

    def entry_for(self, command: str) -> AllowedCommand | None:
        """Entrada da allowlist para ``command`` (normalizada), se houver."""
        if not isinstance(command, str):
            return None
        if "/" in command or "\\" in command:
            # Caminho: só casa com entrada com full_path EXATAMENTE igual
            # (comparação normalizada pelo Path do SO: no Windows "/x/y" e
            # "\x\y" são o MESMO caminho — não há fallback p/ nome simples).
            try:
                requested = Path(command)
            except (OSError, ValueError):
                return None  # caminho inválido ⇒ fail closed
            for entry in self._allowed.values():
                if entry.full_path is None:
                    continue
                try:
                    if requested == entry.full_path:
                        return entry
                except (OSError, ValueError):
                    continue
            return None
        return self._allowed.get(normalize_command(command))

    # ------------------------------------------------------------ validação
    def validate(
        self,
        command: Any,
        args: Any,
        cwd: Any,
        sandbox: WorkspaceSandbox,
    ) -> ValidatedCommand:
        """Valida comando/argumentos/cwd contra toda a política.

        Levanta :class:`TerminalSecurityError` (subtipos) com motivo
        claro. Não executa nada — usada antes do checkpoint (viabilidade)
        e de novo antes da execução real (defesa em profundidade).
        """
        if not isinstance(command, str) or not command.strip():
            raise InvalidCommandError(
                "Parâmetro 'command' é obrigatório e deve ser texto."
            )
        if _has_control_chars(command):
            raise InvalidCommandError("Comando contém caracteres de controle.")
        if "\"" in command or "'" in command:
            raise InvalidCommandError(
                "Comando não pode conter aspas (use o nome simples ou o "
                "caminho exato registrado)."
            )
        if args is None:
            args_list: list[str] = []
        elif isinstance(args, (list, tuple)) and all(isinstance(a, str) for a in args):
            args_list = list(args)
        else:
            raise InvalidCommandError(
                "Parâmetro 'args' deve ser uma lista de textos."
            )

        # 1) denylist permanente (antes de tudo, mesmo antes da allowlist).
        normalized = normalize_command(command)
        if normalized in FORBIDDEN_COMMANDS:
            raise InterpreterForbiddenError(
                f"Comando {normalized!r} é proibido (política permanente)."
            )

        # 2) allowlist explícita (fora da lista ⇒ bloqueado, sem execução).
        entry = self.entry_for(command)
        if entry is None:
            raise CommandNotAllowlistedError(
                f"Comando {command!r} não está na allowlist de terminal — "
                "bloqueado antes da execução."
            )
        if entry.full_path is not None:
            if "/" in command or "\\" in command:
                # Casou pelo caminho completo: executa exatamente o que foi
                # validado (o comando pedido, já igual ao full_path registrado
                # após a normalização do SO — barras do Windows incluídas).
                argv0 = command
            else:
                # Nome simples em entrada com full_path: o caminho registrado
                # tem prioridade (binário exato — comportamento 0.6.x).
                argv0 = str(entry.full_path)
        else:
            if "/" in command or "\\" in command:
                raise CommandNotAllowlistedError(
                    f"Caminho de comando não autorizado: {command!r} "
                    "(use o nome simples ou registre o caminho exato)."
                )
            argv0 = command

        # 3) argumentos: tipos, operadores, argumentos perigosos e caminhos.
        if entry.args_allowlist:
            expected = list(entry.args_allowlist)
            if args_list != expected:
                raise CommandNotAllowlistedError(
                    f"Argumentos não correspondem aos permitidos para "
                    f"{entry.name!r} (esperado: {expected!r})."
                )
        self._validate_args(args_list, sandbox)

        # 4) cwd: confinado aos workspaces (mesmo contrato do filesystem).
        cwd_requested = cwd if isinstance(cwd, str) and cwd.strip() else "."
        if _has_control_chars(cwd_requested):
            raise InvalidCommandError("cwd contém caracteres de controle.")
        try:
            resolved_cwd = sandbox.resolve(cwd_requested)
        except Exception as exc:  # FilesystemError: fora/traversal/inválido
            raise WorkspacePathBlockedError(
                f"Diretório de trabalho bloqueado: {exc}"
            ) from exc
        if not resolved_cwd.is_dir():
            raise InvalidCommandError(
                f"Diretório de trabalho não existe ou não é diretório: "
                f"{resolved_cwd}."
            )

        # 5) timeout e limites (obrigatórios, clampados).
        timeout_s = entry.timeout_s if entry.timeout_s is not None else self._default_timeout_s
        if timeout_s <= 0:
            raise InvalidCommandError("Timeout deve ser positivo.")
        timeout_s = min(timeout_s, self._max_timeout_s)
        max_output = (
            entry.max_output_bytes
            if entry.max_output_bytes is not None
            else self._default_max_output_bytes
        )
        if max_output <= 0:  # pragma: no cover - make via policy construtor
            raise InvalidCommandError("Limite de saída deve ser positivo.")

        return ValidatedCommand(
            argv=(argv0, *args_list),
            cwd=resolved_cwd,
            timeout_s=timeout_s,
            max_output_bytes=max_output,
            requires_approval=entry.requires_approval,
            entry=entry,
        )

    def _validate_args(self, args: list[str], sandbox: WorkspaceSandbox) -> None:
        for arg in args:
            if _has_control_chars(arg):
                raise InvalidCommandError(
                    "Argumento contém caracteres de controle (inválido)."
                )
            if not self._allow_operators:
                for token in OPERATOR_TOKENS:
                    if token in arg:
                        raise OperatorForbiddenError(
                            f"Argumento contém operador de shell "
                            f"{token!r} (não permitido): {arg[:120]!r}."
                        )
            lowered = arg.strip().strip("\"'").lower()
            if lowered in DANGEROUS_ARGUMENTS:
                raise DangerousArgumentError(
                    f"Argumento perigoso bloqueado: {arg!r} "
                    "(via de execução arbitrária)."
                )
            if ".." in Path(arg.replace("\\", "/")).parts:
                raise WorkspacePathBlockedError(
                    f"Argumento com componente '..' bloqueado: {arg[:120]!r}."
                )
            if _looks_absolute_path(arg):
                if not self._path_inside_workspace(arg, sandbox):
                    raise WorkspacePathBlockedError(
                        f"Argumento aponta caminho absoluto fora dos "
                        f"workspaces autorizados: {arg[:120]!r}."
                    )

    @staticmethod
    def _path_inside_workspace(value: str, sandbox: WorkspaceSandbox) -> bool:
        """Contenção de um caminho absoluto (POSIX agora; Windows no alvo)."""
        try:
            resolved = Path(value).resolve()
        except (OSError, RuntimeError):  # pragma: no cover - defensivo
            return False
        for root in sandbox.roots:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False


def build_safe_environment() -> dict[str, str]:
    """Ambiente mínimo e sanitizado para o processo filho.

    Apenas variáveis seguras (``PATH``, localização de sistema, locale,
    temporários); nomes com marcadores de segredo são sempre descartados
    — um ``printenv`` jamais expõe credenciais da Lumen.
    """
    env: dict[str, str] = {}
    for name, value in os.environ.items():
        upper = name.upper()
        if any(marker in upper for marker in _SECRET_MARKERS):
            continue
        if upper in SAFE_ENV_VARS_UPPER or upper.startswith("LC_"):
            env[upper] = value
    env.setdefault("PATH", os.defpath)
    return env


class RunCommandTool(StructuredTool):
    """Executa um comando da allowlist, confinado e auditado (TERMINAL).

    Parâmetros: ``command`` (nome allowlistado), ``args`` (lista de
    textos) e ``cwd`` (diretório de trabalho dentro do workspace;
    default: primeiro workspace autorizado).
    """

    name = TERMINAL_TOOL_NAME
    description = (
        "Executa um comando da allowlist de terminal, dentro do workspace, "
        "com timeout, limite de saída e auditoria (permissão TERMINAL)."
    )
    required_permission = PermissionLevel.TERMINAL
    operation = TERMINAL_OPERATION

    def __init__(
        self,
        policy: TerminalPolicy,
        sandbox: WorkspaceSandbox,
        audit: FilesystemAudit | None = None,
    ) -> None:
        self._policy = policy
        self._sandbox = sandbox
        self._audit = audit

    # ------------------------------------------------------------- execução
    def run(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command")
        args = kwargs.get("args", [])
        cwd = kwargs.get("cwd")
        base = {
            "operation": self.operation,
            "command": _sanitize_for_audit(
                [command] + list(args) if isinstance(command, str)
                else [str(command)]
            ),
        }
        try:
            validated = self._policy.validate(command, args, cwd, self._sandbox)
        except TerminalSecurityError as exc:
            logger.warning("Comando bloqueado pela política: %s", exc)
            self._audit_record(base["command"], None, success=False, error=str(exc),
                               exit_code=None)
            return ToolResult(
                ok=False,
                data={**base, "exit_code": None, "cwd_requested": cwd},
                error=str(exc),
            )

        started = time.monotonic()
        try:
            outcome = self._execute_subprocess(validated)
        except FileNotFoundError:
            error = f"Comando não encontrado: {validated.argv[0]!r}."
            logger.warning("%s", error)
            self._audit_record(base["command"], str(validated.cwd),
                               success=False, error=error, exit_code=None)
            return ToolResult(ok=False, data={**base, **self._meta(validated, None,
                               time.monotonic() - started)}, error=error)
        except OSError as exc:
            error = f"Falha ao executar o comando: {exc}"
            logger.error("%s", error)
            self._audit_record(base["command"], str(validated.cwd),
                               success=False, error=error, exit_code=None)
            return ToolResult(ok=False, data={**base, **self._meta(validated, None,
                               time.monotonic() - started)}, error=error)

        duration_ms = time.monotonic() - started
        meta = self._meta(validated, outcome["exit_code"], duration_ms)
        data: dict[str, Any] = {
            **base,
            **meta,
            "stdout": outcome["stdout"],
            "stderr": outcome["stderr"],
            "truncated": outcome["truncated"],
            "timed_out": outcome["timed_out"],
            "exit_code": outcome["exit_code"],
        }
        if outcome["timed_out"]:
            error = (
                f"Comando excedeu o timeout de {validated.timeout_s}s "
                "e foi encerrado."
            )
            self._audit_record(base["command"], str(validated.cwd),
                               success=False, error=error,
                               exit_code=outcome["exit_code"],
                               duration_ms=data["duration_ms"], timed_out=True)
            return ToolResult(ok=False, data=data, error=error)
        if outcome["truncated"]:
            error = (
                f"Saída excedeu o limite de {validated.max_output_bytes} bytes "
                "e foi truncada — aumente o limite ou filtre a saída."
            )
            self._audit_record(base["command"], str(validated.cwd),
                               success=False, error=error,
                               exit_code=outcome["exit_code"],
                               duration_ms=data["duration_ms"], truncated=True)
            return ToolResult(ok=False, data=data, error=error)
        if outcome["exit_code"] != 0:
            error = f"Comando falhou com exit code {outcome['exit_code']}."
            self._audit_record(base["command"], str(validated.cwd),
                               success=False, error=error,
                               exit_code=outcome["exit_code"],
                               duration_ms=data["duration_ms"])
            return ToolResult(ok=False, data=data, error=error)

        self._audit_record(base["command"], str(validated.cwd), success=True,
                           exit_code=0, duration_ms=data["duration_ms"])
        return ToolResult(ok=True, data=data)

    # ----------------------------------------------------------- subprocess
    def _execute_subprocess(self, validated: ValidatedCommand) -> dict[str, Any]:
        """Roda o argv validado com timeout e teto de saída (sem shell)."""
        try:
            process = subprocess.Popen(  # noqa: S603 - argv validado, shell=False
                list(validated.argv),
                cwd=str(validated.cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                env=build_safe_environment(),
                shell=False,
            )
        except FileNotFoundError:
            raise
        outputs = {"stdout": bytearray(), "stderr": bytearray()}
        truncated = {"stdout": False, "stderr": False}

        def _read(key: str) -> None:
            stream = process.stdout if key == "stdout" else process.stderr
            assert stream is not None
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    return
                buffer = outputs[key]
                if len(buffer) < validated.max_output_bytes:
                    room = validated.max_output_bytes - len(buffer)
                    buffer.extend(chunk[:room])
                    if len(chunk) > room:
                        truncated[key] = True
                else:
                    truncated[key] = True

        readers = [
            threading.Thread(target=_read, args=("stdout",), daemon=True),
            threading.Thread(target=_read, args=("stderr",), daemon=True),
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            process.wait(timeout=validated.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - kill é duro
                logger.error("Processo não terminou após kill: %s", validated.argv[0])
        for reader in readers:
            reader.join(timeout=5)
        return {
            "exit_code": process.returncode,
            "stdout": outputs["stdout"].decode("utf-8", errors="replace"),
            "stderr": outputs["stderr"].decode("utf-8", errors="replace"),
            "truncated": truncated["stdout"] or truncated["stderr"],
            "timed_out": timed_out,
        }

    @staticmethod
    def _meta(validated: ValidatedCommand, exit_code: int | None,
              duration: float) -> dict[str, Any]:
        return {
            "cwd": str(validated.cwd),
            "timeout_s": validated.timeout_s,
            "max_output_bytes": validated.max_output_bytes,
            "exit_code": exit_code,
            "duration_ms": int(duration * 1000),
            "requires_approval": validated.requires_approval,
        }

    def _audit_record(self, command: list[str], cwd: str | None, *, success: bool,
                      error: str | None = None, exit_code: int | None = None,
                      duration_ms: int | None = None,
                      **extra: Any) -> None:
        if self._audit is None:
            return
        self._audit.record(
            tool=self.name,
            operation=self.operation,
            requested_path=cwd,
            resolved_path=cwd,
            success=success,
            error=error,
            command=command,
            exit_code=exit_code,
            duration_ms=duration_ms,
            **extra,
        )


class TerminalStoreError(RuntimeError):
    """Falha de leitura/escrita da persistência da allowlist."""


class TerminalStore:
    """Persistência da allowlist de terminal (0.6.x) — JSON local, atômico.

    ``data/terminal.json`` guarda os comandos permitidos e os defaults da
    política. O arquivo **só nasce no primeiro save** (startup sem
    efeitos colaterais). A **permissão ``TERMINAL`` nunca é persistida**
    — concessão é ato explícito por sessão (sem concessão silenciosa);
    sem ela, a allowlist carregada não executa nada (o porteiro bloqueia).
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, Any] | None:
        """Lê a configuração persistida; ``None`` se o arquivo não existe.

        Estrutura::

            {"commands": [{...AllowedCommand serializado...}, ...],
             "defaults": {"default_timeout_s": 10, "max_timeout_s": 60,
                          "default_max_output_bytes": 65536,
                          "allow_operators": false}}

        Arquivo corrompido levanta :class:`TerminalStoreError` (o chamador
        decide — o controller **falha fechado**: terminal desabilitado).
        """
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TerminalStoreError(
                f"Allowlist de terminal ilegível ({self._path}): {exc}"
            ) from exc
        if not isinstance(data, dict) or not isinstance(
            data.get("commands", []), list
        ):
            raise TerminalStoreError(
                f"Allowlist de terminal com formato inválido: {self._path}"
            )
        return data

    def save(
        self,
        commands: Sequence[AllowedCommand],
        defaults: dict[str, Any],
    ) -> None:
        """Grava allowlist + defaults (escrita atômica: tmp + replace)."""
        payload = {
            "commands": [
                {
                    "name": entry.name,
                    "full_path": str(entry.full_path) if entry.full_path else None,
                    "args_allowlist": list(entry.args_allowlist),
                    "requires_approval": entry.requires_approval,
                    "timeout_s": entry.timeout_s,
                    "max_output_bytes": entry.max_output_bytes,
                    "description": entry.description,
                }
                for entry in commands
            ],
            "defaults": dict(defaults),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self._path)


def build_terminal_registry(
    permissions: PermissionManager,
    policy: TerminalPolicy,
    sandbox: WorkspaceSandbox,
    audit: FilesystemAudit | None = None,
) -> ToolRegistry:
    """Registry com a ferramenta ``run_command`` (registro explícito)."""
    registry = ToolRegistry(permissions)
    registry.register(RunCommandTool(policy, sandbox, audit))
    return registry


class PrevalidatedTerminalCheckpoints(ToolCheckpoints):
    """Checkpoint de terminal **somente para comandos viáveis** (0.6).

    Mesma lógica da 0.5.1 (:class:`app.tools.control.PrevalidatedCheckpoints`):
    pede aprovação apenas quando (1) a ferramenta é ``run_command`` ou
    ``run_pytest``, (2) a permissão ``TERMINAL`` está concedida e (3) a
    tarefa é viável — para ``run_command``: o comando passa por toda a
    política (allowlist + argumentos + cwd) e está marcado
    :attr:`AllowedCommand.requires_approval`; para ``run_pytest`` (11D):
    os inputs da tool são válidos e o path está confinado no sandbox
    (fora da ``TerminalPolicy`` por design). Caso contrário a tarefa
    roda no handler e falha/bloqueia com o motivo real — nunca
    interrogamos o usuário sobre algo inviável (aprovação decorativa).
    """

    def __init__(
        self,
        permissions: PermissionManager,
        registry: ToolRegistry,
        policy: TerminalPolicy,
        sandbox: WorkspaceSandbox,
    ) -> None:
        # 11D: run_pytest também pausa para checkpoint. Literal (e não
        # RUN_PYTEST_TOOL_NAME) para evitar import em ciclo — run_pytest
        # importa build_safe_environment deste módulo.
        super().__init__((TERMINAL_TOOL_NAME, "run_pytest"))
        self._permissions = permissions
        self._registry = registry
        self._policy = policy
        self._sandbox = sandbox

    def requires_checkpoint(self, task) -> bool:  # type: ignore[override]
        if not super().requires_checkpoint(task):
            return False
        if not task.tool:
            return False
        try:
            tool = self._registry.get(task.tool)
        except Exception:
            return False  # não registrada: falha controlada no handler
        if not self._permissions.is_granted(tool.required_permission):
            return False  # sem TERMINAL: o porteiro bloqueia de verdade
        parameters = dict(task.parameters or {})
        if task.tool == "run_pytest":
            # 11D: fora da TerminalPolicy por design (python/pytest são
            # FORBIDDEN_COMMANDS); viável ⇒ checkpoint (default
            # conservador — spec 11D §8.10, ainda em aberto).
            return self._run_pytest_viable(tool, parameters)
        try:
            validated = self._policy.validate(
                parameters.get("command"),
                parameters.get("args", []),
                parameters.get("cwd"),
                self._sandbox,
            )
        except TerminalSecurityError:
            return False  # inviável: falha controlada com o motivo real
        return validated.requires_approval

    def _run_pytest_viable(self, tool: Any, parameters: dict[str, Any]) -> bool:
        """Viabilidade de ``run_pytest`` (11D): inputs válidos + path no sandbox.

        Reaproveita a validação da própria tool (``_validated_input``) —
        sem duplicar regras aqui — e o confinamento de
        ``WorkspaceSandbox.resolve``. Qualquer falha ⇒ não viável ⇒ sem
        checkpoint (nunca aprovação decorativa); a tarefa falha no
        handler com o motivo real. Viável ⇒ checkpoint (default).
        """
        try:
            params = tool._validated_input(dict(parameters))
        except (ValueError, TypeError):
            return False
        try:
            self._sandbox.resolve(params["path"])
        except Exception:  # FilesystemError: fora/traversal/inválido
            return False
        return True
