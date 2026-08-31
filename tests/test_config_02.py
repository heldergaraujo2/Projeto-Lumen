"""Testes das novas configurações da 0.2 (contexto, timeout, retry)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import ConfigError, Settings

ENV_KEYS_0_2 = (
    "LUMEN_PROVIDER",
    "LUMEN_MODEL",
    "LUMEN_API_KEY",
    "LUMEN_DATA_DIR",
    "LUMEN_LOG_LEVEL",
    "LUMEN_MAX_CONTEXT_MESSAGES",
    "LUMEN_REQUEST_TIMEOUT",
    "LUMEN_MAX_RETRIES",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_defaults_for_new_settings():
    settings = Settings()
    assert settings.max_context_messages == 50
    assert settings.request_timeout == 60.0
    assert settings.max_retries == 2
    assert settings.provider == "mock"


def test_new_settings_from_environment(tmp_path):
    environ = {
        "LUMEN_PROVIDER": "openai",
        "LUMEN_MODEL": "gpt-4o-mini",
        "LUMEN_API_KEY": "sk-x",
        "LUMEN_MAX_CONTEXT_MESSAGES": "10",
        "LUMEN_REQUEST_TIMEOUT": "30.5",
        "LUMEN_MAX_RETRIES": "4",
    }
    settings = Settings.load(env_file=tmp_path / ".env-inexistente", environ=environ)
    assert settings.provider == "openai"
    assert settings.max_context_messages == 10
    assert settings.request_timeout == 30.5
    assert settings.max_retries == 4


def test_new_settings_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LUMEN_MAX_CONTEXT_MESSAGES=7\nLUMEN_REQUEST_TIMEOUT=15\nLUMEN_MAX_RETRIES=1\n",
        encoding="utf-8",
    )
    settings = Settings.load(env_file=env_file, environ={})
    assert settings.max_context_messages == 7
    assert settings.request_timeout == 15.0
    assert settings.max_retries == 1


def test_environment_overrides_env_file_for_new_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LUMEN_MAX_RETRIES=1\n", encoding="utf-8")
    settings = Settings.load(env_file=env_file, environ={"LUMEN_MAX_RETRIES": "5"})
    assert settings.max_retries == 5


@pytest.mark.parametrize("chave,valor", [
    ("LUMEN_MAX_CONTEXT_MESSAGES", "abc"),
    ("LUMEN_MAX_CONTEXT_MESSAGES", "0"),
    ("LUMEN_REQUEST_TIMEOUT", "rapido"),
    ("LUMEN_REQUEST_TIMEOUT", "-5"),
    ("LUMEN_MAX_RETRIES", "muitos"),
    ("LUMEN_MAX_RETRIES", "-1"),
])
def test_invalid_values_raise_config_error(tmp_path, chave, valor):
    with pytest.raises(ConfigError) as exc:
        Settings.load(env_file=tmp_path / ".env-x", environ={chave: valor})
    assert chave in str(exc.value)


def test_zero_retries_is_valid(tmp_path):
    settings = Settings.load(env_file=tmp_path / ".env-x",
                             environ={"LUMEN_MAX_RETRIES": "0"})
    assert settings.max_retries == 0


def test_env_example_documents_all_0_2_keys():
    """19. .env.example documenta todas as variáveis da 0.2."""
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    for chave in ENV_KEYS_0_2:
        assert chave in content, f"chave ausente no .env.example: {chave}"
