"""Configurações de IA salvas pelo usuário via interface gráfica.

Diferentemente do ``.env`` (ferramenta de desenvolvimento), este arquivo
representa uma configuração **explícita do usuário** e, portanto, tem
prioridade sobre ele. Só contém valores não secretos (provider e model);
a API Key vai para o :class:`~app.config.secrets.SecretStore`.

Precedência documentada (maior → menor):

1. Configuração gráfica salva (``data/settings.json`` + cofre de segredos);
2. Variáveis de ambiente reais (``LUMEN_*``);
3. Arquivo ``.env``;
4. Padrões internos.
"""
from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.secrets import API_KEY_NAME, SecretStore

if TYPE_CHECKING:
    from app.config.settings import Settings

#: Chaves permitidas no arquivo de configuração do usuário.
_ALLOWED_KEYS = ("provider", "model")


class UserConfigError(RuntimeError):
    """Falha de leitura/escrita da configuração do usuário."""


class UserConfigStore:
    """Persistência das configurações não secretas escolhidas na UI."""

    FILENAME = "settings.json"

    def __init__(self, file_path: Path | str) -> None:
        self._path = Path(file_path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, str]:
        """Carrega a configuração salva ({} se não existir).

        Raises:
            UserConfigError: arquivo corrompido ou inválido.
        """
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise UserConfigError(
                f"Arquivo de configuração do usuário corrompido: {self._path} ({exc}). "
                "Corrija ou remova o arquivo; salvando novamente pela interface o "
                "arquivo será recriado."
            ) from exc
        if not isinstance(raw, dict):
            raise UserConfigError(
                f"Arquivo de configuração do usuário inválido ({self._path}): "
                "esperado um objeto JSON."
            )
        config: dict[str, str] = {}
        for key in _ALLOWED_KEYS:
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                config[key] = value.strip()
        return config

    def save(self, config: dict[str, str]) -> None:
        """Salva atomicamente apenas as chaves permitidas (não secretas)."""
        clean = {k: str(config[k]).strip() for k in _ALLOWED_KEYS if str(config.get(k, "")).strip()}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)  # escrita atômica


def resolve_api_key(base: "Settings", secrets: SecretStore) -> str:
    """Chave efetiva: cofre da aplicação → chave do ``.env`` → vazia.

    A remoção da chave no cofre faz o sistema cair de volta para a chave
    do ``.env`` (se existir) — comportamento documentado.
    """
    stored = secrets.get_secret(API_KEY_NAME)
    if stored:
        return stored
    return base.api_key or ""


def apply_user_overrides(
    base: "Settings", overrides: dict[str, str] | None, secrets: SecretStore
) -> "Settings":
    """Combina ``.env``/ambiente com a configuração gráfica salva.

    A configuração gráfica (``overrides``) vence; a API Key efetiva vem
    do cofre, com fallback para a chave do ``.env``.
    """
    overrides = overrides or {}
    provider = overrides.get("provider") or base.provider
    model = overrides.get("model") or base.model
    return replace(base, provider=provider, model=model, api_key=resolve_api_key(base, secrets))
