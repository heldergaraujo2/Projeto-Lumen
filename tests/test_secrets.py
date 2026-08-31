"""Testes do armazenamento de segredos (API Key).

Sem keyring instalado e sem rede: o cofre do SO é simulado por um módulo
falso e o fallback em arquivo é exercitado de verdade.
"""
from __future__ import annotations

import json
import os
import pytest

from app.config.secrets import (
    API_KEY_NAME,
    FileSecretStore,
    KeyringSecretStore,
    SecretStoreError,
    create_secret_store,
)


# ------------------------------------------------------------------- arquivo
def test_file_store_roundtrip(tmp_path):
    store = FileSecretStore(tmp_path)
    assert store.get_secret(API_KEY_NAME) is None

    store.set_secret(API_KEY_NAME, "sk-abc")
    assert store.get_secret(API_KEY_NAME) == "sk-abc"

    store.delete_secret(API_KEY_NAME)
    assert store.get_secret(API_KEY_NAME) is None
    store.delete_secret(API_KEY_NAME)  # idempotente


def test_file_store_location_and_permissions(tmp_path):
    store = FileSecretStore(tmp_path)
    store.set_secret(API_KEY_NAME, "sk-xyz")

    path = tmp_path / ".credentials.json"
    assert path.exists()
    if os.name == "posix":  # permissões restritas são verificáveis no POSIX
        assert (path.stat().st_mode & 0o777) == 0o600


def test_file_store_overwrite(tmp_path):
    store = FileSecretStore(tmp_path)
    store.set_secret(API_KEY_NAME, "antiga")
    store.set_secret(API_KEY_NAME, "nova")
    assert store.get_secret(API_KEY_NAME) == "nova"
    data = json.loads((tmp_path / ".credentials.json").read_text(encoding="utf-8"))
    assert data == {API_KEY_NAME: "nova"}


def test_file_store_corrupted_raises_clear_error(tmp_path):
    (tmp_path / ".credentials.json").write_text("{corrompido", encoding="utf-8")
    with pytest.raises(SecretStoreError) as exc:
        FileSecretStore(tmp_path).get_secret(API_KEY_NAME)
    assert "corrompido" in str(exc.value)


# -------------------------------------------------------------------- keyring
class FakeKeyringModule:
    """Simula o pacote keyring com um cofre em memória."""

    def __init__(self, broken=False):
        self._vault: dict[tuple[str, str], str] = {}
        self._broken = broken

    def get_keyring(self):
        if self._broken:
            raise RuntimeError("sem backend")
        return object()

    def get_password(self, service, username):
        return self._vault.get((service, username))

    def set_password(self, service, username, password):
        self._vault[(service, username)] = password

    def delete_password(self, service, username):
        self._vault.pop((service, username), None)


def test_keyring_store_roundtrip():
    module = FakeKeyringModule()
    store = KeyringSecretStore(module)
    store.set_secret(API_KEY_NAME, "sk-keyring")
    assert store.get_secret(API_KEY_NAME) == "sk-keyring"
    assert module._vault[("Lumen", API_KEY_NAME)] == "sk-keyring"
    store.delete_secret(API_KEY_NAME)
    assert store.get_secret(API_KEY_NAME) is None


def test_keyring_availability_detection():
    assert KeyringSecretStore.is_available(FakeKeyringModule())
    assert not KeyringSecretStore.is_available(FakeKeyringModule(broken=True))


def test_keyring_availability_requires_functional_backend():
    """Backend presente mas não operacional (ex.: Linux headless) → fallback."""
    keyring_errors = pytest.importorskip(
        "keyring.errors", reason="pacote keyring não instalado neste ambiente"
    )

    class HeadlessKeyring(FakeKeyringModule):
        """get_keyring() funciona, mas toda operação real falha."""

        def get_password(self, service, username):
            raise keyring_errors.NoKeyringError("No recommended backend was available.")

    assert not KeyringSecretStore.is_available(HeadlessKeyring())


def test_keyring_availability_probe_without_keyring_package():
    """O probe não depende do pacote keyring instalado (usa erro genérico)."""

    class HeadlessKeyring(FakeKeyringModule):
        def get_password(self, service, username):
            raise RuntimeError("backend indisponível")

    assert not KeyringSecretStore.is_available(HeadlessKeyring())


def test_create_secret_store_prefers_keyring(tmp_path):
    store = create_secret_store(tmp_path, keyring_module=FakeKeyringModule())
    assert isinstance(store, KeyringSecretStore)


def test_create_secret_store_falls_back_to_file(tmp_path):
    """Sem cofre do SO disponível → fallback em arquivo restrito."""
    store = create_secret_store(tmp_path, keyring_module=FakeKeyringModule(broken=True))
    assert isinstance(store, FileSecretStore)
    store.set_secret(API_KEY_NAME, "sk-fallback")
    assert store.get_secret(API_KEY_NAME) == "sk-fallback"
