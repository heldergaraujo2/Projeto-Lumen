"""EditFileTool — edição cirúrgica de arquivo do workspace (11C).

**Estado (11C, parte 2/5): implementada e NÃO REGISTRADA.** Esta tool
não é construída por nenhum factory nem exposta em catálogo — está
inalcançável pelo ``ToolRegistry`` até que o wiring seja autorizado
(registro em ``build_filesystem_registry`` + ``FILESYSTEM_TOOLS`` +
``FILESYSTEM_DESTRUCTIVE_TOOLS`` e, se decidido, o Planner Catalog).
Ver ``docs/SPEC-11C-EDIT_FILE.md`` (DRAFT / NÃO AUTORIZADA).

Contrato (spec §3): substitui **exatamente uma** ocorrência literal de
``expected_old_text`` por ``new_text`` — nunca reescreve "a primeira que
achar" e nunca edita parcialmente quando a validação falha:

- 0 ocorrências  ⇒ erro claro ``NO_MATCH`` (nada é escrito);
- ≥2 ocorrências (inclusive sobrepostas) ⇒ ``MULTIPLE_MATCHES`` (nada
  é escrito);
- binário (byte NUL ou UTF-8 inválido) ou arquivo acima do limite ⇒
  recusa (nada é escrito).

Segurança: mesmíssima coleira das tools de filesystem — permissão
``WRITE`` aportada pelo ``ToolRegistry``, ``resolve()`` +
``check_operation("write")`` no sandbox antes de qualquer toque no
arquivo, auditoria com metadados (JAMAIS conteúdo). A escrita segue o
padrão do projeto (``write_text`` UTF-8, como ``WriteFileTool`` — não
existe helper de escrita atômica nesta base); o teto de tamanho e o
parâmetro ``max_bytes`` espelham ``ReadFileTool`` (1 MiB default).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.security.permissions import PermissionLevel
from app.tools.filesystem import OPERATION_WRITE, FilesystemError, FilesystemTool


class EditFileTool(FilesystemTool):
    """Edita um trecho único de um arquivo de texto do workspace (WRITE)."""

    name = "edit_file"
    description = (
        "Edita um arquivo do workspace substituindo um trecho literal "
        "único (edição cirúrgica, sem reescrever o arquivo inteiro)."
    )
    required_permission = PermissionLevel.WRITE
    operation = OPERATION_WRITE

    #: Teto de tamanho editável — mesmo limite/padrão de ``read_file``.
    DEFAULT_MAX_BYTES = 1_000_000

    # ---------------------------------------------------------------- API
    def _perform(self, resolved: Path, **kwargs: Any) -> dict[str, Any]:
        old_text = kwargs.get("expected_old_text")
        if not isinstance(old_text, str) or not old_text:
            raise FilesystemError(
                "Parâmetro 'expected_old_text' é obrigatório e deve ser "
                "texto não vazio (trecho literal, sem regex)."
            )
        new_text = kwargs.get("new_text")
        if not isinstance(new_text, str) or not new_text:
            # 11C: requisito vigente = não vazia (remoção de trecho é
            # questão aberta na spec §9.6 — decidir antes do wiring).
            raise FilesystemError(
                "Parâmetro 'new_text' é obrigatório e deve ser texto não "
                "vazio (use delete_file para remover arquivos)."
            )
        max_bytes = kwargs.get("max_bytes", self.DEFAULT_MAX_BYTES)
        if (
            not isinstance(max_bytes, int) or isinstance(max_bytes, bool)
            or max_bytes <= 0
        ):
            raise FilesystemError(
                "Parâmetro 'max_bytes' deve ser um inteiro positivo."
            )

        if not resolved.exists():
            raise FilesystemError(f"Arquivo não existe: {resolved}")
        if resolved.is_dir():
            raise FilesystemError(
                f"O caminho é um diretório (não um arquivo): {resolved}"
            )

        size = resolved.stat().st_size
        if size > max_bytes:
            raise FilesystemError(
                f"FILE_TOO_LARGE: arquivo grande demais ({size} bytes; "
                f"limite {max_bytes}). Ajuste 'max_bytes' se for intencional."
            )
        try:
            payload = resolved.read_bytes()
        except OSError as exc:
            raise FilesystemError(f"Erro de filesystem: {exc}") from exc
        if b"\x00" in payload:
            raise FilesystemError(
                f"BINARY_FILE: arquivo binário (byte NUL) não é editável: "
                f"{resolved}"
            )
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            raise FilesystemError(
                f"BINARY_FILE: o arquivo não é texto UTF-8 válido: {resolved}"
            ) from None

        # Ocorrência exatamente 1 — busca manual com sobreposição:
        # a 2ª procura começa em idx+1 (pega âncoras sobrepostas, ex.
        # "aa" em "aaa") e conta TODAS as ocorrências para a mensagem.
        index = text.find(old_text)
        if index == -1:
            raise FilesystemError(
                "NO_MATCH: o trecho esperado não foi encontrado no arquivo "
                f"({resolved}) — nada foi escrito."
            )
        occurrences = 1
        probe = text.find(old_text, index + 1)
        while probe != -1:
            occurrences += 1
            probe = text.find(old_text, probe + 1)
        if occurrences > 1:
            raise FilesystemError(
                f"MULTIPLE_MATCHES: o trecho aparece {occurrences} vezes em "
                f"{resolved} — torne a âncora única; nada foi escrito."
            )

        # Substituição exatamente na posição única encontrada
        # (não usar str.replace global).
        new_content = text[:index] + new_text + text[index + len(old_text):]
        bytes_before = len(payload)
        bytes_after = len(new_content.encode("utf-8"))
        resolved.write_text(new_content, encoding="utf-8", newline="")

        line = text.count("\n", 0, index) + 1
        column = index - (text.rfind("\n", 0, index) + 1) + 1
        return {
            # Vocabulário público da operação (a POLÍTICA/audit continuam
            # com "write" — self.operation — como nas demais tools).
            "operation": self.name,
            "written": True,
            "match_count": 1,
            "line": line,
            "col": column,
            "bytes_before": bytes_before,
            "bytes_after": bytes_after,
            "replaced_bytes": len(old_text.encode("utf-8")),
            "_audit": {
                "bytes_before": bytes_before,
                "bytes_after": bytes_after,
            },
        }


__all__ = ["EditFileTool"]
