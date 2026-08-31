"""Workspaces autorizados da Lumen (0.5.x — camada de controle).

Um *workspace* é um diretório que o usuário **explicitamente autorizou**
para as ferramentas de filesystem, com política própria:

- ``writable=False`` (padrão): somente leitura;
- ``writable=True``: permite escrita/criação;
- ``allow_delete=True`` (exige ``writable``): opt-in adicional para
  exclusão — o mesmo duplo/opt-in triplo da 0.5.

Garantias preservadas:

- **Nada é autorizado por padrão** — o store começa vazio (arquivo nem
  existe até a primeira autorização) e **raiz de disco/Windows inteiro é
  rejeitada** (ex.: ``/`` ou ``C:\\``);
- caminhos são **validados e normalizados** (absoluto, existente,
  diretório, resolvido — symlinks normalizados) antes de armazenados;
- :class:`MultiWorkspaceSandbox` aplica a política **por raiz**: um
  caminho que cai em workspace somente-leitura é bloqueado para
  escrita mesmo que outro workspace permita escrita.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.tools.filesystem import (
    DeleteNotAllowedError,
    FilesystemError,
    PathOutsideWorkspaceError,
    WorkspaceSandbox,
    WriteNotAllowedError,
)

logger = logging.getLogger("lumen.tools.workspaces")


class WorkspaceStoreError(RuntimeError):
    """Falha do store de workspaces (persistência inválida)."""


def _now_anchor(path: Path) -> bool:
    """True se ``path`` é a raiz de um disco (ex.: ``/``, ``C:\\``)."""
    return path == Path(path.anchor)


@dataclass(frozen=True)
class WorkspaceEntry:
    """Um diretório autorizado + sua política."""

    root: Path
    writable: bool = False
    allow_delete: bool = False

    @property
    def mode_label(self) -> str:
        if self.allow_delete:
            return "escrita + exclusão"
        return "escrita" if self.writable else "somente leitura"

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "writable": self.writable,
            "allow_delete": self.allow_delete,
        }

    @classmethod
    def from_dict(cls, data: object) -> "WorkspaceEntry":
        if not isinstance(data, dict):
            raise WorkspaceStoreError("Entrada de workspace inválida (não é objeto).")
        root = data.get("root")
        if not isinstance(root, str) or not root.strip():
            raise WorkspaceStoreError("Entrada de workspace sem 'root' válido.")
        writable = bool(data.get("writable", False))
        allow_delete = bool(data.get("allow_delete", False))
        if allow_delete and not writable:
            raise WorkspaceStoreError(
                f"Workspace {root!r} inválido: allow_delete exige writable."
            )
        return cls(root=Path(root), writable=writable, allow_delete=allow_delete)


class WorkspaceStore:
    """Persistência dos workspaces autorizados (JSON local, atômico).

    O arquivo **só nasce na primeira autorização** — construtor/leitura
    não criam nada (startup sem efeitos colaterais).
    """

    FILENAME = "workspaces.json"

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------- persistência
    def load(self) -> list[WorkspaceEntry]:
        """Carrega as entradas salvas (arquivo ausente ⇒ lista vazia)."""
        with self._lock:
            if not self._path.exists():
                return []
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise WorkspaceStoreError(
                    f"Não foi possível ler {self._path.name}: {exc}"
                ) from exc
            if not isinstance(raw, list):
                raise WorkspaceStoreError(
                    f"{self._path.name} inválido: esperada uma lista de workspaces."
                )
            entries = [WorkspaceEntry.from_dict(item) for item in raw]
            # invariantes de unicidade preservados ao carregar
            seen: set[Path] = set()
            for entry in entries:
                if entry.root in seen:
                    raise WorkspaceStoreError(
                        f"{self._path.name} inválido: workspace duplicado ({entry.root})."
                    )
                seen.add(entry.root)
            return entries

    def save(self, entries: Iterable[WorkspaceEntry]) -> None:
        """Grava a lista completa (escrita atômica ``.tmp`` + replace)."""
        payload = json.dumps(
            [entry.to_dict() for entry in entries], ensure_ascii=False, indent=2
        )
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(payload + "\n", encoding="utf-8")
            os.replace(tmp, self._path)

    # ---------------------------------------------------------------- operações
    def add(
        self, path: str, *, writable: bool = False, allow_delete: bool = False
    ) -> WorkspaceEntry:
        """Valida, normaliza e autoriza um novo workspace (persiste)."""
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Informe o caminho do diretório a autorizar.")
        candidate = Path(path.strip())
        if not candidate.is_absolute():
            raise ValueError(
                f"Caminho relativo não é aceito: {path!r} (use o caminho absoluto)."
            )
        if not candidate.exists():
            raise ValueError(f"O diretório não existe: {path}")
        if not candidate.is_dir():
            raise ValueError(f"O caminho não é um diretório: {path}")
        resolved = candidate.resolve()
        if _now_anchor(resolved):
            raise ValueError(
                "Autorizar a raiz do disco equivale a dar acesso a todo o "
                "sistema — escolha um diretório específico."
            )
        if allow_delete and not writable:
            raise ValueError("Permitir exclusão exige permitir escrita (writable).")
        entries = self.load()
        if any(entry.root == resolved for entry in entries):
            raise ValueError(f"Workspace já autorizado: {resolved}")
        entry = WorkspaceEntry(root=resolved, writable=writable,
                               allow_delete=allow_delete)
        entries.append(entry)
        self.save(entries)
        logger.info("Workspace autorizado: %s (%s).", resolved, entry.mode_label)
        return entry

    def remove(self, path: str) -> WorkspaceEntry:
        """Remove uma autorização existente (persiste)."""
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Informe o caminho do workspace a remover.")
        candidate = Path(path.strip())
        resolved = candidate.resolve() if candidate.is_absolute() else None
        entries = self.load()
        for index, entry in enumerate(entries):
            if (resolved is not None and entry.root == resolved) or entry.root == Path(path.strip()):
                removed = entries.pop(index)
                self.save(entries)
                logger.info("Workspace removido: %s.", removed.root)
                return removed
        raise ValueError(f"Workspace não autorizado: {path}")

    def set_flags(
        self, path: str, *, writable: bool, allow_delete: bool
    ) -> WorkspaceEntry:
        """Atualiza a política (somente leitura/escrita/exclusão) de um workspace."""
        if allow_delete and not writable:
            raise ValueError("Permitir exclusão exige permitir escrita (writable).")
        candidate = Path(path.strip()) if isinstance(path, str) else Path("")
        entries = self.load()
        for index, entry in enumerate(entries):
            if entry.root == candidate.resolve() or entry.root == candidate:
                updated = WorkspaceEntry(root=entry.root, writable=writable,
                                         allow_delete=allow_delete)
                entries[index] = updated
                self.save(entries)
                logger.info(
                    "Workspace %s agora: %s.", updated.root, updated.mode_label
                )
                return updated
        raise ValueError(f"Workspace não autorizado: {path}")


class MultiWorkspaceSandbox:
    """Sandbox sobre o **conjunto** de workspaces autorizados.

    - ``resolve`` procura em cada workspace (na ordem autorizada) e
      devolve o primeiro que contém o caminho;
    - ``check_operation`` aplica a política **do workspace que contém o
      caminho** (somente leitura num workspace bloqueia escrita mesmo
      que outro permita);
    - conjunto vazio ⇒ **tudo** bloqueado (``PathOutsideWorkspaceError``).

    Interface compatível com :class:`~app.tools.filesystem.WorkspaceSandbox`
    (``resolve``/``check_operation``/``assert_operation_allowed``).
    """

    def __init__(self, entries: Iterable[WorkspaceEntry]) -> None:
        self._entries: tuple[WorkspaceEntry, ...] = tuple(entries)
        self._sandboxes: tuple[WorkspaceSandbox, ...] = tuple(
            WorkspaceSandbox(
                [entry.root], writable=entry.writable, allow_delete=entry.allow_delete
            )
            for entry in self._entries
        )

    @property
    def entries(self) -> tuple[WorkspaceEntry, ...]:
        return self._entries

    @property
    def roots(self) -> tuple[Path, ...]:
        return tuple(entry.root for entry in self._entries)

    @property
    def writable(self) -> bool:
        """Resumo p/ UI: algum workspace permite escrita."""
        return any(entry.writable for entry in self._entries)

    @property
    def allow_delete(self) -> bool:
        """Resumo p/ UI: algum workspace permite exclusão."""
        return any(entry.allow_delete for entry in self._entries)

    def entry_for(self, resolved: Path) -> WorkspaceEntry | None:
        """Workspace que contém ``resolved`` (ou ``None``)."""
        for entry in self._entries:
            try:
                resolved.relative_to(entry.root)
                return entry
            except ValueError:
                continue
        return None

    def resolve(self, path) -> Path:
        if not self._sandboxes:
            raise PathOutsideWorkspaceError(
                "Nenhum workspace autorizado — autorize um diretório para "
                "que as ferramentas de arquivo possam trabalhar."
            )
        outside: FilesystemError | None = None
        for sandbox in self._sandboxes:
            try:
                return sandbox.resolve(path)
            except PathOutsideWorkspaceError as exc:
                outside = exc
        raise outside if outside is not None else PathOutsideWorkspaceError(
            f"Caminho fora dos workspaces autorizados: {path!r}."
        )

    def check_operation(self, operation: str, resolved: Path) -> None:
        """Política do workspace que contém o caminho resolvido."""
        for entry, sandbox in zip(self._entries, self._sandboxes):
            try:
                resolved.relative_to(entry.root)
            except ValueError:
                continue
            sandbox.assert_operation_allowed(operation)
            return
        raise PathOutsideWorkspaceError(
            f"Caminho fora dos workspaces autorizados: {resolved}"
        )

    def assert_operation_allowed(self, operation: str) -> None:
        """Resumo independente de caminho (leitura livre; escrita/exclusão
        se **algum** workspace permitir). As ferramentas usam
        ``check_operation`` (por caminho) — este método é para UI/diagnóstico."""
        if operation == "read":
            return
        if operation in ("write", "delete"):
            if not self.writable:
                raise WriteNotAllowedError(
                    "Nenhum workspace autorizado permite escrita."
                )
            if operation == "delete" and not self.allow_delete:
                raise DeleteNotAllowedError(
                    "Nenhum workspace autorizado permite exclusão (allow_delete)."
                )
            return
        raise FilesystemError(f"Operação desconhecida: {operation!r}.")
