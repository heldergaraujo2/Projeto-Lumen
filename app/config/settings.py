"""Configuração central da Lumen.

Lê variáveis do arquivo ``.env`` (na raiz do projeto) e do ambiente real
(este tem precedência), expõe caminhos resolvidos (dados, memória, logs)
e configura o logging da aplicação.

Segurança: nenhuma secret é registrada em log — ver
:class:`_SecretRedactionFilter`.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

#: Raiz do projeto (diretório que contém ``main.py``).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Arquivo de configuração opcional (veja ``.env.example``).
ENV_FILE = PROJECT_ROOT / ".env"

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

_MODULE_LOGGER = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Erro de configuração da aplicação."""


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parser mínimo de arquivos ``.env`` (sem dependências externas).

    Aceita ``CHAVE=valor``, ``export CHAVE=valor``, comentários com ``#``
    e valores entre aspas simples ou duplas.
    """
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            _MODULE_LOGGER.warning(".env:%d: linha ignorada (formato inválido): %r", line_no, raw_line)
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if not key:
            _MODULE_LOGGER.warning(".env:%d: chave vazia ignorada: %r", line_no, raw_line)
            continue
        values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    """Configurações da Lumen, imutáveis após o carregamento.

    Atributos:
        provider: nome do provedor de IA (``LUMEN_PROVIDER``; ``mock`` ou
            ``openai``).
        model: identificador de modelo (``LUMEN_MODEL``) — obrigatório
            para provedores reais.
        api_key: chave de API (``LUMEN_API_KEY``) — nunca vai para logs.
        data_dir: diretório de dados (``LUMEN_DATA_DIR``), absoluto ou
            relativo à raiz do projeto.
        log_level: nível de logging (``LUMEN_LOG_LEVEL``).
        max_context_messages: quantas mensagens de histórico o Agent envia
            ao provedor (``LUMEN_MAX_CONTEXT_MESSAGES``).
        request_timeout: timeout em segundos para chamadas ao provedor
            (``LUMEN_REQUEST_TIMEOUT``).
        max_retries: retries adicionais para erros temporários
            (``LUMEN_MAX_RETRIES``); 0 = tentativa única.
        max_memory_records: limite de registros de memória estruturada
            selecionados como contexto (``LUMEN_MAX_MEMORY_RECORDS``).
    """

    provider: str = "mock"
    model: str = ""
    api_key: str = ""
    data_dir: Path = PROJECT_ROOT / "data"
    log_level: str = "INFO"
    max_context_messages: int = 50
    request_timeout: float = 60.0
    max_retries: int = 2
    max_memory_records: int = 12
    #: 10B — guardrails do planejamento (exceder REJEITA o plano, nunca
    #: trunca silenciosamente nem executa parcialmente).
    planner_max_tasks: int = 12
    planner_max_dependency_depth: int = 6
    planner_max_text_field_bytes: int = 16 * 1024
    planner_max_dataflow_refs_per_param: int = 4
    #: 10B — Stage 2 do planejamento (refinador conservador, com fallback).
    planner_refine_enabled: bool = False
    #: 9B: persistência do Execution State (observabilidade) — OFF por padrão.
    persist_execution_state: bool = False
    #: 11I: export do relatório de evidências pós-execução
    #: (observabilidade) — OFF por padrão.
    export_execution_reports: bool = False

    def __post_init__(self) -> None:
        if self.log_level not in VALID_LOG_LEVELS:
            raise ConfigError(
                f"Nível de log inválido: {self.log_level!r}. "
                f"Use um de: {', '.join(sorted(VALID_LOG_LEVELS))}."
            )
        if not isinstance(self.max_context_messages, int) or self.max_context_messages < 1:
            raise ConfigError(
                "LUMEN_MAX_CONTEXT_MESSAGES deve ser um inteiro >= 1 "
                f"(recebido: {self.max_context_messages!r})."
            )
        if not isinstance(self.request_timeout, (int, float)) or self.request_timeout <= 0:
            raise ConfigError(
                "LUMEN_REQUEST_TIMEOUT deve ser um número > 0 em segundos "
                f"(recebido: {self.request_timeout!r})."
            )
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ConfigError(
                f"LUMEN_MAX_RETRIES deve ser um inteiro >= 0 (recebido: {self.max_retries!r})."
            )
        if not isinstance(self.max_memory_records, int) or self.max_memory_records < 1:
            raise ConfigError(
                "LUMEN_MAX_MEMORY_RECORDS deve ser um inteiro >= 1 "
                f"(recebido: {self.max_memory_records!r})."
            )
        for field_name in (
            "planner_max_tasks", "planner_max_dependency_depth",
            "planner_max_text_field_bytes", "planner_max_dataflow_refs_per_param",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value < 1:
                raise ConfigError(
                    f"{field_name} deve ser um inteiro >= 1 (recebido: {value!r})."
                )
        if not isinstance(self.planner_refine_enabled, bool):
            raise ConfigError("planner_refine_enabled deve ser booleano.")

    # ------------------------------------------------------- caminhos derivados
    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def memory_file(self) -> Path:
        return self.memory_dir / "conversation.json"

    @property
    def tasks_file(self) -> Path:
        return self.data_dir / "tasks.json"

    @property
    def execution_dir(self) -> Path:
        """Bundles de execução sanitizados (9B; só é escrito se habilitado)."""
        return self.data_dir / "executions"

    def ensure_dirs(self) -> None:
        """Cria os diretórios de dados (idempotente)."""
        for directory in (self.data_dir, self.memory_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------- carga
    @classmethod
    def load(
        cls,
        env_file: Path | str | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "Settings":
        """Carrega as configurações: o ambiente real vence o ``.env``.

        Args:
            env_file: caminho do arquivo ``.env`` (padrão: raiz do projeto).
            environ: ambiente alternativo (padrão: ``os.environ``) — útil
                para testes.
        """
        env_path = Path(env_file) if env_file is not None else ENV_FILE
        file_values = _parse_env_file(env_path)
        env = os.environ if environ is None else environ

        def pick(key: str, default: str) -> str:
            value = env.get(key)
            if value is None:
                value = file_values.get(key, default)
            return value

        data_dir_raw = pick("LUMEN_DATA_DIR", "data").strip() or "data"
        data_dir = Path(data_dir_raw).expanduser()
        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir

        def pick_number(key: str, default: str, cast: type) -> float | int:
            raw = pick(key, default).strip() or default
            try:
                return cast(raw)
            except ValueError:
                friendly = cast.__name__ if cast is not float else "número"
                raise ConfigError(
                    f"{key} deve ser um {friendly} válido (recebido: {raw!r})."
                ) from None

        return cls(
            provider=(pick("LUMEN_PROVIDER", "mock").strip().lower() or "mock"),
            model=pick("LUMEN_MODEL", "").strip(),
            api_key=pick("LUMEN_API_KEY", "").strip(),
            data_dir=data_dir,
            log_level=(pick("LUMEN_LOG_LEVEL", "INFO").strip().upper() or "INFO"),
            max_context_messages=int(pick_number("LUMEN_MAX_CONTEXT_MESSAGES", "50", int)),
            request_timeout=float(pick_number("LUMEN_REQUEST_TIMEOUT", "60", float)),
            max_retries=int(pick_number("LUMEN_MAX_RETRIES", "2", int)),
            max_memory_records=int(pick_number("LUMEN_MAX_MEMORY_RECORDS", "12", int)),
            planner_max_tasks=int(pick_number("LUMEN_PLANNER_MAX_TASKS", "12", int)),
            planner_max_dependency_depth=int(
                pick_number("LUMEN_PLANNER_MAX_DEPENDENCY_DEPTH", "6", int)
            ),
            planner_max_text_field_bytes=int(
                pick_number("LUMEN_PLANNER_MAX_TEXT_FIELD_BYTES", str(16 * 1024), int)
            ),
            planner_max_dataflow_refs_per_param=int(
                pick_number("LUMEN_PLANNER_MAX_DATAFLOW_REFS_PER_PARAM", "4", int)
            ),
            planner_refine_enabled=(
                pick("LUMEN_PLANNER_REFINE", "0").strip().lower()
                in ("1", "true", "yes", "sim", "on")
            ),
            export_execution_reports=(
                pick("LUMEN_EXPORT_EXECUTION_REPORTS", "0").strip().lower()
                in ("1", "true", "yes", "sim", "on")
            ),
        )


# --------------------------------------------------------------------- logging
_TOKEN_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{6,}"),                      # chaves estilo OpenAI
    re.compile(r"(?i)(api[_\-]?key\s*[:=]\s*)\S+"),            # "api_key=..." explícito
)


class _SecretRedactionFilter(logging.Filter):
    """Impede que segredos (ex.: API keys) cheguem aos logs."""

    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - registro malformado
            return True

        redacted = message
        for secret in self._secrets:
            redacted = redacted.replace(secret, "***")
        redacted = _TOKEN_PATTERNS[0].sub("***", redacted)
        redacted = _TOKEN_PATTERNS[1].sub(r"\1***", redacted)

        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def setup_logging(settings: Settings) -> None:
    """Configura o logger da aplicação.

    Console + arquivo rotativo em ``data/logs/lumen.log`` (1 MB × 3
    backups). Todo o tráfego fica sob o namespace ``lumen``.
    """
    settings.ensure_dirs()

    logger = logging.getLogger("lumen")
    logger.setLevel(settings.log_level)
    logger.propagate = False

    for handler in list(logger.handlers):  # reconfiguração segura
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-16s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redaction = _SecretRedactionFilter((settings.api_key,))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redaction)

    file_handler = RotatingFileHandler(
        settings.logs_dir / "lumen.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
