"""Testes da memória de conversa (MemoryStore)."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.memory.store import MemoryStore, MemoryStoreError


def test_memory_saves_and_persists(tmp_path):
    """1. Memória consegue salvar (e recarregar do disco)."""
    path = tmp_path / "mem" / "conversation.json"
    store = MemoryStore(path)

    message = store.add_message("user", "Quero criar um inventário")

    assert message.role == "user"
    assert message.content == "Quero criar um inventário"
    datetime.fromisoformat(message.timestamp)  # timestamp ISO válido
    assert path.exists(), "o arquivo de memória deveria existir após salvar"

    reloaded = MemoryStore(path)
    assert reloaded.count == 1
    assert reloaded.all_messages()[0].to_dict() == message.to_dict()


def test_memory_recovers_recent_in_order(tmp_path):
    """2. Memória consegue recuperar mensagens recentes, em ordem."""
    store = MemoryStore(tmp_path / "conversation.json")
    for index in range(5):
        role = "user" if index % 2 == 0 else "assistant"
        store.add_message(role, f"mensagem {index}")

    recent = store.recent(3)
    assert [m.content for m in recent] == ["mensagem 2", "mensagem 3", "mensagem 4"]
    assert store.recent(0) == []


def test_memory_rejects_invalid_role(tmp_path):
    store = MemoryStore(tmp_path / "conversation.json")
    with pytest.raises(ValueError):
        store.add_message("admin", "oi")


def test_memory_rejects_empty_content(tmp_path):
    store = MemoryStore(tmp_path / "conversation.json")
    with pytest.raises(ValueError):
        store.add_message("user", "   ")


def test_memory_reports_corrupted_file(tmp_path):
    path = tmp_path / "conversation.json"
    path.write_text("{ não sou um json válido", encoding="utf-8")
    with pytest.raises(MemoryStoreError):
        MemoryStore(path)


def test_memory_clear(tmp_path):
    store = MemoryStore(tmp_path / "conversation.json")
    store.add_message("user", "oi")
    store.add_message("assistant", "olá")
    store.clear()
    assert store.count == 0
    assert MemoryStore(tmp_path / "conversation.json").count == 0
