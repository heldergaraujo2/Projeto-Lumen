"""Toolkit Tk falso compartilhado — permite testar a UI sem display.

Usado por ``tests/test_settings_dialog.py`` e por
``tools_dev/verify_ui_headless.py``. Registra tudo o que a UI faz em
widgets simples em memória (nenhuma janela real é aberta).
"""
from __future__ import annotations


class FakeWidget:
    def __init__(self, *args, **kwargs):
        self._config = dict(kwargs)
        self.destroyed = False

    def pack(self, **kwargs): ...
    def grid(self, **kwargs): ...
    def pack_forget(self): ...

    def config(self, **kwargs):
        self._config.update(kwargs)

    configure = config

    def bind(self, *args, **kwargs): ...
    def focus_set(self): ...

    def cget(self, key):
        return self._config.get(key, "")

    def destroy(self):
        self.destroyed = True


class FakeRoot(FakeWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.window_title = None
        self.close_handler = None
        self.scheduled = []

    def title(self, value):
        self.window_title = value

    def geometry(self, value): ...
    def minsize(self, *args): ...
    def transient(self, *args): ...
    def grab_set(self): ...

    def protocol(self, name, handler):
        self.close_handler = handler

    def after(self, ms, callback):
        self.scheduled.append(callback)

    def mainloop(self): ...


class FakeToplevel(FakeRoot):
    """Janela filha (usada pelo diálogo de configurações)."""


class FakeText(FakeWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = ""
        self._state = "normal"

    def config(self, **kwargs):
        if "state" in kwargs:
            self._state = kwargs.pop("state")
        self._config.update(kwargs)

    configure = config

    def insert(self, index, text, tag=None):
        assert self._state == "normal", "insert com widget desabilitado"
        self.text += text

    def delete(self, start="1.0", end="end"):
        self.text = ""

    def see(self, *args): ...

    def get(self, start="1.0", end="end"):
        return self.text

    def tag_configure(self, *args, **kwargs): ...


class FakeEntry(FakeWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = ""

    def insert(self, index, text):
        self.text += text

    def get(self):
        return self.text

    def delete(self, start, end):
        self.text = ""


class FakeCombobox(FakeEntry):
    """ttk.Combobox falsa: valores readonly com get/set."""

    def set(self, value):
        self.text = value

    def get(self):
        return self.text


class FakeButton(FakeWidget):
    def invoke(self):
        command = self._config.get("command")
        if callable(command):
            command()


class FakeTkModule:
    Tk = FakeRoot
    Toplevel = FakeToplevel
    Frame = FakeWidget
    Label = FakeWidget
    Text = FakeText
    Entry = FakeEntry
    Button = FakeButton

    END = "end"
    NORMAL = "normal"
    DISABLED = "disabled"
    LEFT = "left"
    RIGHT = "right"
    X = "x"
    BOTH = "both"
    FLAT = "flat"
    WORD = "word"
    N = "n"
    W = "w"
    E = "e"
    S = "s"
    TOP = "top"

    class TclError(Exception): ...


class FakeTtkModule:
    Combobox = FakeCombobox


class FakeMessagebox:
    """tkinter.messagebox falso — respostas programáveis."""

    def __init__(self, answer=True):
        self.answer = answer
        self.calls: list[tuple] = []

    def askyesno(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.answer
