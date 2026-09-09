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


    def mouse_move_to(self, *, x: int, y: int, target=None) -> tuple[int, int]:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("x must be int")
        if not isinstance(y, int) or isinstance(y, bool):
            raise TypeError("y must be int")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        vx = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
        vy = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))

        ax = vx + int(x)
        ay = vy + int(y)

        ok = user32.SetCursorPos(ax, ay)
        if not ok:
            raise RuntimeError("SetCursorPos failed")
        return (ax, ay)
    def mouse_click(self, *, button: str = "left", target: Optional[CCTarget] = None) -> tuple[int, int]:
        # target accepted for API compatibility; MVP does not filter by window/app.
        if button != "left":
            raise ValueError("only left button is supported in MVP")

        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        pt = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            raise OSError("GetCursorPos failed")

        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004

        # MVP: click at current cursor position (no move, no double click).
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

        return (int(pt.x), int(pt.y))

    def mouse_click_at(
        self,
        *,
        dx: int,
        dy: int,
        button: str = "left",
        target: Optional[CCTarget] = None,
    ) -> tuple[int, int]:
        # MVP: move relativo + click no ponto atual (ap?s mover).
        self.mouse_move(dx=dx, dy=dy, target=target)
        return self.mouse_click(button=button, target=target)
    def key_type(self, *, text: str, target: Optional[CCTarget] = None) -> int:
        # MVP: foca por window_title_pattern (se fornecido) e digita via SendInput (UNICODE).
        if not isinstance(text, str):
            raise TypeError("text must be str")

        user32 = ctypes.WinDLL("user32", use_last_error=True)

        def _focus_by_title_substring(sub: str) -> None:
            sub_l = sub.lower()
            hwnd_match = None

            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def _cb(hwnd, lparam):  # noqa: ANN001
                nonlocal hwnd_match
                if hwnd_match is not None:
                    return False
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if title and sub_l in title.lower():
                    hwnd_match = hwnd
                    return False
                return True

            user32.EnumWindows(EnumWindowsProc(_cb), 0)
            if hwnd_match is None:
                raise LookupError("target window not found")

            SW_RESTORE = 9
            user32.ShowWindow(hwnd_match, SW_RESTORE)
            user32.SetForegroundWindow(hwnd_match)

        if target is not None and isinstance(target.window_title_pattern, str) and target.window_title_pattern.strip():
            _focus_by_title_substring(target.window_title_pattern.strip())

        # IMPORTANT: INPUT is a union of MOUSEINPUT/KEYBDINPUT/HARDWAREINPUT.
        # If we define only KEYBDINPUT, sizeof(INPUT) is too small and SendInput fails (WinError 87).
        ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32

        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_UNICODE = 0x0004

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            ]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD),
            ]

        class _INPUT_UNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]

        user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        user32.SendInput.restype = wintypes.UINT

        def _send(ch: str) -> None:
            code = ord(ch)
            down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0))
            up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0))
            arr = (INPUT * 2)(down, up)
            sent = user32.SendInput(2, arr, ctypes.sizeof(INPUT))
            if sent != 2:
                raise ctypes.WinError(ctypes.get_last_error())

        for ch in text:
            _send(ch)

        return len(text)

    def focus_window(self, *, target: CCTarget) -> bool:
        if not isinstance(target, CCTarget):
            raise TypeError("target must be CCTarget")
        pat = target.window_title_pattern
        if not (isinstance(pat, str) and pat.strip()):
            return False

        user32 = ctypes.WinDLL("user32", use_last_error=True)

        sub_l = pat.strip().lower()
        hwnd_match = None

        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, lparam):  # noqa: ANN001
            nonlocal hwnd_match
            if hwnd_match is not None:
                return False
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if title and sub_l in title.lower():
                hwnd_match = hwnd
                return False
            return True

        user32.EnumWindows(EnumWindowsProc(_cb), 0)
        if hwnd_match is None:
            return False

        SW_RESTORE = 9
        SW_SHOW = 5
        # IMPORTANT: SW_RESTORE pode "des-maximizar" algumas janelas.
        # S? restaurar quando estiver minimizada (IsIconic).
        try:
            if user32.IsIconic(hwnd_match):
                user32.ShowWindow(hwnd_match, SW_RESTORE)
            else:
                user32.ShowWindow(hwnd_match, SW_SHOW)
        except Exception:
            pass
        user32.SetForegroundWindow(hwnd_match)
        return True
    def wait_for_window(self, *, target: CCTarget, timeout_s: int) -> bool:
        if not isinstance(target, CCTarget):
            raise TypeError("target must be CCTarget")
        if not isinstance(timeout_s, int) or isinstance(timeout_s, bool) or timeout_s <= 0:
            raise ValueError("timeout_s must be positive int")

        pat = target.window_title_pattern
        if not (isinstance(pat, str) and pat.strip()):
            return False

        import time

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.focus_window(target=target):
                return True
            time.sleep(0.2)
        return False
