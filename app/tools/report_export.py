"""11I — export de relatório de evidências pós-execução (funções puras).

Módulo de **montagem + escrita** do relatório estruturado de evidências
(11I): o payload combina estruturas que JÁ existem — ``Plan.to_dict()``,
``ExecutionReport.to_dict()``, ``correction_history()`` e a auditoria
JSONL correlacionada por ``plan_id`` — sem nenhuma nova coleta
(ver ``docs/SPEC-11I-REPORT_EXPORT.md``).

Princípios (normativos — spec 11I §4):

* **Não executa nada:** sem ``subprocess``/shell/tool — apenas leitura de
  estruturas passadas por argumento e escrita de um arquivo JSON.
* **Não toca permissões:** nenhum level do ``PermissionManager`` é
  lido/alterado; o export é observabilidade.
* **Sanitização obrigatória:** o payload exportado é SEMPRE o resultado de
  ``sanitize_any`` (``app/memory/execution_store.py`` — redige segredos,
  trunca strings no limite, remove ``stdout``/``stderr``/``content`` de
  dicts com shape de ``ToolResult``).
* **Falha de escrita é controlada:** :class:`ReportExportError` para o
  chamador decidir — o hook no controller (11I) trata como best-effort
  (log + execução segue inalterada).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.memory.execution_store import sanitize_any

logger = logging.getLogger("lumen.tools.report_export")

#: Versão do schema do relatório (política de migração de versões futuras:
#: TBD — spec 11I §7).
REPORT_VERSION = 1

#: Limite de strings exportadas (mesmo limite dos bundles 9B).
DEFAULT_STRING_LIMIT = 16 * 1024


class ReportExportError(RuntimeError):
    """Falha de escrita da persistência do relatório (disco/permisões)."""


def build_export_payload(
    plan: Any,
    report: Any,
    correction_history: list[dict] | None = None,
    audit_records: list[dict] | None = None,
    lumen_version: str = "",
    *,
    string_limit: int = DEFAULT_STRING_LIMIT,
) -> dict:
    """Monta o payload do relatório 11I (pura — sem E/S, sem execução).

    Args:
        plan: ``Plan`` (serializado via ``to_dict()`` — original imutável).
        report: ``ExecutionReport`` (serializado via ``to_dict()`` —
            tasks/eventos/checkpoints/pending_checkpoint).
        correction_history: ciclos de correção do controller
            (``list[dict]``) ou ``None``/vazio (sem correção).
        audit_records: registros de auditoria **já filtrados por
            ``plan_id``** (o chamador aplica o filtro via
            ``read_audit_tail`` + ``plan_id``) ou ``None``.
        lumen_version: versão da Lumen que gera o relatório.
        string_limit: teto de bytes por string (default 16 KiB).

    Returns:
        Dict **sanitizado** (``sanitize_any``) no shape::

            {"version": 1,
             "lumen_version": str,
             "exported_at": str (ISO8601, UTC),
             "plan": dict,
             "execution_report": dict,
             "correction_history": [dict, ...],
             "audit": [dict, ...]}
    """
    payload = {
        "version": REPORT_VERSION,
        "lumen_version": str(lumen_version),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "plan": plan.to_dict(),
        "execution_report": report.to_dict(),
        "correction_history": list(correction_history or []),
        "audit": list(audit_records or []),
    }
    return sanitize_any(payload, string_limit)


def export_execution_report(path: Path, payload: dict) -> Path:
    """Grava o relatório (escrita atômica: tmp + ``os.replace``).

    Cria o diretório de destino se necessário — o diretório **só nasce no
    momento do export** (opt-in desligado ⇒ nenhum efeito no disco). JSON
    com ``indent=2`` e ``ensure_ascii=False``.

    Args:
        path: destino completo (ex.: ``<reports_dir>/<plan_id>.json``).
        payload: dict já sanitizado (:func:`build_export_payload`).

    Raises:
        ReportExportError: falha de disco/OS na escrita (o chamador decide —
            o hook do controller trata como best-effort: log e segue).

    Returns:
        O caminho gravado.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, target)
    except OSError as exc:
        raise ReportExportError(
            f"Falha ao gravar o relatório de execução em {target}: {exc}"
        ) from exc
    logger.info("Relatório de execução exportado em %s.", target)
    return target
