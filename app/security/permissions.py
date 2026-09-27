"""Segurança e permissões da Lumen.

Princípio: a Lumen **nunca** deverá executar uma ação sensível (ler ou
escrever arquivos, executar comandos, controlar mouse/teclado/aplicações)
sem que a permissão correspondente tenha sido concedida explicitamente
pelo usuário.

Fase 0: apenas :attr:`PermissionLevel.CHAT` é concedida por padrão.
Nada além disso.
"""
from __future__ import annotations

import threading
from collections.abc import Iterable
from enum import IntEnum


class PermissionLevel(IntEnum):
    """Níveis de permissão, ordenados por risco (maior = mais sensível).

    A ordenação é informativa (para documentação e UI); as concessões em
    si são explícitas por nível — ter ``WRITE`` não implica ter ``READ``.
    """

    CHAT = 10
    READ = 20
    WRITE = 30
    TERMINAL = 40
    COMPUTER_CONTROL = 50
    VISION_PROVIDER = 60


PERMISSION_DESCRIPTIONS: dict[PermissionLevel, str] = {
    PermissionLevel.CHAT: "Conversar com o usuário",
    PermissionLevel.READ: "Ler arquivos e diretórios",
    PermissionLevel.WRITE: "Criar, modificar ou apagar arquivos",
    PermissionLevel.TERMINAL: "Executar comandos no terminal",
    PermissionLevel.COMPUTER_CONTROL: "Controlar mouse, teclado e aplicações",
}


def _as_level(level: "PermissionLevel | str") -> PermissionLevel:
    """Aceita ``PermissionLevel`` ou o nome da constante (``"WRITE"``)."""
    if isinstance(level, PermissionLevel):
        return level
    try:
        return PermissionLevel[str(level).upper()]
    except (KeyError, TypeError) as exc:
        raise TypeError(
            f"Nível de permissão inválido: {level!r}. "
            f"Use um de: {', '.join(l.name for l in PermissionLevel)}."
        ) from exc


class PermissionDeniedError(PermissionError):
    """Ação bloqueada por falta de permissão."""

    def __init__(self, level: PermissionLevel) -> None:
        self.level = level
        description = PERMISSION_DESCRIPTIONS.get(level, level.name)
        super().__init__(
            f"Permissão negada: '{level.name}' ({description}) não foi concedida à Lumen."
        )


class PermissionManager:
    """Guarda as permissões concedidas (grants explícitos, thread-safe)."""

    #: Concessões iniciais na fase 0: apenas conversa.
    DEFAULT_GRANTS: tuple[PermissionLevel, ...] = (PermissionLevel.CHAT,)

    def __init__(self, granted: Iterable["PermissionLevel | str"] | None = None) -> None:
        initial = self.DEFAULT_GRANTS if granted is None else granted
        self._granted: set[PermissionLevel] = {_as_level(level) for level in initial}
        self._lock = threading.RLock()

    def grant(self, level: "PermissionLevel | str") -> None:
        """Concede uma permissão (idempotente)."""
        with self._lock:
            self._granted.add(_as_level(level))

    def revoke(self, level: "PermissionLevel | str") -> None:
        """Revoga uma permissão (idempotente)."""
        with self._lock:
            self._granted.discard(_as_level(level))

    def is_granted(self, level: "PermissionLevel | str") -> bool:
        """Verifica se uma permissão específica foi concedida."""
        with self._lock:
            return _as_level(level) in self._granted

    def require(self, level: "PermissionLevel | str") -> None:
        """Exige uma permissão; levanta :class:`PermissionDeniedError` se ausente."""
        resolved = _as_level(level)
        if not self.is_granted(resolved):
            raise PermissionDeniedError(resolved)

    def granted_levels(self) -> frozenset[PermissionLevel]:
        """Conjunto imutável das permissões vigentes."""
        with self._lock:
            return frozenset(self._granted)
