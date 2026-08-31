"""Tela "⚙ Configurações → Inteligência Artificial" da Lumen.

Permite configurar provider, modelo e API Key sem editar o ``.env``:
testa a conexão com uma requisição mínima e salva através do
:class:`~app.config.config_service.ConfigService`, que persiste os
valores e troca o provider do Agent em tempo de execução.

Regras de segurança da API Key aqui:

- o campo sempre **começa vazio** (a chave salva nunca é exibida);
- ``•••`` por padrão; o botão 👁 mostra/oculta **temporariamente**
  apenas o que o usuário está digitando;
- ao salvar, a chave vai para o cofre (Credential Manager / fallback);
- nada de chave em logs ou arquivos comuns.
"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.ai.provider import available_providers
from app.config.config_service import ConnectionTestResult

if TYPE_CHECKING:
    from app.config.config_service import ConfigService

logger = logging.getLogger("lumen.ui.settings")

_OK_GREEN = "#4cc38a"
_ERR_RED = "#e2606f"
_MUTED = "#8a93a8"
_PANEL = "#161b26"
_TEXT = "#e7eaf2"


class SettingsDialog:
    """Diálogo de configuração de IA (Provider, Modelo, API Key)."""

    def __init__(
        self,
        parent: tk.Misc,
        config_service: "ConfigService",
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        self._service = config_service
        self._on_saved = on_saved
        self._visible = False
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()

        current = config_service.current_config()

        self.top = tk.Toplevel(parent)
        self.top.title("Configurações — Inteligência Artificial")
        self.top.geometry("460x470")
        self.top.configure(bg=_PANEL)
        self.top.transient(parent)

        tk.Label(
            self.top, text="INTELIGÊNCIA ARTIFICIAL", font=("Segoe UI", 13, "bold"),
            fg=_TEXT, bg=_PANEL,
        ).pack(anchor=tk.W, padx=18, pady=(14, 8))

        # ---------------------------------------------------------- Provedor
        tk.Label(self.top, text="Provedor", fg=_MUTED, bg=_PANEL,
                 font=("Segoe UI", 9)).pack(anchor=tk.W, padx=18)
        self.provider_combo = ttk.Combobox(
            self.top, state="readonly", values=list(available_providers())
        )
        self.provider_combo.set(
            current["provider"] if current["provider"] in available_providers()
            else "mock"
        )
        self.provider_combo.pack(fill=tk.X, padx=18, pady=(0, 10))

        # ------------------------------------------------------------ Modelo
        tk.Label(
            self.top,
            text="Modelo (obrigatório p/ openai; ex.: gpt-4o-mini · gemini-2.5-flash · "
                 "openai/gpt-oss-120b (groq) · meta-llama/Llama-4-Scout-17B-16E-Instruct "
                 "(together) — vazio usa o padrão do provedor)",
            fg=_MUTED, bg=_PANEL, font=("Segoe UI", 9),
        ).pack(anchor=tk.W, padx=18)
        self.model_entry = tk.Entry(self.top)
        self.model_entry.insert(0, current.get("model", ""))
        self.model_entry.pack(fill=tk.X, padx=18, pady=(0, 10), ipady=4)

        # ---------------------------------------------------------- API Key
        tk.Label(self.top, text="API Key", fg=_MUTED, bg=_PANEL,
                 font=("Segoe UI", 9)).pack(anchor=tk.W, padx=18)
        key_row = tk.Frame(self.top, bg=_PANEL)
        key_row.pack(fill=tk.X, padx=18, pady=(0, 4))
        self.key_entry = tk.Entry(key_row, show="•")
        self.key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 8))
        self.eye_button = tk.Button(
            key_row, text="👁", width=3, relief=tk.FLAT, cursor="hand2",
            command=self.toggle_key_visibility,
        )
        self.eye_button.pack(side=tk.LEFT)

        self.key_hint = tk.Label(self.top, text="", fg=_MUTED, bg=_PANEL,
                                 font=("Segoe UI", 8))
        self.key_hint.pack(anchor=tk.W, padx=18)
        self._refresh_key_hint(current)

        self.remove_key_button = tk.Button(
            self.top, text="Remover chave salva", relief=tk.FLAT, cursor="hand2",
            fg=_ERR_RED, bg=_PANEL, command=self._remove_key,
        )
        self.remove_key_button.pack(anchor=tk.W, padx=18, pady=(6, 10))

        # ------------------------------------------------------ Teste/Status
        self.test_button = tk.Button(
            self.top, text="TESTAR CONEXÃO", relief=tk.FLAT, cursor="hand2",
            bg="#7aa2ff", fg="#0d1220", font=("Segoe UI", 10, "bold"),
            command=self.test_connection,
        )
        self.test_button.pack(fill=tk.X, padx=18, pady=(4, 4))

        self.status_label = tk.Label(
            self.top, text="Status: —", fg=_MUTED, bg=_PANEL,
            font=("Segoe UI", 10), wraplength=410, justify=tk.LEFT,
        )
        self.status_label.pack(fill=tk.X, padx=18, pady=(4, 12))

        # ------------------------------------------------------------ Salvar
        self.save_button = tk.Button(
            self.top, text="SALVAR", relief=tk.FLAT, cursor="hand2",
            bg=_OK_GREEN, fg="#0d1220", font=("Segoe UI", 10, "bold"),
            command=self.save,
        )
        self.save_button.pack(fill=tk.X, padx=18, pady=(4, 14))

        self._poll_queue()
        logger.info("Tela de configurações de IA aberta.")

    # ------------------------------------------------------------------ chave
    def toggle_key_visibility(self) -> None:
        """Alterna entre ocultar (•••) e mostrar a chave em edição."""
        self._visible = not self._visible
        self.key_entry.configure(show="" if self._visible else "•")

    def _refresh_key_hint(self, current: dict) -> None:
        if current.get("has_stored_key"):
            fonte = current.get("key_source")
            self.key_hint.configure(
                text="Chave salva no cofre da aplicação. Deixe o campo em "
                     f"branco para mantê-la (origem atual: {fonte}). A chave "
                     "salva nunca é exibida."
            )
        elif current.get("key_source") == ".env":
            self.key_hint.configure(
                text="Nenhuma chave no cofre; usando a chave do .env "
                     "(desenvolvimento). Digite uma chave para guardá-la no cofre."
            )
        else:
            self.key_hint.configure(
                text="Nenhuma chave salva. Provedores reais (openai) exigem uma "
                     "API Key; o provedor mock não precisa."
            )

    def _remove_key(self) -> None:
        if not messagebox.askyesno(
            "Lumen", "Remover a API Key salva no cofre da aplicação?"
        ):
            return
        try:
            message = self._service.remove_api_key()
        except Exception as exc:
            logger.exception("Falha ao remover a chave.")
            self._set_status(False, f"🔴 Não foi possível remover a chave: {exc}")
            return
        self._set_status(True, f"🟢 {message}")
        self._refresh_key_hint(self._service.current_config())

    # ------------------------------------------------------------ conexão
    def test_connection(self) -> None:
        """Testa a conexão em uma thread (a janela nunca congela)."""
        provider = self.provider_combo.get()
        model = self.model_entry.get()
        key = self.key_entry.get().strip() or None
        self.test_button.configure(state=tk.DISABLED)
        self._set_status(None, "Testando conexão…")

        def run() -> None:
            try:
                result = self._service.test_connection(provider, model, key)
                self._queue.put(("test", result))
            except Exception as exc:  # defensivo: nunca traceback na UI
                logger.exception("Falha inesperada no teste de conexão.")
                self._queue.put(
                    ("test", ConnectionTestResult(False, f"🔴 Erro inesperado: {exc}"))
                )

        threading.Thread(target=run, daemon=True, name="lumen-test-connection").start()

    # ------------------------------------------------------------- salvar
    def save(self) -> None:
        provider = self.provider_combo.get()
        model = self.model_entry.get()
        key = self.key_entry.get()

        if provider == "openai" and not model.strip():
            self._set_status(
                False,
                "🔴 Informe o modelo para o provedor openai (ex.: gpt-4o-mini).",
            )
            return

        try:
            self._service.save(provider, model.strip(), api_key=key)
        except ValueError as exc:  # InvalidAIConfig — mensagem amigável
            self._set_status(False, f"🔴 {exc}")
            return
        except Exception as exc:
            logger.exception("Falha ao salvar configuração de IA.")
            self._set_status(False, f"🔴 Não foi possível salvar: {exc}")
            return

        # Limpa o campo: a chave digitada não permanece exposta na tela.
        self.key_entry.delete(0, tk.END)
        self._set_status(True, "🟢 Configuração salva e aplicada à conversa.")
        self._refresh_key_hint(self._service.current_config())
        if self._on_saved is not None:
            try:
                self._on_saved()
            except Exception:
                logger.exception("Callback on_saved falhou.")

    # ------------------------------------------------------------- helpers
    def _set_status(self, ok: bool | None, message: str) -> None:
        color = _OK_GREEN if ok else (_ERR_RED if ok is False else _MUTED)
        self.status_label.configure(text=f"Status: {message}", fg=color)

    def _poll_queue(self) -> None:
        """Drena resultados das threads de teste (agendado com ``after``)."""
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "test":
                    self._set_status(payload.ok, payload.message)
                    self.test_button.configure(state=tk.NORMAL)
        except queue.Empty:
            pass
        except tk.TclError:  # pragma: no cover - diálogo destruído
            return
        try:
            self.top.after(100, self._poll_queue)
        except tk.TclError:  # pragma: no cover
            pass
