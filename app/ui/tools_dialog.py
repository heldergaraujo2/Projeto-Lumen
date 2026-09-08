"""Tela "🛡 Ferramentas e Segurança" da Lumen (0.5.x).

Camada **visual** para o :class:`~app.tools.control.ToolsController`:
workspaces autorizados, permissões (CHAT/READ/WRITE + DELETE por
workspace), aprovação de checkpoints de operações destrutivas e a trilha
de auditoria. Toda a lógica/mensagem de negócio vive no controller —
aqui é apresentação e ações claras.

Clareza de UX (o usuário sempre vê): **o que** a Lumen quer fazer,
**onde** (workspace/caminho), **qual ferramenta**, **qual permissão** e
**se precisa de aprovação**.
"""
from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import messagebox

from app.tools.control import ToolsController

logger = logging.getLogger("lumen.ui.tools")

_OK_GREEN = "#4cc38a"
_ERR_RED = "#e2606f"
_WARN = "#e2b93b"
_MUTED = "#8a93a8"
_PANEL = "#161b26"
_TEXT = "#e7eaf2"

_AUDIT_LIMIT = 200


class ToolsDialog:
    """Diálogo de workspaces, permissões, aprovações e auditoria."""

    def __init__(
        self,
        parent: tk.Misc,
        controller: ToolsController,
        on_plan_finished=None,
    ) -> None:
        self._controller = controller
        #: Callback opcional ``on_plan_finished(report)`` (0.6.6): recebe o
        #: ``ExecutionReport`` depois de APROVAR/RECUSAR para a janela
        #: principal exibir o desfecho no chat. ``None`` (default) mantém o
        #: comportamento anterior — o diálogo segue autônomo.
        self._on_plan_finished = on_plan_finished
        self._add_writable = False
        self._add_allow_delete = False

        self.top = tk.Toplevel(parent)
        self.top.title("Ferramentas e Segurança")
        self.top.geometry("640x680")  # +60: seção Automação (11H)
        self.top.configure(bg=_PANEL)
        self.top.transient(parent)

        tk.Label(
            self.top, text="FERRAMENTAS E SEGURANÇA",
            font=("Segoe UI", 13, "bold"), fg=_TEXT, bg=_PANEL,
        ).pack(anchor=tk.W, padx=18, pady=(14, 2))
        tk.Label(
            self.top,
            text="Nada é acessível até você autorizar um diretório (workspace) "
                 "e conceder a permissão correspondente.",
            fg=_MUTED, bg=_PANEL, font=("Segoe UI", 9), justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=18, pady=(0, 8))

        self.status_label = tk.Label(
            self.top, text="", fg=_MUTED, bg=_PANEL,
            font=("Segoe UI", 9), justify=tk.LEFT,
        )
        self.status_label.pack(anchor=tk.W, padx=18)

        self._build_approval_section()
        self._build_workspaces_section()
        self._build_permissions_section()
        self._build_terminal_section()
        self._build_automation_section()  # 11H: toggles persistentes
        self._build_audit_section()

        self.close_button = tk.Button(
            self.top, text="Fechar", relief=tk.FLAT, cursor="hand2",
            bg=_PANEL, fg=_MUTED, font=("Segoe UI", 10),
            command=self._close,
        )
        self.close_button.pack(anchor=tk.E, padx=18, pady=(8, 14))

        self.refresh()
        logger.info("Tela de Ferramentas e Segurança aberta.")

    # ------------------------------------------------------------ aprovação
    def _build_approval_section(self) -> None:
        tk.Label(self.top, text="APROVAÇÃO", font=("Segoe UI", 10, "bold"),
                 fg=_TEXT, bg=_PANEL).pack(anchor=tk.W, padx=18, pady=(6, 2))
        self.pending_label = tk.Label(
            self.top, text="Nenhuma operação aguardando aprovação.",
            fg=_MUTED, bg=_PANEL, font=("Segoe UI", 10),
            justify=tk.LEFT, wraplength=590,
        )
        self.pending_label.pack(anchor=tk.W, padx=18)
        buttons = tk.Frame(self.top, bg=_PANEL)
        buttons.pack(anchor=tk.W, padx=18, pady=(4, 6))
        self.approve_button = tk.Button(
            buttons, text="✔ APROVAR", relief=tk.FLAT, cursor="hand2",
            bg=_OK_GREEN, fg="#0d1220", font=("Segoe UI", 10, "bold"),
            state=tk.DISABLED, command=self._approve_with_popup_for_cc_click,
        )
        self.approve_button.pack(side=tk.LEFT, padx=(0, 8))
        self.refuse_button = tk.Button(
            buttons, text="✖ RECUSAR", relief=tk.FLAT, cursor="hand2",
            bg=_ERR_RED, fg="#0d1220", font=("Segoe UI", 10, "bold"),
            state=tk.DISABLED, command=self._refuse,
        )
        self.refuse_button.pack(side=tk.LEFT)

        self.open_screenshot_button = tk.Button(
            buttons, text="?? ABRIR SCREENSHOT", relief=tk.FLAT, cursor="hand2",
            bg="#7aa2ff", fg="#0d1220", font=("Segoe UI", 10, "bold"),
            state=tk.DISABLED, command=self._open_last_cc_screenshot,
        )
        self.open_screenshot_button.pack(side=tk.LEFT, padx=(8, 0))

    def _refresh_pending(self) -> None:
        pending = self._controller.pending_approval()
        if pending is None:
            self.pending_label.configure(
                text="Nenhuma operação aguardando aprovação.", fg=_MUTED,
            )
            self.approve_button.configure(state=tk.DISABLED)
            self.refuse_button.configure(state=tk.DISABLED)
            self.open_screenshot_button.configure(state=tk.DISABLED)
            return
        where = pending.get("requested_path") or "?"
        if pending.get("resolved_path"):
            where = (
                f"{where} → {pending['resolved_path']} "
                f"(workspace: {pending.get('workspace') or '?'})"
            )
        elif pending.get("preview_error"):
            where = f"{where} (⚠ {pending['preview_error']})"
        if pending.get("kind") == "correction":
            original = pending.get("original_tool") or "?"
            corrected = pending.get("tool") or "?"
            failure = pending.get("preview_error") or "?"
            kind = pending.get("failure_kind") or "?"
            kind_label = ("verificação" if kind == "verification"
                          else "execução")
            original_params = pending.get("original_parameters") or {}
            corrected_params = pending.get("corrected_parameters") or {}
            text = (
                "⚠ CORREÇÃO PROPOSTA AGUARDANDO APROVAÇÃO — nada é "
                "aplicado antes da sua decisão\n"
                f"O que: {pending.get('description') or '?'}\n"
                f"Falha de {kind_label}: {failure}\n"
                f"Ferramenta: {original} → {corrected}\n"
                f"Parâmetros: {original_params or '—'} → "
                f"{corrected_params or '—'}\n"
                f"Aprovar aplica a correção e executa de novo (com "
                "checkpoint da operação); Recusar mantém a falha — nada "
                "é executado."
            )
            # CC UX: corre??o proposta n?o tem screenshot associado.
            if hasattr(self, "open_screenshot_button"):
                self.open_screenshot_button.configure(state=tk.DISABLED)
            self.pending_label.configure(text=text, fg=_WARN)
            self.approve_button.configure(state=tk.NORMAL)
            self.refuse_button.configure(state=tk.NORMAL)
            return
        text = (
            "⚠ OPERAÇÃO AGUARDANDO APROVAÇÃO — nada é executado antes da sua decisão\n"
            f"O que: {pending.get('description') or '?'}\n"
            f"Ferramenta: {pending.get('tool') or '?'} · "
            f"Operação: {pending.get('operation_label') or '?'} · "
            f"Permissão: {pending.get('permission') or '?'}\n"
            f"Onde: {where}"
        )
        if pending.get("content_preview"):
            # 0.6.3: conteúdo a gravar (create_file/write_file) no card.
            text += f"\nConteúdo: {pending['content_preview']}"
        if pending.get("command"):
            # Terminal (0.6/0.6.x): comando, argumentos, cwd e timeout.
            argv = list(pending["command"])
            text += f"\nComando: {argv[0] if argv else '?'}"
            if len(argv) > 1:
                text += f"\nArgumentos: {' '.join(argv[1:])}"
            if pending.get("resolved_path"):
                text += f"\nDiretório de trabalho: {pending['resolved_path']}"
            timeout = pending.get("timeout_s")
            if timeout is not None:
                text += f"\nTimeout: {timeout}s"
        tool = pending.get("tool")
        if tool in ("cc_mouse_click", "cc_mouse_click_at"):
            self.open_screenshot_button.configure(state=tk.NORMAL)
        else:
            self.open_screenshot_button.configure(state=tk.DISABLED)
        self.pending_label.configure(text=text, fg=_WARN)
        self.approve_button.configure(state=tk.NORMAL)
        self.refuse_button.configure(state=tk.NORMAL)

    def _open_last_cc_screenshot(self) -> None:
        """Abre o ?ltimo artifact_ref de cc_screenshot (se existir)."""
        records = self._controller.audit_records(limit=_AUDIT_LIMIT)
        last = None
        for rec in reversed(records):
            if rec.get("tool") == "cc_screenshot" and rec.get("success") is True:
                last = rec
                break
        if not last:
            self._set_status(False, "?? Nenhum screenshot encontrado na auditoria.")
            return
        artifact = last.get("artifact_ref")
        if not artifact and isinstance(last.get("detail"), dict):
            artifact = last["detail"].get("artifact_ref")
        if not artifact or not isinstance(artifact, str):
            self._set_status(False, "?? Screenshot sem artifact_ref.")
            return
        try:
            os.startfile(artifact)  # Windows
            self._set_status(True, f"?? Screenshot aberto: {artifact}")
        except Exception as exc:
            self._set_status(False, f"?? N?o foi poss?vel abrir o screenshot: {exc}")

    def _approve_with_popup_for_cc_click(self) -> None:
        """UI safety: approval popup for CC click tools.

        Rationale: if user clicks the APPROVE button with the mouse, the cursor is on the UI.
        For CC click actions we want the user to position the cursor on the real target and
        confirm with Enter (no mouse movement).
        """
        pending = self._controller.pending_approval() or {}
        tool = pending.get("tool")
        if tool not in ("cc_mouse_click", "cc_mouse_click_at"):
            self._approve()
            return

        win = tk.Toplevel(self.top)
        win.title("Confirmar click (Computer Control)")
        win.configure(bg=_PANEL)
        win.geometry("520x180+120+120")
        win.transient(self.top)
        win.grab_set()

        msg = (
            "COMPUTER CONTROL ? confirma??o\n\n"
            "1) Posicione o mouse no ALVO (ex.: ?cone do arquivo).\n"
            "2) Pressione ENTER para APROVAR e executar o click.\n"
            "ESC cancela."
        )
        tk.Label(win, text=msg, fg=_TEXT, bg=_PANEL, justify=tk.LEFT,
                 font=("Segoe UI", 10), wraplength=500).pack(anchor=tk.W, padx=16, pady=12)

        buttons = tk.Frame(win, bg=_PANEL)
        buttons.pack(anchor=tk.E, padx=16, pady=(0, 12))

        def _do_approve():
            try:
                win.grab_release()
                win.destroy()
            except Exception:
                pass
            self._approve()

        def _cancel():
            try:
                win.grab_release()
                win.destroy()
            except Exception:
                pass

        b_ok = tk.Button(
            buttons, text="? APROVAR (ENTER)", relief=tk.FLAT, cursor="hand2",
            bg=_OK_GREEN, fg="#0d1220", font=("Segoe UI", 10, "bold"),
            command=_do_approve,
        )
        b_ok.pack(side=tk.RIGHT, padx=(8, 0))

        b_cancel = tk.Button(
            buttons, text="Cancelar (ESC)", relief=tk.FLAT, cursor="hand2",
            bg=_ERR_RED, fg="#0d1220", font=("Segoe UI", 10, "bold"),
            command=_cancel,
        )
        b_cancel.pack(side=tk.RIGHT)

        win.bind("<Return>", lambda e: _do_approve())
        win.bind("<Escape>", lambda e: _cancel())
        b_ok.focus_set()

    def _approve(self) -> None:
        try:
            report = self._controller.approve()
        except Exception as exc:  # nunca traceback na UI
            logger.exception("Falha ao aprovar operação.")
            self._set_status(False, f"🔴 Não foi possível aprovar: {exc}")
            self._refresh_pending()
            return
        self._set_status(
            True,
            f"🟢 Aprovada e executada (plano: {report.status.value}).",
        )
        self.refresh()
        self._notify_plan_finished(report)

    def _notify_plan_finished(self, report) -> None:
        """Entrega o desfecho do plano ao callback (janela principal).

        Falhas do callback NÃO afetam o diálogo (apenas log) — a
        execução já aconteceu (ou foi bloqueada) no controller.
        """
        if self._on_plan_finished is None:
            return
        try:
            self._on_plan_finished(report)
        except Exception:
            logger.exception("Falha ao notificar desfecho do plano.")

    def _refuse(self) -> None:
        try:
            report = self._controller.refuse()
        except Exception as exc:
            logger.exception("Falha ao recusar operação.")
            self._set_status(False, f"🔴 Não foi possível recusar: {exc}")
            self._refresh_pending()
            return
        self._set_status(
            True,
            f"🟢 Recusada — a operação NÃO foi executada "
            f"(plano: {report.status.value}).",
        )
        self.refresh()
        self._notify_plan_finished(report)

    # ------------------------------------------------------------ workspaces
    def _build_workspaces_section(self) -> None:
        tk.Label(self.top, text="WORKSPACES AUTORIZADOS",
                 font=("Segoe UI", 10, "bold"), fg=_TEXT, bg=_PANEL,
                 ).pack(anchor=tk.W, padx=18, pady=(6, 2))
        self.ws_frame = tk.Frame(self.top, bg=_PANEL)
        self.ws_frame.pack(fill=tk.X, padx=18)
        self.ws_rows: list[dict] = []
        self._empty_ws_label = tk.Label(
            self.ws_frame, text="Nenhum diretório autorizado.",
            fg=_MUTED, bg=_PANEL, font=("Segoe UI", 9),
        )

        add_row = tk.Frame(self.top, bg=_PANEL)
        add_row.pack(fill=tk.X, padx=18, pady=(4, 2))
        self.path_entry = tk.Entry(add_row)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                             ipady=4, padx=(0, 8))
        self.write_toggle = tk.Button(
            add_row, text="Escrita: NÃO", relief=tk.FLAT, cursor="hand2",
            bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9),
            command=self._toggle_write,
        )
        self.write_toggle.pack(side=tk.LEFT, padx=(0, 6))
        self.delete_toggle = tk.Button(
            add_row, text="Exclusão: NÃO", relief=tk.FLAT, cursor="hand2",
            bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9),
            command=self._toggle_delete,
        )
        self.delete_toggle.pack(side=tk.LEFT, padx=(0, 6))
        self.add_button = tk.Button(
            add_row, text="Adicionar", relief=tk.FLAT, cursor="hand2",
            bg="#7aa2ff", fg="#0d1220", font=("Segoe UI", 10, "bold"),
            command=self._add_workspace,
        )
        self.add_button.pack(side=tk.LEFT)

    def _toggle_write(self) -> None:
        self._add_writable = not self._add_writable
        if not self._add_writable:
            self._add_allow_delete = False
        self._refresh_add_toggles()

    def _toggle_delete(self) -> None:
        self._add_allow_delete = not self._add_allow_delete
        if self._add_allow_delete:
            self._add_writable = True
        self._refresh_add_toggles()

    def _refresh_add_toggles(self) -> None:
        self.write_toggle.configure(
            text=f"Escrita: {'SIM' if self._add_writable else 'NÃO'}",
            fg=_OK_GREEN if self._add_writable else _MUTED,
        )
        self.delete_toggle.configure(
            text=f"Exclusão: {'SIM' if self._add_allow_delete else 'NÃO'}",
            fg=_OK_GREEN if self._add_allow_delete else _MUTED,
        )

    def _refresh_workspaces(self) -> None:
        for row in self.ws_rows:
            for widget in row["widgets"]:
                widget.destroy()
        self.ws_rows = []
        workspaces = self._controller.list_workspaces()
        if not workspaces:
            self._empty_ws_label.pack(anchor=tk.W)
        else:
            self._empty_ws_label.pack_forget()
        for item in workspaces:
            line = tk.Frame(self.ws_frame, bg=_PANEL)
            line.pack(fill=tk.X, pady=1)
            label = tk.Label(
                line, text=f"📁 {item['root']} — {item['mode']}",
                fg=_TEXT, bg=_PANEL, font=("Segoe UI", 9),
            )
            label.pack(side=tk.LEFT)
            remove = tk.Button(
                line, text="Remover", relief=tk.FLAT, cursor="hand2",
                fg=_ERR_RED, bg=_PANEL, font=("Segoe UI", 9),
                command=lambda root=item["root"]: self._remove_workspace(root),
            )
            remove.pack(side=tk.RIGHT)
            self.ws_rows.append({
                "root": item["root"], "mode": item["mode"],
                "widgets": (line, label, remove), "remove_button": remove,
            })

    def _add_workspace(self) -> None:
        path = self.path_entry.get().strip()
        try:
            info = self._controller.add_workspace(
                path, writable=self._add_writable,
                allow_delete=self._add_allow_delete,
            )
        except Exception as exc:
            self._set_status(False, f"🔴 {exc}")
            return
        self.path_entry.delete(0, tk.END)
        self._add_writable = self._add_allow_delete = False
        self._refresh_add_toggles()
        self._set_status(True, f"🟢 Workspace autorizado: {info['root']} ({info['mode']}).")
        self.refresh()

    def _remove_workspace(self, root: str) -> None:
        if not messagebox.askyesno(
            "Lumen", f"Remover a autorização do workspace?\n{root}"
        ):
            return
        try:
            self._controller.remove_workspace(root)
        except Exception as exc:
            self._set_status(False, f"🔴 {exc}")
            return
        self._set_status(True, f"🟢 Autorização removida: {root}.")
        self.refresh()

    # ------------------------------------------------------------ permissões
    def _build_permissions_section(self) -> None:
        tk.Label(self.top, text="PERMISSÕES", font=("Segoe UI", 10, "bold"),
                 fg=_TEXT, bg=_PANEL).pack(anchor=tk.W, padx=18, pady=(6, 2))
        self.perm_frame = tk.Frame(self.top, bg=_PANEL)
        self.perm_frame.pack(fill=tk.X, padx=18)
        self.perm_rows: dict[str, dict] = {}
        for level, hint in (
            ("CHAT", "Conversar (padrão: sempre ativa)"),
            ("READ", "Ler arquivos dos workspaces"),
            ("WRITE", "Criar/modificar arquivos dos workspaces"),
        ):
            line = tk.Frame(self.perm_frame, bg=_PANEL)
            line.pack(fill=tk.X, pady=1)
            status = tk.Label(line, text="", fg=_MUTED, bg=_PANEL,
                              font=("Segoe UI", 9))
            status.pack(side=tk.LEFT)
            action = tk.Button(
                line, text="", relief=tk.FLAT, cursor="hand2",
                bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9),
                command=lambda name=level: self._toggle_permission(name),
            )
            action.pack(side=tk.RIGHT)
            tk.Label(line, text=hint, fg=_MUTED, bg=_PANEL,
                     font=("Segoe UI", 8)).pack(side=tk.RIGHT, padx=(0, 8))
            self.perm_rows[level] = {"status": status, "action": action}
        delete_line = tk.Frame(self.perm_frame, bg=_PANEL)
        delete_line.pack(fill=tk.X, pady=1)
        self.delete_status = tk.Label(
            delete_line, text="", fg=_MUTED, bg=_PANEL, font=("Segoe UI", 9),
        )
        self.delete_status.pack(side=tk.LEFT)
        tk.Label(delete_line,
                 text="DELETE = opt-in por workspace (escrita + permitir excluir)",
                 fg=_MUTED, bg=_PANEL, font=("Segoe UI", 8)).pack(side=tk.RIGHT)

    def _refresh_permissions(self) -> None:
        rows = {row["level"]: row for row in self._controller.permission_status()}
        for level in ("CHAT", "READ", "WRITE"):
            granted = rows[level]["granted"]
            self.perm_rows[level]["status"].configure(
                text=("● concedida — " if granted else "○ não concedida — ")
                     + rows[level]["description"],
                fg=_OK_GREEN if granted else _MUTED,
            )
            self.perm_rows[level]["action"].configure(
                text="Revogar" if granted else "Conceder",
                fg=_ERR_RED if granted else _OK_GREEN,
            )
        delete_on = rows["DELETE"]["granted"]
        self.delete_status.configure(
            text=("● ativa em workspace(s) com exclusão permitida"
                  if delete_on else "○ inativa — nenhum workspace com exclusão"),
            fg=_OK_GREEN if delete_on else _MUTED,
        )

    def _toggle_permission(self, level: str) -> None:
        granted = {
            row["level"]: row["granted"]
            for row in self._controller.permission_status()
        }[level]
        try:
            if granted:
                self._controller.revoke_permission(level)
            else:
                self._controller.grant_permission(level)
        except Exception as exc:
            self._set_status(False, f"🔴 {exc}")
            return
        self._set_status(True, f"🟢 Permissão {level} "
                               f"{'revogada' if granted else 'concedida'}.")
        self.refresh()

    # --------------------------------------------------------------- terminal
    def _build_terminal_section(self) -> None:
        header = tk.Frame(self.top, bg=_PANEL)
        header.pack(anchor=tk.W, padx=18, pady=(6, 2), fill=tk.X)
        tk.Label(header, text="TERMINAL (0.6.x)",
                 font=("Segoe UI", 10, "bold"), fg=_TEXT, bg=_PANEL,
                 ).pack(side=tk.LEFT)
        self.disable_terminal_button = tk.Button(
            header, text="Desabilitar terminal", relief=tk.FLAT, cursor="hand2",
            fg=_ERR_RED, bg=_PANEL, font=("Segoe UI", 9),
            command=self._disable_terminal,
        )
        self.disable_terminal_button.pack(side=tk.RIGHT)
        tk.Label(
            self.top,
            text="TERMINAL permite executar APENAS os comandos da allowlist "
                 "abaixo, dentro dos workspaces, com timeout, limite de saída, "
                 "ambiente sem segredos e checkpoint por comando. Shells, "
                 "interpretadores e rede são proibidos permanentemente; a "
                 "concessão vale só nesta sessão.",
            fg=_MUTED, bg=_PANEL, font=("Segoe UI", 8), justify=tk.LEFT,
            wraplength=590,
        ).pack(anchor=tk.W, padx=18)
        term_line = tk.Frame(self.top, bg=_PANEL)
        term_line.pack(fill=tk.X, padx=18, pady=(2, 0))
        self.terminal_status_label = tk.Label(
            term_line, text="", fg=_MUTED, bg=_PANEL, font=("Segoe UI", 9),
        )
        self.terminal_status_label.pack(side=tk.LEFT)
        self.terminal_toggle = tk.Button(
            term_line, text="", relief=tk.FLAT, cursor="hand2",
            bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9),
            command=self._toggle_terminal,
        )
        self.terminal_toggle.pack(side=tk.RIGHT)

        self.term_frame = tk.Frame(self.top, bg=_PANEL)
        self.term_frame.pack(fill=tk.X, padx=18)
        self.term_rows: list[dict] = []
        self._empty_term_label = tk.Label(
            self.term_frame,
            text="Terminal desabilitado — allowlist vazia (nenhum comando "
                 "pode executar).",
            fg=_MUTED, bg=_PANEL, font=("Segoe UI", 9),
        )
        add_row = tk.Frame(self.top, bg=_PANEL)
        add_row.pack(fill=tk.X, padx=18, pady=(4, 2))
        self.cmd_entry = tk.Entry(add_row)
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                            ipady=4, padx=(0, 8))
        self._add_cmd_approval = True
        self.cmd_approval_toggle = tk.Button(
            add_row, text="Aprovação: SIM", relief=tk.FLAT, cursor="hand2",
            bg=_PANEL, fg=_OK_GREEN, font=("Segoe UI", 9),
            command=self._toggle_cmd_approval,
        )
        self.cmd_approval_toggle.pack(side=tk.LEFT, padx=(0, 6))
        self.add_cmd_button = tk.Button(
            add_row, text="Permitir comando", relief=tk.FLAT, cursor="hand2",
            bg="#7aa2ff", fg="#0d1220", font=("Segoe UI", 10, "bold"),
            command=self._add_command,
        )
        self.add_cmd_button.pack(side=tk.LEFT)

    def _toggle_cmd_approval(self) -> None:
        self._add_cmd_approval = not self._add_cmd_approval
        self.cmd_approval_toggle.configure(
            text=f"Aprovação: {'SIM' if self._add_cmd_approval else 'NÃO'}",
            fg=_OK_GREEN if self._add_cmd_approval else _MUTED,
        )

    def _refresh_terminal(self) -> None:
        status = self._controller.terminal_status()
        allowed = self._controller.list_allowed_commands()
        granted = status["permission_granted"]
        self.terminal_status_label.configure(
            text=("● TERMINAL concedida — comandos da allowlist podem ser "
                  "aprovados" if granted else
                  "○ TERMINAL não concedida — nenhum comando executa") +
                 f" · allowlist: {status['allowed_count']} comando(s)",
            fg=_OK_GREEN if granted else _MUTED,
        )
        self.terminal_toggle.configure(
            text="Revogar" if granted else "Conceder",
            fg=_ERR_RED if granted else _OK_GREEN,
        )
        for row in self.term_rows:
            for widget in row["widgets"]:
                widget.destroy()
        self.term_rows = []
        if not allowed:
            self._empty_term_label.configure(
                text=("Allowlist vazia — cadastre um comando para habilitar."
                      if status["enabled"] else
                      "Terminal desabilitado — allowlist vazia (nenhum "
                      "comando pode executar).")
            )
            self._empty_term_label.pack(anchor=tk.W)
        else:
            self._empty_term_label.pack_forget()
        for item in allowed:
            line = tk.Frame(self.term_frame, bg=_PANEL)
            line.pack(fill=tk.X, pady=1)
            approval = ("aprovação obrigatória" if item["requires_approval"]
                        else "executa direto")
            label = tk.Label(
                line,
                text=f"⌨ {item['name']} — {approval} · "
                     f"timeout {item['timeout_s']}s",
                fg=_TEXT, bg=_PANEL, font=("Segoe UI", 9),
            )
            label.pack(side=tk.LEFT)
            remove = tk.Button(
                line, text="Remover", relief=tk.FLAT, cursor="hand2",
                fg=_ERR_RED, bg=_PANEL, font=("Segoe UI", 9),
                command=lambda name=item["name"]: self._remove_command(name),
            )
            remove.pack(side=tk.RIGHT)
            self.term_rows.append({
                "name": item["name"], "widgets": (line, label, remove),
                "remove_button": remove,
            })

    def _toggle_terminal(self) -> None:
        granted = self._controller.terminal_status()["permission_granted"]
        try:
            if granted:
                self._controller.revoke_terminal()
            else:
                self._controller.grant_terminal()
        except Exception as exc:
            self._set_status(False, f"🔴 {exc}")
            return
        self._set_status(
            True,
            f"🟢 Permissão TERMINAL {'revogada' if granted else 'concedida'} "
            f"(explícita; {'comandos seguem bloqueados' if granted else 'sujeitos a allowlist e checkpoints'}).",
        )
        self.refresh()

    def _add_command(self) -> None:
        name = self.cmd_entry.get().strip()
        try:
            info = self._controller.allow_command(
                name, requires_approval=self._add_cmd_approval
            )
        except Exception as exc:
            self._set_status(False, f"🔴 {exc}")
            self.refresh()
            return
        self.cmd_entry.delete(0, tk.END)
        self._set_status(
            True,
            f"🟢 Comando allowlistado: {info['name']} "
            f"({'aprovação obrigatória' if info['requires_approval'] else 'executa direto'}).",
        )
        self.refresh()

    def _remove_command(self, name: str) -> None:
        if not messagebox.askyesno(
            "Lumen", f"Remover o comando da allowlist?\n{name}"
        ):
            return
        try:
            self._controller.remove_allowed_command(name)
        except Exception as exc:
            self._set_status(False, f"🔴 {exc}")
            return
        self._set_status(True, f"🟢 Comando removido da allowlist: {name}.")
        self.refresh()

    def _disable_terminal(self) -> None:
        if not messagebox.askyesno(
            "Lumen",
            "Desabilitar o terminal?\nTodos os comandos da allowlist serão "
            "removidos (a allowlist persistida também é esvaziada).",
        ):
            return
        try:
            self._controller.disable_terminal()
        except Exception as exc:
            self._set_status(False, f"🔴 {exc}")
            return
        self._set_status(True, "🟢 Terminal desabilitado.")
        self.refresh()

    # -------------------------------------------------------- automação (11H)
    def _build_automation_section(self) -> None:
        tk.Label(self.top, text="AUTOMAÇÃO (11H)",
                 font=("Segoe UI", 10, "bold"), fg=_TEXT, bg=_PANEL,
                 ).pack(anchor=tk.W, padx=18, pady=(6, 2))
        tk.Label(
            self.top,
            text="Toggles de CAPACIDADE persistentes: sobrevivem ao "
                 "reinício. Não concedem permissões — TERMINAL e aprovações "
                 "continuam exigidos (concessão vale só nesta sessão).",
            fg=_MUTED, bg=_PANEL, font=("Segoe UI", 8), justify=tk.LEFT,
            wraplength=590,
        ).pack(anchor=tk.W, padx=18)
        self.corrections_toggle = tk.Button(
            self.top, text="Correções automáticas: OFF", relief=tk.FLAT,
            cursor="hand2", bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9),
            anchor="w", command=self._toggle_corrections,
        )
        self.corrections_toggle.pack(fill=tk.X, padx=18, pady=(4, 1))
        self.verification_toggle = tk.Button(
            self.top, text="Verificação real (pytest): OFF", relief=tk.FLAT,
            cursor="hand2", bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9),
            anchor="w", command=self._toggle_verification,
        )
        self.verification_toggle.pack(fill=tk.X, padx=18, pady=(1, 2))

    def _toggle_corrections(self) -> None:
        try:
            self._controller.set_corrections_enabled(
                not self._controller.corrections_enabled
            )
        except Exception as exc:
            self._set_status(False, f"🔴 {exc}")
            return
        self._set_status(
            True,
            "🟢 Correção automática "
            + ("habilitada" if self._controller.corrections_enabled
               else "desabilitada")
            + " (persistida; permissões inalteradas).",
        )
        self.refresh()

    def _toggle_verification(self) -> None:
        try:
            self._controller.set_verification_enabled(
                not self._controller.verification_enabled
            )
        except Exception as exc:
            self._set_status(False, f"🔴 {exc}")
            return
        self._set_status(
            True,
            "🟢 Verificação real "
            + ("habilitada (pytest_result)" if self._controller.verification_enabled
               else "desabilitada")
            + " (persistida; permissões inalteradas).",
        )
        self.refresh()

    def _refresh_automation(self) -> None:
        """11H: reflete o estado do controller nos toggles (fonte única)."""
        for widget, on, name in (
            (self.corrections_toggle,
             self._controller.corrections_enabled,
             "Correções automáticas"),
            (self.verification_toggle,
             self._controller.verification_enabled,
             "Verificação real (pytest)"),
        ):
            widget.configure(
                text=f"{name}: {'ON' if on else 'OFF'}",
                fg=_OK_GREEN if on else _MUTED,
            )

    # ------------------------------------------------------------- auditoria
    def _build_audit_section(self) -> None:
        header = tk.Frame(self.top, bg=_PANEL)
        header.pack(anchor=tk.W, padx=18, pady=(8, 2))
        tk.Label(header, text="AUDITORIA (últimas operações)",
                 font=("Segoe UI", 10, "bold"), fg=_TEXT, bg=_PANEL,
                 ).pack(side=tk.LEFT)
        self.refresh_audit_button = tk.Button(
            header, text="Atualizar", relief=tk.FLAT, cursor="hand2",
            bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9),
            command=self._refresh_audit,
        )
        self.refresh_audit_button.pack(side=tk.RIGHT)
        self.audit_text = tk.Text(
            self.top, height=8, state=tk.DISABLED, wrap=tk.WORD,
            relief=tk.FLAT, bg="#10141d", fg=_TEXT, font=("Consolas", 8),
        )
        self.audit_text.pack(fill=tk.BOTH, expand=True, padx=18, pady=(2, 4))

    def _refresh_audit(self) -> None:
        lines = []
        for record in self._controller.audit_records(limit=_AUDIT_LIMIT):
            outcome = "✓" if record.get("success") else "✗"
            error = f" · erro: {record['error']}" if record.get("error") else ""
            context = (
                f" · {record.get('task_id')}/{record.get('plan_id')}"
                if record.get("task_id") else ""
            )
            lines.append(
                f"{record.get('timestamp', '?')} · {record.get('tool', '?')} · "
                f"{record.get('operation', '?')} · "
                f"{record.get('requested_path') or '?'} → "
                f"{record.get('resolved_path') or '—'} {outcome}{error}{context}"
            )
        body = "\n".join(lines) if lines else "Nenhuma operação registrada."
        self.audit_text.config(state=tk.NORMAL)
        try:
            self.audit_text.delete("1.0", tk.END)
            self.audit_text.insert(tk.END, body)
        finally:
            self.audit_text.config(state=tk.DISABLED)

    # ---------------------------------------------------------------- vários
    def refresh(self) -> None:
        """Re-renderiza todas as seções a partir do controller."""
        self._refresh_pending()
        self._refresh_workspaces()
        self._refresh_permissions()
        self._refresh_terminal()
        self._refresh_automation()  # 11H
        self._refresh_audit()

    def _set_status(self, ok: bool | None, message: str) -> None:
        color = _OK_GREEN if ok else (_ERR_RED if ok is False else _MUTED)
        self.status_label.configure(text=message, fg=color)

    def _close(self) -> None:
        self.top.destroy()
