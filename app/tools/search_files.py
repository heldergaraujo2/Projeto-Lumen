"""SearchFilesTool — busca textual somente-leitura no workspace (11B).

Busca **literal** (sem regex) de um texto nos arquivos do workspace
autorizado, com resultado estruturado (:class:`ToolResult.data`).

Segurança (mesma coleira das ferramentas de filesystem):
- permissão ``READ`` exigida pelo porteio do ``ToolRegistry``;
- caminho resolvido pelo **sandbox** do workspace: ``..`` e caminhos
  absolutos fora do workspace são bloqueados antes de qualquer leitura;
- symlinks que resolvem para **fora** do workspace NUNCA são seguidos
  (arquivo ou diretório): ``os.walk(followlinks=False)`` + confinamento
  ``resolve()`` por arquivo candidato;
- somente leitura: nada é criado/editado/removido; nenhum subprocesso;
  nenhuma outra ferramenta é chamada internamente.

Anti-DoS (defaults clampados — o chamador só pode **reduzir**):
- ``DEFAULT_MAX_FILES = 200`` (arquivos examinados por busca);
- ``DEFAULT_MAX_FILE_BYTES = 256 * 1024`` (arquivos maiores são pulados);
- ``DEFAULT_MAX_MATCHES = 200`` (correspondências devolvidas);
- ``DEFAULT_SNIPPET_BYTES = 200`` (trechos/linhas truncados em bytes).

Binários (byte ``\\x00`` ou UTF-8 inválido) e arquivos grandes são
**pulados** e contabilizados em ``skipped`` — nunca decodificados à força.

Schema estável de ``ToolResult.data``::
    operation, requested_path, resolved_path, query, files_scanned,
    matches_returned, truncated,
    matches[{path, line, col, line_text, snippet}],
    skipped{binary, too_large, errors}
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.security.permissions import PermissionLevel
from app.tools.filesystem import (
    OPERATION_READ,
    FilesystemError,
    FilesystemTool,
)

logger = logging.getLogger("lumen.tools.search_files")


class SearchFilesTool(FilesystemTool):
    """Busca textual literal nos arquivos do workspace (permissão READ)."""

    name = "search_files"
    description = (
        "Busca um texto (literal, sem regex) nos arquivos do workspace e "
        "devolve correspondências com arquivo, linha, coluna e trecho."
    )
    required_permission = PermissionLevel.READ
    operation = OPERATION_READ

    #: Anti-DoS (11B): tetos padrão — parâmetros do chamador são
    #: validados e clampados para no máximo estes valores.
    DEFAULT_MAX_FILES = 200
    DEFAULT_MAX_FILE_BYTES = 256 * 1024
    DEFAULT_MAX_MATCHES = 200
    DEFAULT_SNIPPET_BYTES = 200

    # ---------------------------------------------------------------- API
    def _perform(self, resolved: Path, **kwargs: Any) -> dict[str, Any]:
        query = kwargs.get("query")
        if not isinstance(query, str) or not query:
            raise FilesystemError(
                "Parâmetro 'query' é obrigatório (texto não vazio)."
            )
        max_files = self._limit(
            kwargs.get("max_files"), self.DEFAULT_MAX_FILES, "max_files"
        )
        max_file_bytes = self._limit(
            kwargs.get("max_file_bytes"), self.DEFAULT_MAX_FILE_BYTES,
            "max_file_bytes",
        )
        max_matches = self._limit(
            kwargs.get("max_matches"), self.DEFAULT_MAX_MATCHES, "max_matches"
        )
        snippet_bytes = self._limit(
            kwargs.get("snippet_bytes"), self.DEFAULT_SNIPPET_BYTES,
            "snippet_bytes",
        )

        if not resolved.exists():
            raise FilesystemError(f"Caminho não existe: {resolved}")
        if not resolved.is_dir():
            raise FilesystemError(
                f"O caminho de busca deve ser um diretório: {resolved}"
            )

        root = resolved
        matches: list[dict[str, Any]] = []
        files_scanned = 0
        skipped_binary = 0
        skipped_too_large = 0
        errors = 0
        truncated = False
        stop = False

        # followlinks=False: nunca desce por symlinks de diretório.
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            for filename in sorted(filenames):
                if files_scanned >= max_files:
                    truncated = True
                    stop = True
                    break
                candidate = Path(dirpath) / filename
                try:
                    if not candidate.is_file():
                        continue  # symlink quebrado, fifo, dispositivo…
                    # Confinamento: o destino real do candidato tem de
                    # continuar dentro do workspace (bloqueia escape por
                    # symlink de arquivo).
                    real = candidate.resolve(strict=True)
                    real.relative_to(root)
                except (OSError, ValueError):
                    continue  # fora do workspace/inacessível: pula
                files_scanned += 1
                try:
                    if candidate.stat().st_size > max_file_bytes:
                        skipped_too_large += 1
                        continue
                    with candidate.open("rb") as handle:
                        payload = handle.read(max_file_bytes + 1)
                except OSError:
                    errors += 1
                    continue
                if len(payload) > max_file_bytes:
                    skipped_too_large += 1
                    continue
                if b"\x00" in payload:
                    skipped_binary += 1
                    continue
                try:
                    text = payload.decode("utf-8")
                except UnicodeDecodeError:
                    skipped_binary += 1
                    continue
                if self._collect_matches(
                    text, candidate, root, query,
                    max_matches, snippet_bytes, matches,
                ):
                    truncated = True
                    stop = True
                    break
            if stop:
                break

        return {
            # 11B: o schema público exige operation="search_files" (o
            # ``self.operation`` ("read") é o vocabulário da POLÍTICA do
            # sandbox/auditoria e permanece intacto para check_operation).
            "operation": self.name,
            "query": query,
            "files_scanned": files_scanned,
            "matches_returned": len(matches),
            "truncated": truncated,
            "matches": matches,
            "skipped": {
                "binary": skipped_binary,
                "too_large": skipped_too_large,
                "errors": errors,
            },
            "_audit": {
                "files_scanned": files_scanned,
                "matches_returned": len(matches),
            },
        }

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _limit(value: Any, ceiling: int, name: str) -> int:
        """Valida/clampa um parâmetro de limite (anti-DoS).

        ``None`` ⇒ default (teto). Inteiros < 1 são erro; valores acima do
        teto são reduzidos ao teto — o chamador só pode **reduzir**.
        """
        if value is None:
            return ceiling
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise FilesystemError(
                f"Parâmetro '{name}' deve ser um inteiro >= 1."
            )
        return min(value, ceiling)

    @staticmethod
    def _clip_bytes(text: str, limit: int) -> str:
        """Trunca ``text`` em ``limit`` bytes UTF-8 (sem quebrar encoding)."""
        raw = text.encode("utf-8")
        if len(raw) <= limit:
            return text
        return raw[:limit].decode("utf-8", errors="ignore")

    @classmethod
    def _collect_matches(
        cls,
        text: str,
        candidate: Path,
        root: Path,
        query: str,
        max_matches: int,
        snippet_bytes: int,
        matches: list[dict[str, Any]],
    ) -> bool:
        """Coleta correspondências literais; ``True`` quando a cota enche."""
        relative = str(candidate.relative_to(root))
        half = max(0, snippet_bytes // 2 - len(query))
        for lineno, line in enumerate(text.splitlines(), start=1):
            start = line.find(query)
            while start != -1:
                if len(matches) >= max_matches:
                    return True
                window = line[max(0, start - half):start + len(query) + half]
                matches.append({
                    "path": relative,
                    "line": lineno,
                    "col": start + 1,
                    "line_text": cls._clip_bytes(line, snippet_bytes),
                    "snippet": cls._clip_bytes(window, snippet_bytes),
                })
                start = line.find(query, start + len(query))
        return False
