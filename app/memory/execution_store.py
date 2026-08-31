"""ExecutionBundleStore — persistência sanitizada do Execution State (9B).

Observabilidade/rastreabilidade apenas: quando um plano atinge estado
terminal, um "bundle" JSON (metadados + plano + relatório de execução +
correções) é sanitizado e gravado com escrita atômica. NÃO existe resume
nem recuperação automática — o arquivo é um registro histórico.

Vive em :mod:`app.memory` (a camada de persistência da Lumen) para
manter o pacote ``app/executor`` livre de I/O real (contrato de
arquitetura guardado por testes).

Sanitização obrigatória antes de qualquer persistência:

- :func:`app.memory.sanitization.redact_secrets` em TODA string;
- truncamento de toda string a ``max_string_bytes`` (16 KiB default) —
  incluindo o ``TaskRun.result`` já re-serializado;
- ``stdout``/``stderr`` e o ``content`` integral de ``read_file`` são
  REMOVIDOS de qualquer resultado com shape ``{"ok","data","error"}``;
- ``TaskRun.result`` JSON: parse → sanitize → re-serializa; se não
  parsear, string redigida/truncada + marcador seguro;
- nada de permissões/autorizações reutilizáveis é gravado.

A persistência é **best-effort**: falha do sink jamais mascara o
resultado da execução (quem chama envolve em try/except).
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.memory.sanitization import redact_secrets

logger = logging.getLogger("lumen.memory.execution_store")

#: Versão do formato do bundle (evoluções futuras bumpam aqui).
BUNDLE_VERSION = 1

#: Marcador anexado a strings truncadas.
_TRUNCATION_MARKER = "…[truncado]"

#: Campos REMOVIDOS do payload ``data`` de resultados de ferramenta:
#: saídas de terminal (stdout/stderr) e conteúdo integral de arquivos.
_FORBIDDEN_RESULT_FIELDS: tuple[str, ...] = ("stdout", "stderr", "content")

#: Marcador para ``TaskRun.result`` que não é JSON válido (fallback seguro).
_UNPARSEABLE_MARKER = " <unparseable ToolResult>"


class ExecutionStoreError(RuntimeError):
    """Falha do armazenamento de estado de execução."""


# ------------------------------------------------------- funções puras (9B)
def _truncate(text: str, limit: int) -> str:
    """Corta a string em ``limit`` bytes UTF-8 (fronteira segura)."""
    marker_bytes = len(_TRUNCATION_MARKER.encode("utf-8"))
    if len(text.encode("utf-8")) <= limit:
        return text
    budget = max(0, limit - marker_bytes)
    encoded = text.encode("utf-8")[:budget]
    return encoded.decode("utf-8", errors="ignore") + _TRUNCATION_MARKER


def sanitize_any(value: Any, limit: int = 16 * 1024) -> Any:
    """Sanitização recursiva (pura): redige segredos e trunca strings.

    Dicionários com o shape de ``ToolResult`` (``ok``/``data``/``error``)
    têm ``data.stdout``/``data.stderr``/``data.content`` removidos.
    """
    if isinstance(value, str):
        redacted, _found = redact_secrets(value)
        return _truncate(redacted, limit)
    if isinstance(value, dict):
        sanitized = {
            sanitize_any(str(key), limit): sanitize_any(item, limit)
            for key, item in value.items()
        }
        if (
            {"ok", "data", "error"} <= set(sanitized)
            and isinstance(sanitized.get("data"), dict)
        ):
            for field in _FORBIDDEN_RESULT_FIELDS:
                sanitized["data"].pop(field, None)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [sanitize_any(item, limit) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    redacted, _found = redact_secrets(repr(value))
    return _truncate(redacted, limit)


def sanitize_result_string(raw: str, limit: int = 16 * 1024) -> str:
    """Sanitiza um ``TaskRun.result`` (string JSON do ``ToolResult``).

    JSON válido ⇒ sanitize (remove stdout/stderr/content, redige, trunca)
    e re-serializa (``ensure_ascii=False``), com truncamento final ao
    limite. JSON inválido ⇒ string redigida/truncada + marcador seguro.
    """
    try:
        payload = json.loads(raw)
    except ValueError:
        redacted, _found = redact_secrets(raw)
        return _truncate(redacted, limit) + _UNPARSEABLE_MARKER
    try:
        return _truncate(
            json.dumps(sanitize_any(payload, limit), ensure_ascii=False),
            limit,
        )
    except (TypeError, ValueError):  # pragma: no cover - defensivo
        redacted, _found = redact_secrets(raw)
        return _truncate(redacted, limit) + _UNPARSEABLE_MARKER


def _serialize(obj: Any) -> Any:
    """Converte um objeto para dict/list com prioridade to_dict → asdict."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, (dict, list, tuple)):
        return obj
    return repr(obj)


# ------------------------------------------------------------------ store
class ExecutionBundleStore:
    """Grava bundles de execução sanitizados em ``base_dir`` (atômico)."""

    def __init__(self, base_dir: Path | str, *, max_string_bytes: int = 16 * 1024) -> None:
        self._base_dir = Path(base_dir)
        self._limit = int(max_string_bytes)
        if self._limit < 1:
            raise ExecutionStoreError("max_string_bytes deve ser >= 1.")

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def max_string_bytes(self) -> int:
        return self._limit

    def save_bundle(
        self,
        *,
        plan: Any,
        report: Any,
        correction: Any | None = None,
        lumen_version: str = "",
    ) -> Path:
        """Sanitiza e grava o bundle; devolve o caminho gravado.

        O diretório só nasce no momento da gravação (persistência
        desligada ⇒ nenhum efeito no disco). Nada de permissões ou
        autorizações é incluído — o bundle é apenas observabilidade.
        """
        report_dict = _serialize(report)
        if isinstance(report_dict, dict):
            for task in report_dict.get("tasks", []) or []:
                if isinstance(task, dict) and isinstance(task.get("result"), str):
                    task["result"] = sanitize_result_string(
                        task["result"], self._limit,
                    )
        bundle = {
            "version": BUNDLE_VERSION,
            "lumen_version": sanitize_any(str(lumen_version), self._limit),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "plan_id": sanitize_any(str(getattr(report, "plan_id", "")), self._limit),
            "plan": sanitize_any(_serialize(plan), self._limit),
            "execution_report": sanitize_any(report_dict, self._limit),
            "correction": (
                sanitize_any(_serialize(correction), self._limit)
                if correction else None
            ),
        }
        safe_name = (
            re.sub(r"[^A-Za-z0-9._-]", "_", str(getattr(report, "plan_id", "")))
            or "plano"
        )
        path = self._base_dir / f"{safe_name}.json"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(bundle, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)  # escrita atômica
        except OSError as exc:
            raise ExecutionStoreError(
                f"Falha ao gravar o bundle de execução em {path}: {exc}"
            ) from exc
        logger.info("Bundle de execução salvo em %s.", path)
        return path
