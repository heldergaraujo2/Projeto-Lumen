"""Testes do centro operacional da UI."""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")

from app.ui.operations_dialog import OperationsDialog


class _Provider:
    name = "ollama"
    model_name = "qwen2.5-coder:7b-instruct-q8_0"


class _Agent:
    provider = _Provider()


class _Controller:
    has_pending = False
    autonomous_mode = False

    def permission_status(self):
        return [
            {"level": "CHAT", "granted": True},
            {"level": "WEB_ACCESS", "granted": True},
            {"level": "READ", "granted": False},
            {"level": "WRITE", "granted": False},
            {"level": "UNREAL", "granted": False},
            {"level": "COMPUTER_CONTROL", "granted": False},
            {"level": "DELETE", "granted": False},
        ]

    def unreal_scope_status(self):
        return None

    def pending_unreal_plan(self):
        return None


@pytest.fixture()
def root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tkinter sem display: {exc}")
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def test_operational_panel_exposes_all_required_tabs(root):
    reports = []
    panel = OperationsDialog(
        root,
        agent=_Agent(),
        tools_controller=_Controller(),
        plugin_reports=reports,
    )
    assert OperationsDialog.TABS == (
        "Runtime",
        "Computer Control",
        "Web Research",
        "Unreal Integration",
        "Ollama",
        "Unreal MCP",
        "Ferramentas / Aprovações",
        "Configurações",
    )
    for name in OperationsDialog.TABS:
        panel.select_tab(name)
    panel.top.destroy()


def test_operational_panel_rejects_unknown_tab(root):
    panel = OperationsDialog(root, agent=_Agent(), tools_controller=_Controller())
    with pytest.raises(ValueError, match="Aba operacional desconhecida"):
        panel.select_tab("desconhecida")
    panel.top.destroy()


def test_operational_panel_exposes_autonomous_mode_contract():
    assert hasattr(OperationsDialog, "_toggle_autonomous")
