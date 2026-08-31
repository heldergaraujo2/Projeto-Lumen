"""RunPytestTool — execução estruturada de testes pytest (11D).

**Estado (11D, parte 1/5): implementada e NÃO REGISTRADA.** Esta tool
não é construída por nenhum factory, não entra no ``ToolRegistry`` e não
consta no Planner Catalog — está inalcançável até que o wiring seja
autorizado (registro condicional em ``ToolsController.build_registry`` +
checkpoint próprio + catálogo). Ver ``docs/SPEC-11D-BUILD_TEST.md``
(DRAFT / NÃO AUTORIZADA).

Motivação (spec §3): ``python``/``pytest`` estão em
``FORBIDDEN_COMMANDS`` do terminal — **por design** — portanto
verificação real NÃO passa por ``run_command``/allowlist. Esta tool é
uma **capacidade específica** (rodar o runner conhecido com parâmetros
fechados), não um interpretador genérico (F17 preservado).

Contrato (spec §4):

- subprocesso ``[sys.executable, "-m", "pytest", ...]`` direto, **sem
  shell** e **sem** ``TerminalPolicy``;
- ``path`` relativo ao workspace (absoluto e ``..`` rejeitados;
  resolução confinada pelo ``WorkspaceSandbox``);
- ``-k`` com charset estrito (identificadores, espaço, ``-``, ``.``) —
  nada de expressões arbitrárias (spec §8.7, default conservador);
- ``maxfail`` (clamp 1..10) e ``timeout_s`` (clamp 10..600);
- sujeira zero no repo: ``-p no:cacheprovider`` + ``--basetemp`` em
  temporário do sistema + ``PYTHONDONTWRITEBYTECODE``/``PYTHONPYCACHEPREFIX``
  fora do workspace (spec §4g);
- saída combinada (stderr→stdout) com teto de bytes e truncamento
  **marcado** (``truncated``), nunca silencioso;

Semântica do ``ToolResult`` (spec §4/§5 — difere de ``run_command`` de
propósito): ``ok=False`` **apenas** para falha da tool (input inválido,
path inválido/fora do sandbox, timeout, erro de execução interna).
Se o pytest RODOU, ``exit_code != 0`` (testes falharam / nada coletado)
retorna ``ok=True`` com ``exit_code``/``summary_line`` — o contrato do
executor (``ok=False`` ⇒ FAILED com ``result=None``) esconderia a
evidência que a verificação real precisa analisar.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult
from app.tools.filesystem import FilesystemAudit, FilesystemError, WorkspaceSandbox
from app.tools.terminal import build_safe_environment

logger = logging.getLogger(__name__)

#: Nome canônico (padrão ``TERMINAL_TOOL_NAME`` do terminal).
RUN_PYTEST_TOOL_NAME = "run_pytest"
#: Operação de auditoria — mesmo formato de terminal (``run_command``).
RUN_PYTEST_OPERATION = "run_pytest"

#: Default/limites de input (spec §4b/§4c — base ajustável em revisão).
DEFAULT_PATH = "tests"
DEFAULT_MAXFAIL = 1
MAXFAIL_MIN, MAXFAIL_MAX = 1, 10
DEFAULT_TIMEOUT_S = 60
TIMEOUT_MIN_S, TIMEOUT_MAX_S = 10, 600

#: Teto de saída capturada (bytes) e janelas de debug (chars).
MAX_OUTPUT_BYTES = 200_000
HEAD_CHARS = 4_000
TAIL_CHARS = 4_000

#: Windows: caminho com drive (``C:\\...``) é absoluto também aqui.
_DRIVE_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
#: Charset permitido em ``-k`` (identificadores, espaço, hífen, ponto).
_KEYWORD_ALLOWED = re.compile(r"^[A-Za-z0-9_ .-]{1,100}$")
#: Linha-final de resumo do pytest (``N passed``, ``no tests ran``...).
_SUMMARY_LINE = re.compile(
    r"\d+ (passed|failed|skipped|deselected|error|warning)|no tests ran"
)


def _has_control_chars(text: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in text)


class RunPytestTool(StructuredTool):
    """Roda a suíte pytest do workspace de forma controlada (TERMINAL).

    Parâmetros: ``path`` (relativo ao workspace; default ``"tests"``),
    ``k`` (filtro ``-k`` opcional, charset estrito), ``maxfail``
    (default 1; clamp 1..10) e ``timeout_s`` (default 60; clamp 10..600).
    """

    name = RUN_PYTEST_TOOL_NAME
    description = (
        "Executa testes pytest do workspace de forma controlada "
        "(subprocesso sem shell, sandbox, timeout, saída estruturada)."
    )
    required_permission = PermissionLevel.TERMINAL
    operation = RUN_PYTEST_OPERATION

    def __init__(
        self,
        sandbox: WorkspaceSandbox,
        audit: FilesystemAudit | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._audit = audit

    # ---------------------------------------------------------------- input
    def _validated_input(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Valida/clampeia os parâmetros — qualquer problema vira erro."""
        raw_path = kwargs.get("path", DEFAULT_PATH)
        if raw_path is None:
            raw_path = DEFAULT_PATH
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(
                "Parâmetro 'path' deve ser texto não vazio (caminho relativo "
                "ao workspace, ex.: 'tests')."
            )
        if _has_control_chars(raw_path):
            raise ValueError("Parâmetro 'path' contém caracteres de controle.")
        if Path(raw_path).is_absolute() or _DRIVE_ABSOLUTE.match(raw_path):
            raise ValueError(
                "Parâmetro 'path' deve ser RELATIVO ao workspace "
                f"(recebido caminho absoluto: {raw_path!r})."
            )
        if ".." in re.split(r"[\\/]+", raw_path):
            raise ValueError(
                "Parâmetro 'path' não pode conter '..' "
                "(traversal bloqueado)."
            )

        keyword = kwargs.get("k")
        if keyword is not None:
            if not isinstance(keyword, str) or not _KEYWORD_ALLOWED.match(keyword):
                raise ValueError(
                    "Parâmetro 'k' deve ser texto simples (letras, dígitos, "
                    "'_', espaço, '-', '.'; até 100 chars) — expressões "
                    "compostas não são suportadas."
                )

        maxfail = kwargs.get("maxfail", DEFAULT_MAXFAIL)
        if maxfail is None:
            maxfail = DEFAULT_MAXFAIL
        if isinstance(maxfail, bool) or not isinstance(maxfail, int):
            raise ValueError("Parâmetro 'maxfail' deve ser inteiro (1..10).")
        maxfail = max(MAXFAIL_MIN, min(MAXFAIL_MAX, maxfail))

        timeout_s = kwargs.get("timeout_s", DEFAULT_TIMEOUT_S)
        if timeout_s is None:
            timeout_s = DEFAULT_TIMEOUT_S
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, int):
            raise ValueError("Parâmetro 'timeout_s' deve ser inteiro (10..600).")
        timeout_s = max(TIMEOUT_MIN_S, min(TIMEOUT_MAX_S, timeout_s))

        return {"path": raw_path, "k": keyword, "maxfail": maxfail,
                "timeout_s": timeout_s}

    # ------------------------------------------------------------- execução
    def run(self, **kwargs: Any) -> ToolResult:
        base: dict[str, Any] = {"operation": self.operation}
        try:
            params = self._validated_input(kwargs)
        except ValueError as exc:
            logger.warning("run_pytest: input inválido: %s", exc)
            self._audit_record(None, None, success=False, error=str(exc),
                               command=None)
            return ToolResult(ok=False, data=base, error=str(exc))

        requested = params["path"]
        try:
            resolved = self._sandbox.resolve(requested)
            cwd = next(
                (r for r in self._sandbox.roots if resolved.is_relative_to(r)),
                self._sandbox.roots[0],
            )
        except FilesystemError as exc:
            logger.warning("run_pytest: path bloqueado pelo sandbox: %s", exc)
            self._audit_record(requested, None, success=False, error=str(exc),
                               command=None)
            return ToolResult(
                ok=False,
                data={**base, "requested_path": requested},
                error=str(exc),
            )

        basetemp = Path(tempfile.mkdtemp(prefix="lumen-pytest-"))
        argv: list[str] = [
            sys.executable, "-m", "pytest",
            "-q",
            f"--maxfail={params['maxfail']}",
            "-p", "no:cacheprovider",
            "--basetemp", str(basetemp),
        ]
        if params["k"] is not None:
            argv += ["-k", params["k"]]
        argv.append(str(resolved))
        env = dict(build_safe_environment())
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPYCACHEPREFIX"] = str(basetemp / "pycache")

        started = time.monotonic()
        try:
            outcome = self._execute(argv, cwd, env, params["timeout_s"])
        except OSError as exc:
            error = f"Falha ao executar o subprocesso de testes: {exc}"
            logger.error("run_pytest: %s", error)
            self._audit_record(requested, str(resolved), success=False,
                               error=error, command=argv)
            return ToolResult(
                ok=False,
                data={**base, "requested_path": requested,
                      "resolved_path": str(resolved)},
                error=error,
            )
        finally:
            shutil.rmtree(basetemp, ignore_errors=True)

        duration_s = round(time.monotonic() - started, 3)
        output = outcome["output"]
        data: dict[str, Any] = {
            **base,
            "requested_path": requested,
            "resolved_path": str(resolved),
            "command": argv,
            "exit_code": outcome["exit_code"],
            "duration_s": duration_s,
            "summary_line": self._summary_line(output),
            "output_head": output[:HEAD_CHARS],
            "output_tail": output[-TAIL_CHARS:] if len(output) > HEAD_CHARS else "",
            "truncated": outcome["truncated"],
            "timed_out": outcome["timed_out"],
            "maxfail": params["maxfail"],
            "timeout_s": params["timeout_s"],
        }

        if outcome["timed_out"]:
            error = (
                f"Pytest excedeu o timeout de {params['timeout_s']}s e foi "
                "encerrado (nenhum resultado válido)."
            )
            logger.warning("run_pytest: %s", error)
            self._audit_record(requested, str(resolved), success=False,
                               error=error, command=argv,
                               exit_code=outcome["exit_code"],
                               duration_ms=int(duration_s * 1000), timed_out=True)
            return ToolResult(ok=False, data=data, error=error)

        # pytest RODOU (exit_code != 0 = testes falharam/nada coletado):
        # ok=True — a evidência (exit_code/summary) vai na data.
        audit_extra: dict[str, Any] = {
            "command": argv,
            "exit_code": outcome["exit_code"],
            "duration_ms": int(duration_s * 1000),
        }
        if outcome["truncated"]:
            audit_extra["truncated"] = True
        self._audit_record(requested, str(resolved), success=True,
                           **audit_extra)
        return ToolResult(ok=True, data=data)

    # ------------------------------------------------------------ subprocesso
    def _execute(
        self, argv: list[str], cwd: Path, env: dict[str, str], timeout_s: int
    ) -> dict[str, Any]:
        """Roda o subprocesso com teto de bytes na saída combinada."""
        process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # combinada, conforme o contrato
            stdin=subprocess.DEVNULL,
            env=env,
            shell=False,
        )
        buffer = bytearray()
        state = {"truncated": False}

        def _read() -> None:
            assert process.stdout is not None
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    return
                if len(buffer) < MAX_OUTPUT_BYTES:
                    room = MAX_OUTPUT_BYTES - len(buffer)
                    buffer.extend(chunk[:room])
                    if len(chunk) > room:
                        state["truncated"] = True
                else:
                    state["truncated"] = True

        reader = threading.Thread(target=_read, daemon=True)
        reader.start()
        timed_out = False
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover
                logger.error("run_pytest: processo não terminou após kill.")
        reader.join(timeout=5)
        return {
            "exit_code": process.returncode,
            "output": buffer.decode("utf-8", errors="replace"),
            "truncated": state["truncated"],
            "timed_out": timed_out,
        }

    @staticmethod
    def _summary_line(output: str) -> str | None:
        """Última linha de resumo do pytest (``N passed, ...``)."""
        for line in reversed(output.splitlines()):
            stripped = line.strip()
            if stripped and _SUMMARY_LINE.search(stripped):
                return stripped[:500]
        return None

    # --------------------------------------------------------------- auditoria
    def _audit_record(
        self, requested: Any, resolved: str | None, *, success: bool,
        error: str | None = None, command: list[str] | None = None,
        exit_code: int | None = None, duration_ms: int | None = None,
        **extra: Any,
    ) -> None:
        """Auditoria sem conteúdo de saída nem segredos (padrão terminal)."""
        if self._audit is None:
            return
        self._audit.record(
            tool=self.name,
            operation=self.operation,
            requested_path=requested if isinstance(requested, str) else None,
            resolved_path=resolved,
            success=success,
            error=error,
            command=command,
            exit_code=exit_code,
            duration_ms=duration_ms,
            **extra,
        )
