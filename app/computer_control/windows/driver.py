"""Driver real de Computer Control para Windows (screenshot via ``mss``).

Este módulo fica fora de ``app/tools`` justamente por importar uma
biblioteca de captura de tela (``mss``). A fachada em
``app/tools/computer_control.py`` recebe o driver por injeção e nunca
importa ``mss`` — preservando o guard estático de ``app/tools``.

No MVP o driver só tira screenshots (sem mouse/teclado). Grava um PNG em
``artifacts_dir`` e devolve ``ScreenshotInfo`` metadata-only (o
``artifact_ref`` aponta para o arquivo; nenhum byte vai para o audit).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

import ctypes
from ctypes import wintypes

from mss import mss
from mss.tools import to_png

from app.computer_control.api import CCTarget, ScreenshotInfo


class WindowsComputerControlDriver:
    """Driver Windows real — captura de tela (sem mouse/teclado no MVP).

    - Grava um arquivo PNG em ``artifacts_dir``.
    - Retorna ``ScreenshotInfo`` metadata-only (``artifact_ref`` = caminho).
    """

    def __init__(self, *, artifacts_dir: Path) -> None:
        self._artifacts_dir = Path(artifacts_dir)

    def screenshot(self, *, target: Optional[CCTarget] = None) -> ScreenshotInfo:
        # ``target`` é aceito por compatibilidade de contrato; o MVP ainda
        # não filtra por janela/aplicativo — captura a tela virtual inteira.
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

        filename = f"cc_screenshot_{uuid4().hex}.png"
        out_path = self._artifacts_dir / filename

        with mss() as sct:
            # monitors[0] é a "tela virtual", abrangendo todos os monitores.
            mon = sct.monitors[0]
            img = sct.grab(mon)
            to_png(img.rgb, img.size, output=str(out_path))
            width, height = img.size

        return ScreenshotInfo(width=width, height=height, artifact_ref=str(out_path))

    def mouse_move(self, *, dx: int, dy: int, target: Optional[CCTarget] = None) -> tuple[int, int]:
        # target accepted for API compatibility; MVP does not filter by window/app.
        if not isinstance(dx, int) or isinstance(dx, bool):
            raise TypeError("dx must be int")
        if not isinstance(dy, int) or isinstance(dy, bool):
            raise TypeError("dy must be int")

        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        pt = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            raise OSError("GetCursorPos failed")

        new_x = int(pt.x + dx)
        new_y = int(pt.y + dy)
        if not user32.SetCursorPos(new_x, new_y):
            raise OSError("SetCursorPos failed")

        pt2 = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt2)):
            return (new_x, new_y)
        return (int(pt2.x), int(pt2.y))
