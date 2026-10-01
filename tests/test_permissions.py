"""Testes do sistema de permissões."""
from __future__ import annotations

import pytest

from app.security.permissions import (
    PermissionDeniedError,
    PermissionLevel,
    PermissionManager,
)

PROTECTED_LEVELS = (
    PermissionLevel.READ,
    PermissionLevel.WRITE,
    PermissionLevel.TERMINAL,
    PermissionLevel.COMPUTER_CONTROL,
)


def test_default_grants_chat_and_web():
    """Conversa e pesquisa Web são capacidades gerais; operações locais continuam protegidas."""
    manager = PermissionManager()
    assert manager.is_granted(PermissionLevel.CHAT)
    assert manager.is_granted(PermissionLevel.WEB_ACCESS)
    for level in PROTECTED_LEVELS:
        assert not manager.is_granted(level)


def test_levels_ordered_by_risk():
    assert (
        PermissionLevel.CHAT
        < PermissionLevel.READ
        < PermissionLevel.WRITE
        < PermissionLevel.TERMINAL
        < PermissionLevel.COMPUTER_CONTROL
        < PermissionLevel.WEB_ACCESS
    )


def test_grant_and_revoke_roundtrip():
    manager = PermissionManager()
    manager.grant("write")  # aceita nome da constante
    assert manager.is_granted(PermissionLevel.WRITE)

    manager.revoke(PermissionLevel.WRITE)
    assert not manager.is_granted(PermissionLevel.WRITE)
    manager.revoke(PermissionLevel.WRITE)  # idempotente


def test_require_raises_then_passes_after_grant():
    manager = PermissionManager()
    with pytest.raises(PermissionDeniedError) as exc_info:
        manager.require(PermissionLevel.TERMINAL)
    assert "TERMINAL" in str(exc_info.value)

    manager.grant(PermissionLevel.TERMINAL)
    manager.require(PermissionLevel.TERMINAL)  # não levanta mais


def test_invalid_level_raises_type_error():
    manager = PermissionManager()
    with pytest.raises(TypeError):
        manager.grant("SUPERUSER")


def test_web_access_is_granted_by_default_and_can_be_revoked():
    manager = PermissionManager()
    assert manager.is_granted(PermissionLevel.WEB_ACCESS)
    manager.require(PermissionLevel.WEB_ACCESS)
    manager.revoke(PermissionLevel.WEB_ACCESS)
    assert not manager.is_granted(PermissionLevel.WEB_ACCESS)
    with pytest.raises(PermissionDeniedError):
        manager.require(PermissionLevel.WEB_ACCESS)
