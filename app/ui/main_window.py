"""Janela principal da Lumen (Tkinter puro, sem dependências externas).

A UI é apenas camada de apresentação: envia o texto ao Agent Core em uma
thread separada (para nunca congelar a janela) e exibe a resposta quando
ela chega por uma fila, via polling com ``after()``. Nenhuma lógica de
negócio vive aqui.

Lumen 0.2: suporte a resposta progressiva (streaming via ``on_delta``),
indicação do provedor ativo e erros exibidos de forma amigável.
"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from collections.abc import Callable

from app import __version__
from app.core.agent import Agent
from app.core.bridge import ToolCallingBridge

logger = logging.getLogger("lumen.ui")


class _Palette:
    """Cores da interface (tema escuro, simples e limpo)."""

    BG = "#0f1218"       # fundo da janela
    PANEL = "#161b26"    # área de conversa
    INPUT = "#1c2230"    # campo de entrada
    TEXT = "#e7eaf2"     # texto principal
    MUTED = "#8a93a8"    # texto secundário
    ACCENT = "#7aa2ff"   # destaque / botões
    USER = "#7aa2ff"     # nome do usuário
    LUMEN = "#5ad1a5"    # nome da Lumen
    OK = "#4cc38a"       # status: pronta
    BUSY = "#e2b93b"     # status: processando
    ERROR = "#e2606f"    # status: erro
    BORDER = "#232a3a"   # bordas


class LumenWindow:
    """Compõe a interface: cabeçalho, área de conversa, entrada e status.

    Args:
        root: janela raiz Tk.
        agent: Agent Core que processa as mensagens.
        on_close: callback opcional executado ao fechar a janela.
    """

    STATUS_TEXT = {
        "ready": ("● Pronta", _Palette.OK),
        "busy": ("● Pensando…", _Palette.BUSY),
        "error": ("● Erro", _Palette.ERROR),
    }

    def __init__(
        self,
        root: tk.Tk,
        agent: Agent,
        on_close: Callable[[], None] | None = None,
        config_service=None,
        tools_controller=None,
    ) -> None:
        self._root = root
        self._agent = agent
        self._on_close = on_close
        self._config_service = config_service
        self._tools_controller = tools_controller
        self._busy = False
        self._status = "ready"
        self._streaming = False
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self._root.title("Lumen")
        self._root.geometry("760x580")
        self._root.minsize(560, 440)
        self._root.configure(bg=_Palette.BG)
        self._root.protocol("WM_DELETE_WINDOW", self._handle_close)

        self._build_layout()
        self._show_welcome()
        self._set_status("ready")
        self._root.after(80, self._poll_queue)
        self.entry.focus_set()
        logger.info("Janela principal construída.")

    # ------------------------------------------------------------------ layout
    def _provider_subtitle(self) -> str:
        """Texto do cabeçalho: versão + provedor/modelo vigentes."""
        provider = getattr(self._agent.provider, "name", "?")
        model = getattr(self._agent.provider, "model_name", "")
        label = f"provedor: {provider}" + (f" · {model}" if model else "")
        if provider == "mock":
            label += " (modo simulado, sem rede)"
        return f"Assistente de IA · v{__version__} · {label}"

    def _refresh_provider_label(self) -> None:
        """Atualiza o cabeçalho após troca de provedor (tela de configurações)."""
        self.subtitle_label.configure(text=self._provider_subtitle())

    def _build_layout(self) -> None:
        header = tk.Frame(self._root, bg=_Palette.BG)
        header.pack(fill=tk.X, padx=18, pady=(14, 2))

        tk.Label(
            header,
            text="L U M E N",
            font=("Segoe UI", 20, "bold"),
            fg=_Palette.TEXT,
            bg=_Palette.BG,
        ).pack(side=tk.LEFT)
        self.status_label = tk.Label(
            header, text="●", fg=_Palette.OK, bg=_Palette.BG, font=("Segoe UI", 10)
        )
        self.status_label.pack(side=tk.RIGHT, anchor=tk.N)

        self.settings_button = tk.Button(
            header,
            text="⚙ Configurações",
            command=self._open_settings,
            bg=_Palette.BG,
            fg=_Palette.MUTED,
            activebackground=_Palette.BG,
            activeforeground=_Palette.TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            padx=6,
            cursor="hand2",
        )
        self.settings_button.pack(side=tk.RIGHT, anchor=tk.N, padx=(0, 12))
        if self._config_service is None:
            self.settings_button.configure(state=tk.DISABLED)

        self.tools_button = tk.Button(
            header,
            text="🛡 Ferramentas",
            command=self._open_tools,
            bg=_Palette.BG,
            fg=_Palette.MUTED,
            activebackground=_Palette.BG,
            activeforeground=_Palette.TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            padx=6,
            cursor="hand2",
        )
        self.tools_button.pack(side=tk.RIGHT, anchor=tk.N, padx=(0, 8))
        if self._tools_controller is None:
            self.tools_button.configure(state=tk.DISABLED)

        self.subtitle_label = tk.Label(
            self._root,
            text=self._provider_subtitle(),
            font=("Segoe UI", 9),
            fg=_Palette.MUTED,
            bg=_Palette.BG,
        )
        self.subtitle_label.pack(anchor=tk.W, padx=20)

        # Área de conversa (somente leitura; escrita via helpers).
        self.conversation = tk.Text(
            self._root,
            state=tk.DISABLED,
            wrap=tk.WORD,
            relief=tk.FLAT,
            bg=_Palette.PANEL,
            fg=_Palette.TEXT,
            insertbackground=_Palette.TEXT,
            padx=14,
            pady=12,
            spacing2=4,
            spacing3=10,
            font=("Segoe UI", 11),
            highlightthickness=1,
            highlightbackground=_Palette.BORDER,
            highlightcolor=_Palette.BORDER,
        )
        self.conversation.pack(fill=tk.BOTH, expand=True, padx=18, pady=(10, 8))
        self.conversation.tag_configure("user_name", foreground=_Palette.USER, font=("Segoe UI", 10, "bold"))
        self.conversation.tag_configure("user_text", foreground=_Palette.TEXT)
        self.conversation.tag_configure("lumen_name", foreground=_Palette.LUMEN, font=("Segoe UI", 10, "bold"))
        self.conversation.tag_configure("lumen_text", foreground=_Palette.TEXT)
        self.conversation.tag_configure("meta", foreground=_Palette.MUTED, font=("Segoe UI", 9, "italic"))
        self.conversation.tag_configure("error", foreground=_Palette.ERROR, font=("Segoe UI", 10, "italic"))

        # Entrada de mensagem + botão enviar.
        footer = tk.Frame(self._root, bg=_Palette.BG)
        footer.pack(fill=tk.X, padx=18, pady=(0, 14))

        self.entry = tk.Entry(
            footer,
            bg=_Palette.INPUT,
            fg=_Palette.TEXT,
            insertbackground=_Palette.TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 11),
            highlightthickness=1,
            highlightbackground=_Palette.BORDER,
            highlightcolor=_Palette.ACCENT,
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 10))
        self.entry.bind("<Return>", lambda _event: self.send())

        self.send_button = tk.Button(
            footer,
            text="Enviar",
            command=self.send,
            bg=_Palette.ACCENT,
            fg="#0d1220",
            activebackground="#9db8ff",
            activeforeground="#0d1220",
            disabledforeground="#6b7387",
            relief=tk.FLAT,
            font=("Segoe UI", 10, "bold"),
            padx=16,
            cursor="hand2",
        )
        self.send_button.pack(side=tk.LEFT, ipady=6)

    def _show_welcome(self) -> None:
        self._append_message("lumen", "Olá! Eu sou a Lumen. Como posso ajudar?")
        self._append_line("A conversa é salva localmente em data/memory/conversation.json.", tag="meta")

    # ---------------------------------------------------------------- eventos
    def _open_settings(self) -> None:
        """Abre a tela ⚙ Configurações → Inteligência Artificial."""
        if self._config_service is None:
            return
        from app.ui.settings_dialog import SettingsDialog

        SettingsDialog(self._root, self._config_service,
                       on_saved=self._refresh_provider_label)

    def _open_tools(self) -> None:
        """Abre a tela 🛡 Ferramentas e Segurança (workspaces/permissões/
        aprovações/auditoria — 0.5.x)."""
        if self._tools_controller is None:
            return
        from app.ui.tools_dialog import ToolsDialog

        ToolsDialog(
            self._root, self._tools_controller,
            on_plan_finished=self._on_plan_finished,
        )

    def _on_plan_finished(self, report) -> None:
        """Exibe no chat o desfecho final de um plano (0.6.6).

        Chamado pela tela 🛡 depois de APROVAR/RECUSAR um checkpoint:
        formata o ``ExecutionReport`` com o MESMO formatador do bridge
        (nenhuma lógica nova), injeta a mensagem na fila existente da
        conversa e registra o desfecho na memória linear (pelo bridge —
        o caminho apropriado). Falhas aqui não afetam o diálogo.
        """
        if self._tools_controller is None:
            return
        try:
            bridge = ToolCallingBridge(self._agent, self._tools_controller)
            outcome = bridge.outcome_for_report(None, report.plan_id, report)
            self._queue.put(("reply", outcome.text))
        except Exception:
            logger.exception("Falha ao formatar desfecho do plano.")

    def send(self) -> None:
        """Envia o conteúdo do campo de entrada ao Agent Core."""
        if self._busy:
            return
        text = self.entry.get().strip()
        if not text:
            return

        self._append_message("user", text)
        self.entry.delete(0, tk.END)
        self._streaming = False
        self._set_busy(True)
        self._set_status("busy")

        # Thread separada: a janela nunca trava, mesmo com provedor lento.
        # on_delta encaminha pedaços de streaming para a fila da UI.
        def emit_delta(chunk: str) -> None:
            self._queue.put(("delta", chunk))

        threading.Thread(
            target=self._worker, args=(text, emit_delta), daemon=True, name="lumen-agent-worker"
        ).start()

    def _worker(self, text: str, emit_delta) -> None:
        """Roda fora da thread da UI; comunica resultados pela fila.

        0.6.3: a mensagem passa por ``process_message`` — o bridge
        decide CONVERSA (fluxo clássico com streaming) × AÇÃO
        (Planner com allowlist → ToolsController → checkpoint →
        execução verificada). O resultado volta como texto pronto.
        """
        try:
            outcome = self._agent.process_message(text, on_delta=emit_delta)
            self._queue.put(("reply", outcome.text))
        except Exception as exc:  # a UI segue viva; o erro é exibido e registrado
            logger.exception("Falha ao processar mensagem do usuário.")
            self._queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        """Drena a fila de resultados (agendado com ``after``)."""
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "delta":
                    if not self._streaming:
                        self._streaming = True
                        self._begin_lumen_block()
                    self._insert_stream_text(payload)
                elif kind == "reply":
                    if self._streaming:
                        # O conteúdo já foi exibido progressivamente.
                        self._end_lumen_block()
                        self._streaming = False
                    else:
                        self._append_message("lumen", payload)
                    self._set_status("ready")
                    self._set_busy(False)
                elif kind == "error":
                    if self._streaming:
                        self._end_lumen_block()
                        self._streaming = False
                    self._append_line(f"⚠ {payload}", tag="error")
                    self._set_status("error")
                    self._set_busy(False)
        except queue.Empty:
            try:
                self._root.after(80, self._poll_queue)
            except tk.TclError:
                pass  # janela destruída
        except tk.TclError:
            logger.debug("Loop de eventos da UI finalizado.")

    # ----------------------------------------------------------------- helpers
    def _append_message(self, speaker: str, text: str) -> None:
        """Adiciona uma mensagem com o nome do falante colorido."""
        self.conversation.config(state=tk.NORMAL)
        try:
            if speaker == "user":
                self.conversation.insert(tk.END, "Você\n", "user_name")
                self.conversation.insert(tk.END, text + "\n\n", "user_text")
            else:
                self.conversation.insert(tk.END, "Lumen\n", "lumen_name")
                self.conversation.insert(tk.END, text + "\n\n", "lumen_text")
            self.conversation.see(tk.END)
        finally:
            self.conversation.config(state=tk.DISABLED)

    def _begin_lumen_block(self) -> None:
        """Abre o bloco 'Lumen:' antes do primeiro pedaço de streaming."""
        self.conversation.config(state=tk.NORMAL)
        try:
            self.conversation.insert(tk.END, "Lumen\n", "lumen_name")
            self.conversation.see(tk.END)
        finally:
            self.conversation.config(state=tk.DISABLED)

    def _insert_stream_text(self, chunk: str) -> None:
        """Anexa um pedaço de texto ao bloco de streaming aberto."""
        self.conversation.config(state=tk.NORMAL)
        try:
            self.conversation.insert(tk.END, chunk, "lumen_text")
            self.conversation.see(tk.END)
        finally:
            self.conversation.config(state=tk.DISABLED)

    def _end_lumen_block(self) -> None:
        """Fecha o bloco de streaming (espaçamento final)."""
        self.conversation.config(state=tk.NORMAL)
        try:
            self.conversation.insert(tk.END, "\n\n", "lumen_text")
            self.conversation.see(tk.END)
        finally:
            self.conversation.config(state=tk.DISABLED)

    def _append_line(self, text: str, tag: str = "meta") -> None:
        self.conversation.config(state=tk.NORMAL)
        try:
            self.conversation.insert(tk.END, text + "\n\n", tag)
            self.conversation.see(tk.END)
        finally:
            self.conversation.config(state=tk.DISABLED)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.send_button.config(state=state)
        self.entry.config(state=state)
        if not busy:
            self.entry.focus_set()

    def _set_status(self, status: str) -> None:
        self._status = status
        text, color = self.STATUS_TEXT.get(status, self.STATUS_TEXT["ready"])
        self.status_label.config(text=text, fg=color)

    # --------------------------------------------------------------- ciclo vida
    def run(self) -> None:
        """Entra no mainloop do Tk (bloqueante)."""
        logger.info("Mainloop da interface iniciado.")
        self._root.mainloop()

    def _handle_close(self) -> None:
        logger.info("Janela fechada pelo usuário.")
        if self._on_close is not None:
            try:
                self._on_close()
            except Exception:
                logger.exception("Falha no callback de encerramento.")
        self._root.destroy()
