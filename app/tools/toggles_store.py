"""Persistência dos toggles de automação da 11H (corrections/verification).

``data/agent_toggles.json`` guarda os toggles de **capacidade** do
ToolsController em um JSON local com escrita atômica e schema versionado::

    {"version": 1,
     "toggles": {"corrections_enabled": false,
                 "verification_enabled": false}}

Princípios (normativos — ver ``docs/SPEC-11H-SETTINGS_UI_TOGGLES.md``):

* **Fail-closed:** arquivo ausente ⇒ defaults (tudo OFF). Arquivo
  ilegível/inválido ⇒ defaults (tudo OFF) **sem exceção** — nunca
  habilitar "por otimismo".
* **Nunca concede permissões:** o store é só dados; a permissão ``TERMINAL``
  (e qualquer level do ``PermissionManager``) jamais é persistida aqui.
* **Sem efeitos colaterais no load:** o arquivo só nasce no primeiro
  ``save``; ``load`` não cria diretórios nem grava nada.
* **Sem secrets:** nenhum conteúdo sensível é lido, escrito ou logado.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("lumen.tools.toggles")

#: Versão do schema atual (política de migração de versões futuras: TBD —
#: SPEC 11H §8). Versões desconhecidas são rejeitadas (fail-closed).
SCHEMA_VERSION = 1

#: Chaves de toggle reconhecidas no MVP 11H.
TOGGLE_KEYS = ("corrections_enabled", "verification_enabled")


class ToggleStoreError(RuntimeError):
    """Falha de escrita da persistência de toggles (discos/permisões)."""


@dataclass
class ToggleState:
    """Estado dos toggles de capacidade da 11H (sem permissões).

    Defaults (arquivo ausente ou inválido): **tudo OFF** — o
    comportamento de app sem persistência é bit-a-bit o atual.
    """

    version: int = SCHEMA_VERSION
    corrections_enabled: bool = False
    verification_enabled: bool = False

    def to_payload(self) -> dict:
        """Serializa para o payload on-disk (schema versionado)."""
        return {
            "version": int(self.version),
            "toggles": {
                "corrections_enabled": bool(self.corrections_enabled),
                "verification_enabled": bool(self.verification_enabled),
            },
        }


class ToggleStore:
    """Persistência fail-closed dos toggles da 11H — JSON local, atômico.

    O arquivo **só nasce no primeiro save** (startup sem efeitos
    colaterais). ``load`` nunca levanta para arquivo inválido: devolve
    :class:`ToggleState` em defaults (fail-closed) e registra aviso — o
    chamador pode depender disso no ``__init__`` do controller.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> ToggleState:
        """Lê o estado persistido; defaults (tudo OFF) se ausente/inválido.

        Nunca levanta: qualquer falha (OS, JSON, schema) ⇒
        :class:`ToggleState` em defaults com aviso no log (fail-closed).
        """
        if not self._path.exists():
            return ToggleState()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(
                "Toggles ignorados (arquivo ilegível, fail-closed): "
                "%s (%s).",
                self._path,
                exc,
            )
            return ToggleState()
        if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
            logger.warning(
                "Toggles ignorados (versão de schema desconhecida "
                "%r, fail-closed): %s.",
                data.get("version") if isinstance(data, dict) else type(data).__name__,
                self._path,
            )
            return ToggleState()
        toggles = data.get("toggles")
        if not isinstance(toggles, dict):
            logger.warning(
                "Toggles ignorados (formato inválido, fail-closed): %s.",
                self._path,
            )
            return ToggleState()
        state = ToggleState()
        for key in TOGGLE_KEYS:
            value = toggles.get(key, False)
            if isinstance(value, bool):
                setattr(state, key, value)
            elif value is not None:
                logger.warning(
                    "Toggle %r ignorado (tipo %s, esperado bool; "
                    "mantido OFF): %s.",
                    key,
                    type(value).__name__,
                    self._path,
                )
        # Chaves desconhecidas são simplesmente ignoradas (forward-compat
        # simples; política formal de migração: TBD — SPEC 11H §8).
        return state

    def save(self, state: ToggleState) -> None:
        """Grava o estado (escrita atômica: tmp + ``os.replace``).

        Cria o diretório de destino se necessário. Falha de disco/OS
        levanta :class:`ToggleStoreError` (o chamador decide — a UI mostra
        o erro; o estado em memória do controller não é rejeitado).
        """
        payload = state.to_payload()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self._path)
        except OSError as exc:
            raise ToggleStoreError(
                f"Falha ao persistir toggles ({self._path}): {exc}"
            ) from exc
        logger.info(
            "Toggles persistidos: corrections=%s verification=%s (%s).",
            state.corrections_enabled,
            state.verification_enabled,
            self._path,
        )
