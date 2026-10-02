"""Live monitor for the autonomous Lumen mission.

Read-only presentation layer. It tails the durable mission state and JSONL
event log so the operator can see what the autonomous supervisor is doing
without interrupting or granting any capability.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk


_BG = "#0f1218"
_PANEL = "#161b26"
_TEXT = "#e7eaf2"
_MUTED = "#8a93a8"
_OK = "#4cc38a"
_WARN = "#e2b93b"
_ERR = "#e2606f"
_ACCENT = "#7aa2ff"


class AutonomousMissionMonitor:
    """Live, read-only window for the persisted autonomous mission."""

    def __init__(self, parent, *, data_dir: str | Path):
        self._parent = parent
        self._data_dir = Path(data_dir)
        self._mission_path = self._data_dir / "evolution" / "mission.json"
        self._event_path = self._data_dir / "evolution" / "evolution_log.jsonl"
        self._last_event_offset = 0
        self._closed = False

        self.top = tk.Toplevel(parent)
        self.top.title("Lumen — Autonomia ao Vivo")
        self.top.geometry("1050x700")
        self.top.minsize(820, 520)
        self.top.configure(bg=_BG)
        self.top.protocol("WM_DELETE_WINDOW", self.close)

        self._build()
        self._refresh()
        self.top.after(300, self._poll)

    def _build(self):
        header = tk.Frame(self.top, bg=_BG)
        header.pack(fill=tk.X, padx=18, pady=(14, 8))

        tk.Label(
            header, text="AUTONOMIA AO VIVO",
            font=("Segoe UI", 16, "bold"), fg=_TEXT, bg=_BG,
        ).pack(side=tk.LEFT)

        self.connection = tk.Label(
            header, text="● aguardando missão", font=("Segoe UI", 10, "bold"),
            fg=_MUTED, bg=_BG,
        )
        self.connection.pack(side=tk.RIGHT)

        summary = tk.Frame(self.top, bg=_PANEL)
        summary.pack(fill=tk.X, padx=18, pady=(0, 10))

        self.status = self._metric(summary, "STATUS")
        self.phase = self._metric(summary, "FASE")
        self.action = self._metric(summary, "AÇÃO")
        self.cycle = self._metric(summary, "CICLO")
        self.updated = self._metric(summary, "ATUALIZAÇÃO")

        body = tk.Frame(self.top, bg=_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 14))

        left = tk.Frame(body, bg=_PANEL)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(
            left, text="ATIVIDADE EM TEMPO REAL",
            font=("Segoe UI", 11, "bold"), fg=_TEXT, bg=_PANEL,
        ).pack(anchor=tk.W, padx=14, pady=(12, 6))

        self.log = tk.Text(
            left, state=tk.DISABLED, wrap=tk.WORD,
            bg="#10141d", fg=_TEXT, relief=tk.FLAT,
            font=("Consolas", 9), padx=10, pady=8,
        )
        self.log.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        for tag, color in (("ok", _OK), ("warn", _WARN), ("error", _ERR), ("muted", _MUTED)):
            self.log.tag_configure(tag, foreground=color)

        right = tk.Frame(body, bg=_PANEL, width=310)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right.pack_propagate(False)

        tk.Label(
            right, text="MISSÃO", font=("Segoe UI", 11, "bold"),
            fg=_TEXT, bg=_PANEL,
        ).pack(anchor=tk.W, padx=14, pady=(12, 6))

        self.goal = tk.Label(
            right, text="Nenhuma missão carregada.",
            font=("Segoe UI", 9), fg=_TEXT, bg=_PANEL,
            justify=tk.LEFT, anchor=tk.NW, wraplength=280,
        )
        self.goal.pack(fill=tk.X, padx=14, pady=(0, 12))

        self.result = tk.Label(
            right, text="", font=("Segoe UI", 9), fg=_MUTED, bg=_PANEL,
            justify=tk.LEFT, anchor=tk.NW, wraplength=280,
        )
        self.result.pack(fill=tk.X, padx=14, pady=4)

        self.error = tk.Label(
            right, text="", font=("Segoe UI", 9), fg=_ERR, bg=_PANEL,
            justify=tk.LEFT, anchor=tk.NW, wraplength=280,
        )
        self.error.pack(fill=tk.X, padx=14, pady=4)

        tk.Button(
            right, text="Atualizar agora", command=self._refresh,
            relief=tk.FLAT, bg=_ACCENT, fg="#0d1220",
        ).pack(anchor=tk.W, padx=14, pady=14)

    def _metric(self, parent, title):
        frame = tk.Frame(parent, bg=_PANEL)
        frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=10)
        tk.Label(frame, text=title, font=("Segoe UI", 8, "bold"),
                 fg=_MUTED, bg=_PANEL).pack(anchor=tk.W)
        value = tk.Label(frame, text="—", font=("Segoe UI", 11, "bold"),
                         fg=_TEXT, bg=_PANEL)
        value.pack(anchor=tk.W, pady=(2, 0))
        return value

    @staticmethod
    def _read_json(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def _append_events(self):
        try:
            with self._event_path.open("r", encoding="utf-8") as handle:
                handle.seek(self._last_event_offset)
                chunk = handle.read()
                self._last_event_offset = handle.tell()
        except (FileNotFoundError, OSError):
            return

        if not chunk:
            return
        for raw in chunk.splitlines():
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            stamp = event.get("timestamp", 0)
            action = event.get("event", "?")
            phase = event.get("phase", "?")
            details = []
            if event.get("action"):
                details.append(f"ação={event['action']}")
            if event.get("result"):
                details.append(f"resultado={event['result']}")
            if event.get("reason"):
                details.append(f"motivo={event['reason']}")
            suffix = " | " + " | ".join(details) if details else ""
            try:
                clock = __import__("datetime").datetime.fromtimestamp(stamp).strftime("%H:%M:%S")
            except (TypeError, ValueError, OSError):
                clock = "--:--:--"
            line = f"[{clock}] {action} | fase={phase}{suffix}\n"
            tag = "error" if "error" in action or event.get("status") == "BLOCKED" else (
                "ok" if action in {"action_completed", "mission_completed"} else "muted"
            )
            self.log.configure(state=tk.NORMAL)
            self.log.insert(tk.END, line, tag)
            self.log.see(tk.END)
            self.log.configure(state=tk.DISABLED)

    def _refresh(self):
        mission = self._read_json(self._mission_path)
        if mission is None:
            self.connection.configure(text="● aguardando missão", fg=_MUTED)
            self.goal.configure(text="Nenhuma missão persistente encontrada.")
        else:
            status = str(mission.get("status") or "UNKNOWN")
            color = _OK if status == "COMPLETED" else _ERR if status == "BLOCKED" else _WARN
            self.connection.configure(text=f"● {status}", fg=color)
            self.status.configure(text=status)
            self.phase.configure(text=str(mission.get("phase") or "—"))
            self.action.configure(text=str(mission.get("last_action") or "—"))
            self.cycle.configure(text=str(mission.get("cycle", 0)))
            self.updated.configure(text=str(mission.get("updated_at") or "—"))
            self.goal.configure(text=str(mission.get("goal") or "—"))
            self.result.configure(text=f"Último resultado:\n{mission.get('last_result') or '—'}")
            self.error.configure(text=f"Último erro:\n{mission.get('last_error') or 'Nenhum'}")
        self._append_events()

    def _poll(self):
        if self._closed:
            return
        try:
            if self.top.winfo_exists():
                self._refresh()
                self.top.after(300, self._poll)
        except tk.TclError:
            self._closed = True

    def close(self):
        self._closed = True
        try:
            self.top.destroy()
        except tk.TclError:
            pass
