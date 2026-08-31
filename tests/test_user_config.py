"""Testes da configuração do usuário (GUI) e da precedência de fontes."""
from __future__ import annotations

import json

import pytest

from app.config.secrets import FileSecretStore
from app.config.settings import Settings
from app.config.user_config import (
    UserConfigError,
    UserConfigStore,
    apply_user_overrides,
    resolve_api_key,
)


def test_user_config_roundtrip(tmp_path):
    store = UserConfigStore(tmp_path / "settings.json")
    assert store.load() == {}

    store.save({"provider": "openai", "model": "gpt-4o-mini"})
    assert store.load() == {"provider": "openai", "model": "gpt-4o-mini"}

    store.save({"provider": "mock", "model": ""})  # vazio é descartado
    assert store.load() == {"provider": "mock"}


def test_user_config_ignores_secret_keys(tmp_path):
    """O arquivo de configuração do usuário jamais guarda segredos."""
    store = UserConfigStore(tmp_path / "settings.json")
    store.save({"provider": "openai", "model": "m", "api_key": "sk-vazando"})
    on_disk = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert "api_key" not in on_disk
    assert "sk-vazando" not in (tmp_path / "settings.json").read_text(encoding="utf-8")


def test_user_config_atomic_write(tmp_path):
    store = UserConfigStore(tmp_path / "settings.json")
    store.save({"provider": "mock"})
    assert not (tmp_path / "settings.json.tmp").exists()


def test_user_config_corrupted_raises(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("não é json", encoding="utf-8")
    with pytest.raises(UserConfigError) as exc:
        UserConfigStore(path).load()
    assert "corrompido" in str(exc.value)


def test_user_config_invalid_shape_raises(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(UserConfigError):
        UserConfigStore(path).load()


# --------------------------------------------------------------- precedência
def test_gui_overrides_win_over_env(tmp_path):
    base = Settings(provider="mock", model="", api_key="", data_dir=tmp_path)
    secrets = FileSecretStore(tmp_path)
    effective = apply_user_overrides(
        base, {"provider": "openai", "model": "gpt-4o-mini"}, secrets
    )
    assert effective.provider == "openai"
    assert effective.model == "gpt-4o-mini"


def test_without_overrides_base_is_kept(tmp_path):
    base = Settings(provider="mock", model="meu-modelo", data_dir=tmp_path)
    effective = apply_user_overrides(base, None, FileSecretStore(tmp_path))
    assert effective.provider == "mock"
    assert effective.model == "meu-modelo"


def test_api_key_precedence_vault_over_env(tmp_path):
    base = Settings(provider="openai", api_key="sk-do-env", data_dir=tmp_path)
    secrets = FileSecretStore(tmp_path)
    secrets.set_secret("api_key", "sk-do-cofre")

    assert resolve_api_key(base, secrets) == "sk-do-cofre"
    effective = apply_user_overrides(base, {"provider": "openai"}, secrets)
    assert effective.api_key == "sk-do-cofre"


def test_api_key_falls_back_to_env_then_empty(tmp_path):
    base = Settings(provider="openai", api_key="sk-do-env", data_dir=tmp_path)
    secrets = FileSecretStore(tmp_path)

    assert resolve_api_key(base, secrets) == "sk-do-env"  # sem cofre → .env

    secrets.set_secret("api_key", "sk-cofre")
    secrets.delete_secret("api_key")
    assert resolve_api_key(base, secrets) == "sk-do-env"  # remoção → .env

    base_sem_env = Settings(provider="openai", api_key="", data_dir=tmp_path)
    assert resolve_api_key(base_sem_env, secrets) == ""
