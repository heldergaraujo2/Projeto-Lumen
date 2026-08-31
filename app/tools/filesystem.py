"""Ferramentas de filesystem da Lumen (0.5) — camada segura e auditável.

Primeira camada de **ferramentas reais**: operações de leitura e escrita
de arquivos, **sempre confinadas a um workspace explicitamente
autorizado** (:class:`WorkspaceSandbox`) e **sempre auditadas**
(:class:`FilesystemAudit`).

Modelo de segurança:

- **Sandbox por diretórios autorizados** — o construtor da política
  recebe a lista **explícita** de raízes permitidas; não existe acesso
  irrestrito ao computador nem ao Windows inteiro.
- **Caminhos**: rejeitados caminhos vazios/inválidos/com caracteres de
  controle, qualquer componente ``..`` (traversal) e tudo que, resolvido
  (incluindo symlinks), caia **fora** das raízes autorizadas. Caminhos
  absolutos são aceitos **apenas** se resolvem para dentro de uma raiz.
- **Modo da política**: somente leitura por padrão (``writable=False``);
  escrita exige opt-in explícito; exclusão exige ``allow_delete=True``
  **além de** ``writable`` (delete nunca é permitido por acidente).
- **Permissões** ( porteio do :class:`~app.tools.base.ToolRegistry`):
  leitura exige ``READ``; escrita/criação/exclusão exigem ``WRITE``.
  Sem a permissão, o código da ferramenta **não roda**.
- **Auditoria**: toda tentativa (sucesso, bloqueio ou erro) gera um
  :class:`AuditRecord` com ferramenta, operação, caminho solicitado,
  caminho resolvido, desfecho, erro, timestamp e a tarefa/plano de
  origem (quando disponível via contexto). Conteúdo de arquivos **não**
  é registrado — apenas metadados (tamanhos, contagens, flags).
- **Destrutivas**: ``write_file``/``create_file``/``delete_file`` são
  sinalizadas em :data:`FILESYSTEM_DESTRUCTIVE_TOOLS` para políticas de
  checkpoint/consentimento (ver :class:`app.tools.handler.ToolCheckpoints`).

Ferramentas implementadas: ``list_directory``, ``read_file``,
``write_file``, ``create_file``, ``delete_file``, ``file_exists``.

O que NÃO existe aqui (e continua proibido): execução de comandos,
terminal, subprocess, shell, PowerShell, mouse, teclado, captura de
tela, visão computacional, computer control, Unreal, acesso à rede.
"""
from __future__ import annotations

import logging
import threading
from abc import abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from app.security.permissions import PermissionLevel, PermissionManager
from app.tools.base import StructuredTool, ToolRegistry, ToolResult

logger = logging.getLogger("lumen.tools.filesystem")

#: Operações reconhecidas pela política do sandbox.
OPERATION_READ = "read"
OPERATION_WRITE = "write"
OPERATION_DELETE = "delete"

#: Ferramentas potencialmente destrutivas (mutam/apagam dados) —
#: candidatas naturais a checkpoint/consentimento do usuário.
FILESYSTEM_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {"write_file", "create_file", "delete_file", "edit_file"}
)

#: Ferramentas fornecidas por :func:`build_filesystem_registry`.
FILESYSTEM_TOOLS: tuple[str, ...] = (
    "list_directory",
    "read_file",
    "write_file",
    "create_file",
    "delete_file",
    "file_exists",
    "search_files",
    "edit_file",
)


class FilesystemError(Exception):
    """Falha/bloqueio de uma operação de filesystem (mensagem amigável)."""


class InvalidPathError(FilesystemError):
    """Caminho inválido (vazio, tipo errado, caracteres de controle…)."""


class PathOutsideWorkspaceError(FilesystemError):
    """Caminho fora das raízes autorizadas (inclui ``..``/traversal)."""


class WriteNotAllowedError(FilesystemError):
    """Escrita bloqueada: a política do sandbox é somente leitura."""


class DeleteNotAllowedError(FilesystemError):
    """Exclusão bloqueada: a política não habilita ``allow_delete``."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------- audit
@dataclass(frozen=True)
class AuditRecord:
    """Registro imutável de UMA tentativa de operação de filesystem.

    Conteúdo de arquivos **nunca** é armazenado — ``detail`` guarda
    apenas metadados (tamanhos, contagens, flags).
    """

    timestamp: str
    tool: str
    operation: str
    requested_path: str | None
    resolved_path: str | None
    success: bool
    error: str | None
    task_id: str | None = None
    plan_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "tool": self.tool,
            "operation": self.operation,
            "requested_path": self.requested_path,
            "resolved_path": self.resolved_path,
            "success": self.success,
            "error": self.error,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "detail": dict(self.detail),
        }


class FilesystemAudit:
    """Trilha de auditoria das operações de filesystem (thread-safe).

    Registros ficam em memória; um ``sink`` opcional (callable que
    recebe o dict de cada registro) permite persistência futura
    (ex.: JSONL em ``data/``) sem mudar o contrato.
    """

    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._sink = sink
        self._records: list[AuditRecord] = []
        self._lock = threading.RLock()
        self._context: dict[str, str | None] = {"task_id": None, "plan_id": None}

    @contextmanager
    def scoped(self, *, task_id: str | None = None, plan_id: str | None = None) -> Iterator[None]:
        """Define o contexto (tarefa/plano de origem) dos registros."""
        with self._lock:
            previous = dict(self._context)
            self._context = {"task_id": task_id, "plan_id": plan_id}
        try:
            yield
        finally:
            with self._lock:
                self._context = previous

    def record(
        self,
        *,
        tool: str,
        operation: str,
        requested_path: str | None,
        resolved_path: str | None = None,
        success: bool = True,
        error: str | None = None,
        **detail: Any,
    ) -> AuditRecord:
        """Registra uma tentativa (sucesso, bloqueio ou falha)."""
        with self._lock:
            record = AuditRecord(
                timestamp=_now_iso(),
                tool=tool,
                operation=operation,
                requested_path=requested_path,
                resolved_path=resolved_path,
                success=success,
                error=error,
                task_id=self._context.get("task_id"),
                plan_id=self._context.get("plan_id"),
                detail=dict(detail),
            )
            self._records.append(record)
        if self._sink is not None:
            try:
                self._sink(record.to_dict())
            except Exception:  # sink quebrado não derruba a operação
                logger.exception("Sink de auditoria falhou (registro mantido em memória).")
        return record

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self.records]


# ------------------------------------------------------------------- sandbox
class WorkspaceSandbox:
    """Política de acesso a diretórios explicitamente autorizados.

    Args:
        roots: diretórios autorizados (devem ser caminhos **absolutos**;
            são resolvidos no construtor — symlinks normalizados).
        writable: habilita operações de escrita (default ``False`` =
            somente leitura).
        allow_delete: habilita ``delete_file`` (exige também
            ``writable``; default ``False`` — exclusão é opt-in duplo).

    Regras de resolução (:meth:`resolve`):

    - o caminho deve ser texto não vazio, sem caracteres de controle;
    - **nenhum** componente pode ser ``..`` (traversal bloqueado);
    - caminhos absolutos: aceitos apenas se resolvem para dentro de uma
      das raízes autorizadas;
    - caminhos relativos: resolvidos contra as raízes, **na ordem** em
      que foram declaradas — a primeira raiz que contém o caminho vence;
    - a contenção é verificada **após** ``Path.resolve()`` (symlinks que
      apontam para fora do workspace são bloqueados).
    """

    def __init__(
        self,
        roots: Iterable[Path | str],
        *,
        writable: bool = False,
        allow_delete: bool = False,
    ) -> None:
        resolved_roots: list[Path] = []
        for root in roots:
            path = Path(root)
            if not path.is_absolute():
                raise ValueError(
                    f"Raiz de workspace deve ser um caminho absoluto (recebido: {root!r})."
                )
            resolved = path.resolve()
            if resolved not in resolved_roots:
                resolved_roots.append(resolved)
        if not resolved_roots:
            raise ValueError("O sandbox precisa de ao menos uma raiz autorizada.")
        self._roots = tuple(resolved_roots)
        self._writable = bool(writable)
        self._allow_delete = bool(allow_delete)

    # ------------------------------------------------------------ propriedades
    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    @property
    def writable(self) -> bool:
        return self._writable

    @property
    def allow_delete(self) -> bool:
        return self._allow_delete

    # ----------------------------------------------------------------- política
    def assert_operation_allowed(self, operation: str) -> None:
        """Bloqueia operações incompatíveis com a política (antes de tudo)."""
        if operation == OPERATION_READ:
            return
        if operation in (OPERATION_WRITE, OPERATION_DELETE):
            if not self._writable:
                raise WriteNotAllowedError(
                    "Escrita bloqueada: a política do workspace está em modo "
                    "somente leitura (writable=False)."
                )
            if operation == OPERATION_DELETE and not self._allow_delete:
                raise DeleteNotAllowedError(
                    "Exclusão bloqueada: a política do workspace não habilita "
                    "delete (allow_delete=False)."
                )
            return
        raise FilesystemError(f"Operação desconhecida: {operation!r}.")

    # -------------------------------------------------------------- resolução
    def check_operation(self, operation: str, resolved: Path) -> None:
        """Checagem de política **ciente do caminho resolvido** (0.5.x).

        A política clássica é independente de caminho; sandboxs
        multi-workspace (:class:`~app.tools.workspaces.MultiWorkspaceSandbox`)
        sobrescrevem para decidir pela raiz que contém o caminho.
        """
        self.assert_operation_allowed(operation)

    def _validate_raw(self, path: Any) -> str:
        if not isinstance(path, str):
            raise InvalidPathError(
                f"Parâmetro 'path' é obrigatório e deve ser texto (recebido: {type(path).__name__})."
            )
        if not path.strip():
            raise InvalidPathError("O caminho não pode ser vazio.")
        for char in path:
            if ord(char) < 32 or ord(char) == 127:
                raise InvalidPathError(
                    "O caminho contém caracteres de controle (inválido)."
                )
        if Path(path).parts and ".." in Path(path).parts:
            raise PathOutsideWorkspaceError(
                "Caminho bloqueado: componente '..' não é permitido "
                "(tentativa de traversal fora do workspace)."
            )
        return path

    def _contains(self, root: Path, candidate: Path) -> bool:
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        return True

    def resolve(self, path: Any) -> Path:
        """Valida e resolve ``path`` dentro das raízes autorizadas.

        Raises:
            InvalidPathError: caminho vazio/tipo errado/caracteres de controle.
            PathOutsideWorkspaceError: traversal ``..`` ou fora do workspace.
        """
        raw = self._validate_raw(path)
        candidate = Path(raw)
        if candidate.is_absolute():
            resolved = candidate.resolve()
            for root in self._roots:
                if self._contains(root, resolved):
                    return resolved
            raise PathOutsideWorkspaceError(
                f"Caminho fora do workspace autorizado: {raw!r}."
            )
        for root in self._roots:
            resolved = (root / candidate).resolve()
            if self._contains(root, resolved):
                return resolved
        raise PathOutsideWorkspaceError(
            f"Caminho fora do workspace autorizado: {raw!r}."
        )


# -------------------------------------------------------------------- tools
class FilesystemTool(StructuredTool):
    """Base das ferramentas de filesystem: política + auditoria uniformes.

    Fluxo de :meth:`run`: validação de entrada → porteio da política do
    sandbox (operação permitida?) → resolução confinada do caminho →
    operação real (subclass) → auditoria → :class:`ToolResult`.
    Falhas/bloqueios **não** viram exceção: viram ``ok=False`` com erro
    amigável (e registro de auditoria correspondente).
    """

    _abstract_base = True  # base intermediária: metadados nas concretas

    #: Nome da operação para a política/auditoria: read | write | delete.
    operation: str = OPERATION_READ

    def __init__(self, sandbox: WorkspaceSandbox, audit: FilesystemAudit | None = None) -> None:
        self._sandbox = sandbox
        self._audit = audit

    def _audit_record(self, requested: Any, resolved: Path | None, *, success: bool,
                      error: str | None = None, **detail: Any) -> None:
        if self._audit is None:
            return
        self._audit.record(
            tool=self.name,
            operation=self.operation,
            requested_path=requested if isinstance(requested, str) else None,
            resolved_path=str(resolved) if resolved is not None else None,
            success=success,
            error=error,
            **detail,
        )

    def run(self, **kwargs: Any) -> ToolResult:
        requested = kwargs.get("path")
        try:
            resolved = self._sandbox.resolve(requested)
            self._sandbox.check_operation(self.operation, resolved)
        except FilesystemError as exc:
            logger.warning("Ferramenta %s bloqueada: %s", self.name, exc)
            self._audit_record(requested, None, success=False, error=str(exc))
            return ToolResult(
                ok=False,
                data={"operation": self.operation, "requested_path": requested if isinstance(requested, str) else None},
                error=str(exc),
            )
        try:
            data = self._perform(resolved, **kwargs)
        except FilesystemError as exc:
            self._audit_record(requested, resolved, success=False, error=str(exc))
            return ToolResult(
                ok=False,
                data={"operation": self.operation, "requested_path": requested,
                      "resolved_path": str(resolved)},
                error=str(exc),
            )
        except OSError as exc:
            error = f"Erro de filesystem: {exc}"
            logger.error("Ferramenta %s falhou em %s: %s", self.name, resolved, exc)
            self._audit_record(requested, resolved, success=False, error=error)
            return ToolResult(
                ok=False,
                data={"operation": self.operation, "requested_path": requested,
                      "resolved_path": str(resolved)},
                error=error,
            )
        self._audit_record(requested, resolved, success=True, **data.get("_audit", {}))
        data.pop("_audit", None)
        payload: dict[str, Any] = {
            "operation": self.operation,
            "requested_path": requested,
            "resolved_path": str(resolved),
        }
        payload.update(data)
        return ToolResult(ok=True, data=payload)

    @abstractmethod
    def _perform(self, resolved: Path, **kwargs: Any) -> dict[str, Any]:
        """Operação real (implementada por cada ferramenta concreta)."""
        raise NotImplementedError  # pragma: no cover


class ListDirectoryTool(FilesystemTool):
    """Lista o conteúdo de um diretório do workspace (permissão READ)."""

    name = "list_directory"
    description = "Lista arquivos e subdiretórios de um diretório do workspace."
    required_permission = PermissionLevel.READ
    operation = OPERATION_READ

    def _perform(self, resolved: Path, **kwargs: Any) -> dict[str, Any]:
        if not resolved.exists():
            raise FilesystemError(f"Diretório não existe: {resolved}")
        if not resolved.is_dir():
            raise FilesystemError(f"O caminho não é um diretório: {resolved}")
        entries = []
        for item in sorted(resolved.iterdir(), key=lambda p: p.name):
            kind = "dir" if item.is_dir() else ("file" if item.is_file() else "other")
            entries.append({
                "name": item.name,
                "type": kind,
                "size": item.stat().st_size if item.is_file() else None,
            })
        return {"entries": entries, "count": len(entries)}


class ReadFileTool(FilesystemTool):
    """Lê um arquivo de texto (UTF-8) do workspace (permissão READ)."""

    name = "read_file"
    description = "Lê o conteúdo de um arquivo de texto (UTF-8) do workspace."
    required_permission = PermissionLevel.READ
    operation = OPERATION_READ

    #: Limite padrão de leitura (1 MiB) — arquivos maiores exigem opt-in.
    DEFAULT_MAX_BYTES = 1_000_000

    def _perform(self, resolved: Path, **kwargs: Any) -> dict[str, Any]:
        if not resolved.exists():
            raise FilesystemError(f"Arquivo não existe: {resolved}")
        if resolved.is_dir():
            raise FilesystemError(f"O caminho é um diretório (não um arquivo): {resolved}")
        max_bytes = kwargs.get("max_bytes", self.DEFAULT_MAX_BYTES)
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
            raise FilesystemError("Parâmetro 'max_bytes' deve ser um inteiro positivo.")
        size = resolved.stat().st_size
        if size > max_bytes:
            raise FilesystemError(
                f"Arquivo grande demais ({size} bytes; limite {max_bytes}). "
                "Ajuste 'max_bytes' se for intencional."
            )
        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise FilesystemError(
                f"O arquivo não é texto UTF-8 válido: {resolved}"
            ) from None
        return {"content": content, "size_bytes": size, "_audit": {"size_bytes": size}}


class _WriteBaseTool(FilesystemTool):
    """Base de escrita: exige permissão WRITE + política writable."""

    _abstract_base = True  # base intermediária: metadados nas concretas

    required_permission = PermissionLevel.WRITE
    operation = OPERATION_WRITE

    def _content(self, kwargs: dict[str, Any]) -> str:
        content = kwargs.get("content")
        if not isinstance(content, str):
            raise FilesystemError(
                "Parâmetro 'content' é obrigatório e deve ser texto "
                f"(recebido: {type(content).__name__})."
            )
        return content

    def _ensure_parent(self, resolved: Path) -> None:
        parent = resolved.parent
        if not parent.exists():
            raise FilesystemError(
                f"Diretório pai não existe: {parent} (crie-o antes de escrever)."
            )
        if not parent.is_dir():
            raise FilesystemError(f"O pai do caminho não é um diretório: {parent}.")


class WriteFileTool(_WriteBaseTool):
    """Escreve um arquivo (cria OU sobrescreve) no workspace.

    Destrutiva em relação ao conteúdo anterior — use checkpoint/
    consentimento nas camadas de cima (``FILESYSTEM_DESTRUCTIVE_TOOLS``).
    """

    name = "write_file"
    description = (
        "Escreve conteúdo em um arquivo do workspace (sobrescreve se existir)."
    )

    def _perform(self, resolved: Path, **kwargs: Any) -> dict[str, Any]:
        content = self._content(kwargs)
        existed = resolved.exists()
        if existed and resolved.is_dir():
            raise FilesystemError(f"O caminho é um diretório: {resolved}")
        self._ensure_parent(resolved)
        resolved.write_text(content, encoding="utf-8")
        return {
            "written": True,
            "overwritten": existed,
            "bytes_written": len(content.encode("utf-8")),
            "_audit": {"bytes_written": len(content.encode("utf-8")), "overwritten": existed},
        }


class CreateFileTool(_WriteBaseTool):
    """Cria um arquivo **novo** no workspace (falha se já existir)."""

    name = "create_file"
    description = "Cria um arquivo novo no workspace (não sobrescreve existente)."

    def _perform(self, resolved: Path, **kwargs: Any) -> dict[str, Any]:
        content = self._content(kwargs)
        if resolved.exists():
            raise FilesystemError(
                f"O arquivo já existe (create_file não sobrescreve): {resolved}"
            )
        self._ensure_parent(resolved)
        resolved.write_text(content, encoding="utf-8")
        return {
            "created": True,
            "bytes_written": len(content.encode("utf-8")),
            "_audit": {"bytes_written": len(content.encode("utf-8"))},
        }


class DeleteFileTool(_WriteBaseTool):
    """Apaga um **arquivo** do workspace (opt-in duplo da política).

    Exige ``writable=True`` **e** ``allow_delete=True`` no sandbox, além
    da permissão ``WRITE`` — e é candidata a checkpoint/consentimento.
    Diretórios nunca são apagados por esta ferramenta.
    """

    name = "delete_file"
    description = "Apaga um arquivo do workspace (política deve habilitar delete)."
    operation = OPERATION_DELETE

    def _perform(self, resolved: Path, **kwargs: Any) -> dict[str, Any]:
        if not resolved.exists():
            raise FilesystemError(f"Arquivo não existe: {resolved}")
        if resolved.is_dir():
            raise FilesystemError(
                f"O caminho é um diretório — delete_file apaga apenas arquivos: {resolved}"
            )
        resolved.unlink()
        return {"deleted": True, "_audit": {"deleted": True}}


class FileExistsTool(FilesystemTool):
    """Verifica se um caminho existe no workspace (permissão READ)."""

    name = "file_exists"
    description = "Verifica se um arquivo ou diretório existe no workspace."
    required_permission = PermissionLevel.READ
    operation = OPERATION_READ

    def _perform(self, resolved: Path, **kwargs: Any) -> dict[str, Any]:
        exists = resolved.exists()
        return {
            "exists": exists,
            "is_dir": resolved.is_dir() if exists else None,
            "_audit": {"exists": exists},
        }


def build_filesystem_registry(
    permissions: PermissionManager,
    sandbox: WorkspaceSandbox,
    audit: FilesystemAudit | None = None,
) -> ToolRegistry:
    """Registra as 8 ferramentas de filesystem em um ``ToolRegistry``.

    O registro é **sempre explícito** — nada é registrado globalmente no
    startup da aplicação; quem constrói o registry define o sandbox
    (raízes autorizadas) e o porteio de permissões.
    """
    # Imports locais — search_files/edit_file importam este módulo (base
    # ``FilesystemTool``), logo o import no topo criaria ciclo.
    from app.tools.search_files import SearchFilesTool
    from app.tools.edit_file import EditFileTool

    registry = ToolRegistry(permissions)
    for tool in (
        ListDirectoryTool(sandbox, audit),
        ReadFileTool(sandbox, audit),
        WriteFileTool(sandbox, audit),
        CreateFileTool(sandbox, audit),
        DeleteFileTool(sandbox, audit),
        FileExistsTool(sandbox, audit),
        SearchFilesTool(sandbox, audit),
        EditFileTool(sandbox, audit),
    ):
        registry.register(tool)
    return registry
