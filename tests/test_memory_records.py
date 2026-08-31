"""Testes do modelo de registros e da redação de segredos (0.3)."""
from __future__ import annotations

import pytest

from app.memory.records import (
    ID_PREFIXES,
    KIND_FILENAMES,
    MemoryKind,
    MemoryRecord,
    RecordError,
    compute_hash,
    normalize_text,
)
from app.memory.sanitization import contains_secret, redact_secrets


# ------------------------------------------------------------------- modelo
def test_six_memory_kinds():
    kinds = {k.value for k in MemoryKind}
    assert kinds == {"PROJECT", "TASK", "KNOWLEDGE", "DECISION", "ISSUE", "SOLUTION"}


def test_every_kind_has_prefix_and_filename():
    for kind in MemoryKind:
        assert ID_PREFIXES[kind]
        assert KIND_FILENAMES[kind].endswith(".json")


def test_record_roundtrip_and_defaults():
    record = MemoryRecord(id="KN-0001", kind=MemoryKind.KNOWLEDGE,
                          title="Cache de assets", content="Usar DerivedDataCache")
    data = record.to_dict()

    assert data["origin"] == "user"
    assert data["status"] == "ACTIVE"
    assert data["tags"] == [] and data["related_ids"] == []
    assert data["supersedes"] is None
    assert data["content_hash"]

    restored = MemoryRecord.from_dict(data)
    assert restored == record


def test_record_from_invalid_dict_raises():
    with pytest.raises(RecordError):
        MemoryRecord.from_dict({"id": "X", "title": "sem kind"})
    with pytest.raises(RecordError):
        MemoryRecord.from_dict({"id": "X", "kind": "PROJECT", "title": "t",
                                "content": "c", "status": "QUEBRADO"})


def test_record_rejects_empty_fields():
    with pytest.raises(RecordError):
        MemoryRecord(id="KN-0001", kind=MemoryKind.KNOWLEDGE, title="  ", content="c")
    with pytest.raises(RecordError):
        MemoryRecord(id="", kind=MemoryKind.KNOWLEDGE, title="t", content="c")


def test_hash_is_stable_and_normalizes():
    h1 = compute_hash("Cache de Assets", "Usar  DDC")
    h2 = compute_hash("cache de assets", "usar DDC")
    h3 = compute_hash("cache de assets", "usar LFS")
    assert h1 == h2          # caixa/espaços não importam
    assert h1 != h3


def test_normalize_text_strips_accents():
    assert normalize_text("Configuração RÁPIDA") == "configuracao rapida"


# ------------------------------------------------------------ redação segredos
@pytest.mark.parametrize("segredo", [
    "sk-abc123def456ghi789",
    "AIzaSyD-1234567890abcdef",
    "api_key=minha-chave-secreta",
    "API_KEY: outra-chave",
    "password = hunter2",
    "Bearer eyJhbGciOiJIUzI1NiJ9",
    "access_token=abc123",
])
def test_secrets_are_detected_and_redacted(segredo):
    text = f"configuração do projeto com {segredo} no meio"
    redacted, found = redact_secrets(text)
    assert found is True
    assert segredo not in redacted
    assert "***" in redacted
    assert contains_secret(text)


def test_normal_dev_content_is_not_mangled():
    text = "O sistema usa total de 512 tokens por requisição no inventory component"
    redacted, found = redact_secrets(text)
    assert found is False
    assert redacted == text
    assert not contains_secret(text)
