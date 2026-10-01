"""Painel operacional da Lumen.

Centro visual read-only para diagnosticar runtime e capacidades, com atalhos
para as superfícies que alteram estado. Nenhum diagnóstico concede permissão,
cria escopo, arma driver ou inicia serviço externo.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.runtime.plugins import PluginReport

_BG = "#0f1218"
_PANEL = "#161b26"
_TEXT = "#e7eaf2"
_MUTED = "#8a93a8"
_OK = "#4cc38a"
_WARN = "#e2b93b"
_ERR = "#e2606f"
_ACCENT = "#7aa2ff"


class OperationsDialog:
    """Painel operacional com abas de runtime e capacidades da Lumen."""

    TABS = (
        "Runtime",
        "Computer Control",
        "Web Research",
        "Unreal Integration",
        "Ollama",
        "Unreal MCP",
        "Ferramentas / Aprovações",
        "Configurações",
    )

    def __init__(self, parent, *, agent, config_service=None,
                 tools_controller=None, plugin_reports=(), on_provider_saved=None):
        self._parent = parent
        self._agent = agent
        self._config_service = config_service
        self._tools_controller = tools_controller
        self._plugin_reports = tuple(plugin_reports)
        self._on_provider_saved = on_provider_saved

        self.top = tk.Toplevel(parent)
        self.top.title("Lumen — Painel Operacional")
        self.top.geometry("900x650")
        self.top.minsize(760, 520)
        self.top.configure(bg=_BG)
        self.top.transient(parent)

        header = tk.Frame(self.top, bg=_BG)
        header.pack(fill=tk.X, padx=18, pady=(14, 8))
        tk.Label(header, text="PAINEL OPERACIONAL", font=("Segoe UI", 15, "bold"),
                 fg=_TEXT, bg=_BG).pack(side=tk.LEFT)
        tk.Label(header, text="Diagnóstico + controle explícito", font=("Segoe UI", 9),
                 fg=_MUTED, bg=_BG).pack(side=tk.RIGHT)

        self.notebook = ttk.Notebook(self.top)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))

        self._frames = {}
        for name in self.TABS:
            frame = tk.Frame(self.notebook, bg=_PANEL)
            self.notebook.add(frame, text=name)
            self._frames[name] = frame

        self._build_runtime()
        self._build_capability("Computer Control", "computer_control")
        self._build_capability("Web Research", "web_research")
        self._build_capability("Unreal Integration", "unreal")
        self._build_capability("Ollama", "ollama")
        self._build_capability("Unreal MCP", "mcp")
        self._build_tools()
        self._build_settings()

        self._refresh_all()
        self.top.after(1000, self._poll_refresh)

    def _report(self, plugin_id: str) -> PluginReport | None:
        return next((r for r in self._plugin_reports if r.descriptor.id == plugin_id), None)

    def _status_text(self, report):
        if report is None:
            return "🔴 NÃO DETECTADO", _ERR
        status = report.status.value
        if status == "AVAILABLE":
            return "🟢 DISPONÍVEL", _OK
        if status == "DEGRADED":
            return "🟡 DEGRADADO", _WARN
        return "🔴 INDISPONÍVEL", _ERR

    def _card(self, parent, title, description):
        tk.Label(parent, text=title, font=("Segoe UI", 13, "bold"),
                 fg=_TEXT, bg=_PANEL).pack(anchor=tk.W, padx=20, pady=(18, 2))
        tk.Label(parent, text=description, font=("Segoe UI", 9),
                 fg=_MUTED, bg=_PANEL, justify=tk.LEFT, wraplength=780).pack(
                     anchor=tk.W, padx=20, pady=(0, 10))

    def _build_runtime(self):
        f = self._frames["Runtime"]
        self._card(f, "Runtime da Lumen",
                   "Componentes detectados no processo atual. Esta tela é somente diagnóstico.")
        self.runtime_text = tk.Text(f, height=18, state=tk.DISABLED, wrap=tk.WORD,
                                    bg="#10141d", fg=_TEXT, relief=tk.FLAT,
                                    font=("Consolas", 10))
        self.runtime_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=8)
        tk.Button(f, text="Atualizar diagnóstico", command=self._refresh_runtime,
                  relief=tk.FLAT, bg=_ACCENT, fg="#0d1220").pack(
                      anchor=tk.E, padx=20, pady=10)

    def _build_capability(self, tab, plugin_id):
        f = self._frames[tab]
        report = self._report(plugin_id)
        title = report.descriptor.name if report else tab
        desc = report.descriptor.description if report else "Componente não encontrado no runtime."
        self._card(f, title, desc)
        self._cap_status = getattr(self, "_cap_status", {})
        self._cap_detail = getattr(self, "_cap_detail", {})
        self._cap_status[plugin_id] = tk.Label(
            f, text="", font=("Segoe UI", 12, "bold"), fg=_MUTED, bg=_PANEL)
        self._cap_status[plugin_id].pack(anchor=tk.W, padx=20, pady=6)
        self._cap_detail[plugin_id] = tk.Label(
            f, text="", font=("Segoe UI", 9), fg=_MUTED, bg=_PANEL,
            justify=tk.LEFT, wraplength=780)
        self._cap_detail[plugin_id].pack(anchor=tk.W, padx=20, pady=2)

        if plugin_id == "computer_control":
            self._build_cc_details(f)
        elif plugin_id == "web_research":
            self._build_web_details(f)
        elif plugin_id == "unreal":
            self._build_unreal_details(f)

    def _build_cc_details(self, f):
        self.cc_details = tk.Label(f, text="", font=("Segoe UI", 9),
                                   fg=_TEXT, bg=_PANEL, justify=tk.LEFT)
        self.cc_details.pack(anchor=tk.W, padx=20, pady=12)

    def _build_web_details(self, f):
        self.web_details = tk.Label(f, text="", font=("Segoe UI", 9),
                                    fg=_TEXT, bg=_PANEL, justify=tk.LEFT)
        self.web_details.pack(anchor=tk.W, padx=20, pady=12)

    def _build_unreal_details(self, f):
        self.unreal_details = tk.Label(f, text="", font=("Segoe UI", 9),
                                       fg=_TEXT, bg=_PANEL, justify=tk.LEFT,
                                       wraplength=780)
        self.unreal_details.pack(anchor=tk.W, padx=20, pady=12)

    def _build_tools(self):
        f = self._frames["Ferramentas / Aprovações"]
        self._card(f, "Ferramentas e Aprovações",
                   "A autoridade continua no ToolsController. Esta aba abre a superfície completa de workspaces, permissões, checkpoints, Unreal, terminal e auditoria.")
        self.tools_summary = tk.Label(f, text="", font=("Segoe UI", 10),
                                      fg=_TEXT, bg=_PANEL, justify=tk.LEFT)
        self.tools_summary.pack(anchor=tk.W, padx=20, pady=12)
        tk.Button(f, text="Abrir ferramentas e aprovações",
                  command=self._open_tools, relief=tk.FLAT,
                  bg=_ACCENT, fg="#0d1220", font=("Segoe UI", 10, "bold")
                  ).pack(anchor=tk.W, padx=20, pady=8)

    def _build_settings(self):
        f = self._frames["Configurações"]
        self._card(f, "Configurações",
                   "Configuração do provider/modelo e credenciais. Chaves salvas continuam ocultas e são armazenadas pelo serviço de configuração.")
        self.settings_summary = tk.Label(f, text="", font=("Segoe UI", 10),
                                         fg=_TEXT, bg=_PANEL, justify=tk.LEFT)
        self.settings_summary.pack(anchor=tk.W, padx=20, pady=12)
        tk.Button(f, text="Abrir configurações de IA",
                  command=self._open_settings, relief=tk.FLAT,
                  bg=_ACCENT, fg="#0d1220", font=("Segoe UI", 10, "bold")
                  ).pack(anchor=tk.W, padx=20, pady=8)

    def _refresh_runtime(self):
        lines = []
        for report in self._plugin_reports:
            status, color = self._status_text(report)
            lines.append(f"{status:20} {report.descriptor.name} — {report.detail}")
        self.runtime_text.configure(state=tk.NORMAL)
        self.runtime_text.delete("1.0", tk.END)
        self.runtime_text.insert(tk.END, "\n".join(lines) or "Nenhum componente diagnosticado.")
        self.runtime_text.configure(state=tk.DISABLED)

    def _refresh_capabilities(self):
        for plugin_id, label in getattr(self, "_cap_status", {}).items():
            report = self._report(plugin_id)
            status, color = self._status_text(report)
            label.configure(text=status, fg=color)
            detail = report.detail if report else "O componente não foi encontrado."
            self._cap_detail[plugin_id].configure(text=detail)

        if self._tools_controller is not None:
            perms = {x["level"]: x["granted"] for x in self._tools_controller.permission_status()}
            pending = self._tools_controller.has_pending
            scope = self._tools_controller.unreal_scope_status()
            self.cc_details.configure(
                text="Permissão COMPUTER_CONTROL: " + ("CONCEDIDA" if perms.get("COMPUTER_CONTROL") else "NÃO CONCEDIDA")
                + "\nEscopo Unreal: " + ("ATIVO" if scope else "NENHUM")
            )
            self.web_details.configure(
                text="Permissão WEB_ACCESS: " + ("CONCEDIDA" if perms.get("WEB_ACCESS") else "NÃO CONCEDIDA")
                + "\nPesquisa web é geral por padrão; a política de segurança de rede permanece ativa."
            )
            self.unreal_details.configure(
                text="Permissão UNREAL: " + ("CONCEDIDA" if perms.get("UNREAL") else "NÃO CONCEDIDA")
                + "\nPlano pendente: " + ("SIM — aguarda autorização/execução" if self._tools_controller.pending_unreal_plan() else "NÃO")
            )
            self.tools_summary.configure(
                text="Permissões ativas: " + ", ".join(k for k,v in perms.items() if v)
                + "\nOperação aguardando aprovação: " + ("SIM" if pending else "NÃO")
            )
        else:
            self.cc_details.configure(text="ToolsController indisponível.")
            self.web_details.configure(text="ToolsController indisponível.")
            self.unreal_details.configure(text="ToolsController indisponível.")
            self.tools_summary.configure(text="ToolsController indisponível.")

    def _refresh_settings(self):
        provider = getattr(self._agent.provider, "name", "?")
        model = getattr(self._agent.provider, "model_name", "") or "-"
        self.settings_summary.configure(text=f"Provider ativo: {provider}\nModelo: {model}")

    def _refresh_all(self):
        self._refresh_runtime()
        self._refresh_capabilities()
        self._refresh_settings()

    def _poll_refresh(self):
        try:
            if self.top.winfo_exists():
                self._refresh_all()
                self.top.after(1500, self._poll_refresh)
        except tk.TclError:
            pass

    def _open_tools(self):
        if self._tools_controller is None:
            return
        from app.ui.tools_dialog import ToolsDialog
        ToolsDialog(self.top, self._tools_controller,
                    on_plan_finished=getattr(self._parent, "_on_plan_finished", None))

    def _open_settings(self):
        if self._config_service is None:
            return
        from app.ui.settings_dialog import SettingsDialog
        SettingsDialog(self.top, self._config_service,
                       on_saved=self._on_provider_saved)

    def select_tab(self, name: str):
        if name not in self.TABS:
            raise ValueError(f"Aba operacional desconhecida: {name}")
        self.notebook.select(self.TABS.index(name))
