"""ExecutionBundleStore — persistência sanitizada do Execution State (9B).

Observabilidade/rastreabilidade e recuperação estruturada: quando um plano atinge estado
terminal, um "bundle" JSON (metadados + plano + relatório de execução +
correções + registros individuais de execução) é sanitizado e gravado com escrita atômica.

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
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
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


class ExecutionState(str, Enum):
    """Estados estruturados de execução (Fase B)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ExecutionRecordEntry:
    """Modelo de registro individual de execução de ferramenta/tarefa."""

    execution_id: str
    conversation_id: str | None = None
    task_id: str | None = None
    parent_execution_id: str | None = None
    tool_name: str | None = None
    tool_version: str | None = None
    requested_action: str | None = None
    arguments: dict[str, Any] | None = None
    started_at: str | None = None
    completed_at: str | None = None
    status: ExecutionState = ExecutionState.UNKNOWN
    result: Any = None
    error: str | None = None
    verification: dict[str, Any] | None = None
    workspace: str | None = None
    evidence: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "conversation_id": self.conversation_id,
            "task_id": self.task_id,
            "parent_execution_id": self.parent_execution_id,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "requested_action": self.requested_action,
            "arguments": self.arguments,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": (
                self.status.value
                if isinstance(self.status, ExecutionState)
                else str(self.status)
            ),
            "result": self.result,
            "error": self.error,
            "verification": self.verification,
            "workspace": self.workspace,
            "evidence": self.evidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


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
            "ok" in sanitized
            and "data" in sanitized
            and isinstance(sanitized.get("data"), dict)
        ):
            for field_name in _FORBIDDEN_RESULT_FIELDS:
                sanitized["data"].pop(field_name, None)
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


def _map_task_status_to_execution_state(
    status_val: str, verified: bool | None
) -> ExecutionState:
    """Mapeia status de task e resultado de verificação para ExecutionState."""
    status_str = str(status_val).upper()
    if status_str == "DONE":
        if verified is False:
            return ExecutionState.VERIFICATION_FAILED
        return ExecutionState.SUCCEEDED
    if status_str in ("FAILED", "REJECTED"):
        return ExecutionState.FAILED
    if status_str == "RUNNING":
        return ExecutionState.RUNNING
    if status_str == "PENDING":
        return ExecutionState.PENDING
    if status_str == "SKIPPED":
        return ExecutionState.CANCELLED
    return ExecutionState.UNKNOWN


# ------------------------------------------------------------------ store
class ExecutionBundleStore:
    """Grava e recupera bundles de execução sanitizados em ``base_dir`` (atômico)."""

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
        conversation_id: str | None = None,
        workspace: str | None = None,
    ) -> Path:
        """Sanitiza e grava o bundle; devolve o caminho gravado."""
        report_dict = _serialize(report)
        plan_dict = _serialize(plan)
        plan_id = sanitize_any(
            str(getattr(report, "plan_id", getattr(plan, "id", ""))), self._limit
        )

        effective_conv_id = sanitize_any(
            str(
                conversation_id
                or getattr(report, "conversation_id", None)
                or getattr(plan, "conversation_id", "")
                or ""
            ),
            self._limit,
        )
        effective_workspace = sanitize_any(
            str(
                workspace
                or getattr(report, "workspace", None)
                or getattr(plan, "workspace", "")
                or ""
            ),
            self._limit,
        )

        tasks_dict = []
        execution_records = []

        # Mapeamento das tasks do plano para catálogo de ferramentas
        tasks_map = {}
        if isinstance(plan_dict, dict) and isinstance(plan_dict.get("tasks"), list):
            for ptask in plan_dict["tasks"]:
                if isinstance(ptask, dict) and "id" in ptask:
                    tasks_map[ptask["id"]] = ptask

        if isinstance(report_dict, dict):
            for task in report_dict.get("tasks", []) or []:
                if isinstance(task, dict):
                    raw_res = task.get("result")
                    if isinstance(raw_res, str):
                        task["result"] = sanitize_result_string(
                            raw_res, self._limit
                        )
                    tasks_dict.append(task)

                    # Constrói o ExecutionRecordEntry estruturado para cada task
                    t_id = str(task.get("id", "T1"))
                    exec_id = f"EXEC-{plan_id}-{t_id}"
                    planned_info = tasks_map.get(t_id, {})
                    tool_name = planned_info.get("tool") or task.get("tool")
                    args = planned_info.get("parameters") or task.get("parameters") or {}

                    t_status = task.get("status", "UNKNOWN")
                    verified = task.get("verified")
                    state = _map_task_status_to_execution_state(t_status, verified)

                    parsed_result = None
                    if isinstance(task.get("result"), str):
                        try:
                            parsed_result = json.loads(task["result"])
                        except Exception:
                            parsed_result = task["result"]

                    rec = ExecutionRecordEntry(
                        execution_id=exec_id,
                        conversation_id=effective_conv_id or None,
                        task_id=t_id,
                        parent_execution_id=None,
                        tool_name=tool_name,
                        tool_version=None,
                        requested_action=planned_info.get("description") or task.get("description"),
                        arguments=sanitize_any(args, self._limit) if isinstance(args, dict) else {},
                        started_at=getattr(report, "started_at", None),
                        completed_at=getattr(report, "finished_at", None),
                        status=state,
                        result=parsed_result,
                        error=sanitize_any(task.get("error"), self._limit) if task.get("error") else None,
                        verification={
                            "verified": verified,
                            "error": task.get("error") if verified is False else None,
                        },
                        workspace=effective_workspace or None,
                        evidence=[],
                    )
                    execution_records.append(rec.to_dict())

        bundle = {
            "version": BUNDLE_VERSION,
            "lumen_version": sanitize_any(str(lumen_version), self._limit),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "plan_id": plan_id,
            "conversation_id": effective_conv_id,
            "workspace": effective_workspace,
            "plan": sanitize_any(plan_dict, self._limit),
            "execution_report": sanitize_any(report_dict, self._limit),
            "execution_records": sanitize_any(execution_records, self._limit),
            "correction": (
                sanitize_any(_serialize(correction), self._limit)
                if correction
                else None
            ),
        }

        safe_name = (
            re.sub(r"[^A-Za-z0-9._-]", "_", str(plan_id))
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

    def load_bundle(self, plan_id: str) -> dict[str, Any] | None:
        """Carrega o bundle salvo correspondente ao plan_id."""
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", str(plan_id)) or "plano"
        path = self._base_dir / f"{safe_name}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Falha ao ler bundle em %s: %s", path, exc)
            return None

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        """Busca uma execução individual por execution_id através de todos os bundles."""
        if not self._base_dir.exists():
            return None
        for file_path in self._base_dir.glob("*.json"):
            try:
                bundle = json.loads(file_path.read_text(encoding="utf-8"))
                records = bundle.get("execution_records", [])
                if isinstance(records, list):
                    for rec in records:
                        if isinstance(rec, dict) and rec.get("execution_id") == execution_id:
                            return rec
            except Exception:
                continue
        return None

    def query_executions(
        self,
        conversation_id: str | None = None,
        task_id: str | None = None,
        workspace: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Consulta execuções filtrando por conversa, task e/ou workspace."""
        if not self._base_dir.exists():
            return []
        matches: list[dict[str, Any]] = []
        for file_path in sorted(
            self._base_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                bundle = json.loads(file_path.read_text(encoding="utf-8"))
                records = bundle.get("execution_records", [])
                b_conv = bundle.get("conversation_id")
                b_ws = bundle.get("workspace")
                if isinstance(records, list):
                    for rec in records:
                        if not isinstance(rec, dict):
                            continue
                        if conversation_id is not None:
                            rec_conv = rec.get("conversation_id") or b_conv
                            if rec_conv != conversation_id:
                                continue
                        if task_id is not None and rec.get("task_id") != task_id:
                            continue
                        if workspace is not None:
                            rec_ws = rec.get("workspace") or b_ws
                            if rec_ws != workspace:
                                continue
                        matches.append(rec)
                        if len(matches) >= limit:
                            return matches
            except Exception:
                continue
        return matches
