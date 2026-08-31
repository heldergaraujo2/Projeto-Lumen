"""Armazenamento seguro de segredos da Lumen (API Key).

Estratégia:

1. **Cofre do sistema operacional** quando disponível — no Windows, via
   pacote ``keyring`` (Windows Credential Manager). Preferencial e usado
   automaticamente quando o ``keyring`` está instalado com backend
   funcional.
2. **Fallback em arquivo local** (``data/.credentials.json``) quando o
   cofre do SO não estiver disponível (ex.: Linux sem backend, ambientes
   de teste). O arquivo é criado com permissões restritas (0600),
   escrita atômica, fica fora do versionamento (``.gitignore``) e é
   claramente documentado como fallback.

A API Key **nunca** vai para código, logs, README ou arquivos de
configuração comuns — apenas para um destes dois destinos.
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger("lumen.config.secrets")

#: Nome do serviço/conta no cofre do sistema operacional.
KEYRING_SERVICE = "Lumen"
KEYRING_USERNAME = "api_key"

#: Nome lógico do segredo usado pela interface SecretStore.
API_KEY_NAME = "api_key"


class SecretStoreError(RuntimeError):
    """Falha no armazenamento de segredos."""


class SecretStore(ABC):
    """Contrato para guardar/recuperar/remover segredos da Lumen."""

    @abstractmethod
    def get_secret(self, name: str) -> str | None:
        """Retorna o segredo ou ``None`` se não existir."""
        raise SecretStoreError("SecretStore.get_secret não implementado")  # pragma: no cover

    @abstractmethod
    def set_secret(self, name: str, value: str) -> None:
        """Salva (sobrescreve) o segredo."""
        raise SecretStoreError("SecretStore.set_secret não implementado")  # pragma: no cover

    @abstractmethod
    def delete_secret(self, name: str) -> None:
        """Remove o segredo (idempotente)."""
        raise SecretStoreError("SecretStore.delete_secret não implementado")  # pragma: no cover


# ------------------------------------------------------------- cofre do SO
class KeyringSecretStore(SecretStore):
    """Segredos no cofre do sistema operacional (Windows Credential Manager,
    macOS Keychain, etc.) via pacote ``keyring``."""

    def __init__(self, keyring_module=None) -> None:
        # Módulo injetável: testes passam um cofre falso; produção usa lazy import.
        self._keyring = keyring_module if keyring_module is not None else self._import_keyring()

    @staticmethod
    def _import_keyring():
        try:
            import keyring  # import lazy: ausente → fallback em arquivo
        except ImportError:  # pragma: no cover - depende do ambiente
            raise SecretStoreError("Pacote 'keyring' não instalado.")
        return keyring

    @classmethod
    def is_available(cls, keyring_module=None) -> bool:
        """Verifica se há um backend de cofre **funcional** neste sistema.

        Além de obter o backend, faz uma leitura inofensiva de um segredo
        que não existe: backends ``fail``/indisponíveis (ex.: Linux sem
        serviço de cofre) só revelam o problema na primeira operação, e
        ``get_keyring()`` isolado não é prova suficiente.
        """
        try:
            store = cls(keyring_module)
            store._keyring.get_keyring()
            store._keyring.get_password(KEYRING_SERVICE, "__probe_disponibilidade__")
            return True
        except Exception:  # sem pacote, sem backend funcional ou backend "fail"
            return False

    def get_secret(self, name: str) -> str | None:
        try:
            value = self._keyring.get_password(KEYRING_SERVICE, name)
            return value or None
        except Exception as exc:
            raise SecretStoreError(f"Falha ao ler segredo do cofre do sistema: {exc}") from exc

    def set_secret(self, name: str, value: str) -> None:
        try:
            self._keyring.set_password(KEYRING_SERVICE, name, value)
        except Exception as exc:
            raise SecretStoreError(f"Falha ao salvar segredo no cofre do sistema: {exc}") from exc

    def delete_secret(self, name: str) -> None:
        try:
            try:
                self._keyring.delete_password(KEYRING_SERVICE, name)
            except Exception:
                pass  # ausência é tratada como sucesso (idempotente)
        except Exception as exc:  # pragma: no cover
            raise SecretStoreError(f"Falha ao remover segredo do cofre: {exc}") from exc


# --------------------------------------------------------- fallback em arquivo
class FileSecretStore(SecretStore):
    """Fallback: segredos em arquivo local restrito (``.credentials.json``).

    Usado somente quando o cofre do SO não está disponível. O arquivo:
    fica em ``data/`` (fora do Git), é escrito atomicamente e recebe
    permissão 0600 (best effort; no Windows o cofre do SO é o caminho
    normal). Documentado como fallback — não é tão seguro quanto o
    Credential Manager, mas evita a chave em texto pleno no ``.env``.
    """

    FILENAME = ".credentials.json"

    def __init__(self, data_dir: Path | str) -> None:
        self._path = Path(data_dir) / self.FILENAME
        self._ensure_private()

    def _ensure_private(self) -> None:
        if self._path.exists():
            try:  # best effort; relevante em POSIX
                os.chmod(self._path, 0o600)
            except OSError:  # pragma: no cover
                logger.warning("Não foi possível restringir permissões de %s.", self._path)

    def _load_all(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SecretStoreError(
                f"Arquivo de credenciais corrompido: {self._path} ({exc}). "
                "Remova o arquivo para redefinir as credenciais."
            ) from exc
        return data if isinstance(data, dict) else {}

    def _save_all(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:  # restrito antes do conteúdo ficar visível no destino final
            os.chmod(tmp, 0o600)
        except OSError:  # pragma: no cover
            pass
        os.replace(tmp, self._path)  # escrita atômica

    def get_secret(self, name: str) -> str | None:
        return self._load_all().get(name) or None

    def set_secret(self, name: str, value: str) -> None:
        data = self._load_all()
        data[name] = value
        self._save_all(data)

    def delete_secret(self, name: str) -> None:
        data = self._load_all()
        if name in data:
            del data[name]
            self._save_all(data)


def create_secret_store(data_dir: Path | str, keyring_module=None) -> SecretStore:
    """Escolhe o melhor armazenamento disponível.

    Ordem: cofre do sistema operacional (``keyring``) → arquivo local
    restrito (fallback documentado). A escolha é registrada no log (sem
    jamais registrar valores de segredos).
    """
    try:
        if KeyringSecretStore.is_available(keyring_module):
            logger.info("Cofre do sistema operacional disponível para credenciais.")
            return KeyringSecretStore(keyring_module)
    except Exception:  # pragma: no cover - defensivo
        logger.warning("Falha ao verificar cofre do sistema; usando fallback.")
    logger.warning(
        "Cofre do sistema indisponível — credenciais usarão o fallback em arquivo "
        "restrito (%s).", Path(data_dir) / FileSecretStore.FILENAME,
    )
    return FileSecretStore(data_dir)
