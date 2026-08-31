"""Testes da configuração nova da 0.3 (LUMEN_MAX_MEMORY_RECORDS)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import ConfigError, Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_default_max_memory_records():
    assert Settings().max_memory_records == 12


def test_max_memory_records_from_env_and_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LUMEN_MAX_MEMORY_RECORDS=7\n", encoding="utf-8")
    assert Settings.load(env_file=env_file, environ={}).max_memory_records == 7

    settings = Settings.load(env_file=tmp_path / ".env-x",
                             environ={"LUMEN_MAX_MEMORY_RECORDS": "3"})
    assert settings.max_memory_records == 3


@pytest.mark.parametrize("valor", ["abc", "0", "-4"])
def test_invalid_max_memory_records_raises(tmp_path, valor):
    with pytest.raises(ConfigError) as exc:
        Settings.load(env_file=tmp_path / ".env-x",
                      environ={"LUMEN_MAX_MEMORY_RECORDS": valor})
    assert "LUMEN_MAX_MEMORY_RECORDS" in str(exc.value)


def test_env_example_documents_new_key():
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "LUMEN_MAX_MEMORY_RECORDS" in content
