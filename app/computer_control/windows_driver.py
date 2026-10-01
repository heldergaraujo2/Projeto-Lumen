"""F27 — Windows native Computer Control driver.

The driver is Windows-only and has an independent arming gate. The higher
level ComputerControlService remains the authority boundary:
PermissionManager -> Policy -> Scope -> Checkpoint -> Driver -> Audit.

This module performs real desktop I/O only when instantiated on Windows and
explicitly armed. It does not grant permissions, widen scope, or bypass
checkpoints.
"""
from __future__ import annotations

import ctypes
import os
import re
import tempfile
import time
from pathlib import Path

from .api import CCTarget, ComputerControlDriver, ScreenRegion, ScreenshotInfo


class WindowsComputerControlError(RuntimeError):
    """Raised when the Windows native driver cannot perform an operation."""


_USER32 = ctypes.windll.user32 if os.name == "nt" else None

_MLEFTDOWN = 0x0002
_MLEFTUP = 0x0004
_MRIGHTDOWN = 0x0008
_MRIGHTUP = 0x0010
_MMIDDLEDOWN = 0x0020
_MMIDDLEUP = 0x0040
_MWHEEL = 0x0800
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_SW_RESTORE = 9

_VK = {
    "BACKSPACE": 0x08, "TAB": 0x09, "ENTER": 0x0D, "SHIFT": 0x10,
    "CTRL": 0x11, "ALT": 0x12, "PAUSE": 0x13, "CAPSLOCK": 0x14,
    "ESC": 0x1B, "SPACE": 0x20, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "END": 0x23, "HOME": 0x24, "LEFT": 0x25, "UP": 0x26,
    "RIGHT": 0x27, "DOWN": 0x28, "INSERT": 0x2D, "DELETE": 0x2E,
    "WIN": 0x5B, "LWIN": 0x5B, "RWIN": 0x5C,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
}
_VK.update({chr(ord("A") + i): ord("A") + i for i in range(26)})
_VK.update({str(i): 0x30 + i for i in range(10)})


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowsComputerControlError("Windows native driver requires Windows")


def _require_armed(armed: bool) -> None:
    if not armed:
        raise WindowsComputerControlError(
            "Windows driver is disarmed; explicit F27 physical arming is required"
        )


def _vk(key: str) -> int:
    normalized = str(key).strip().upper()
    if normalized in _VK:
        return _VK[normalized]
    if len(normalized) == 1:
        value = _USER32.VkKeyScanW(ord(normalized))
        if value == -1:
            raise ValueError(f"unsupported key: {key}")
        return value & 0xFF
    raise ValueError(f"unsupported key: {key}")


class WindowsComputerControlDriver(ComputerControlDriver):
    """Minimal real Windows desktop driver backed by user32 and Pillow.

    Input is disabled by default. Set armed=True only inside an already
    authorized ComputerControlService flow or an explicit physical smoke test.
    """

    def __init__(self, *, armed: bool = False, screenshot_dir: Path | str | None = None) -> None:
        _require_windows()
        self.armed = bool(armed)
        self.screenshot_dir = Path(screenshot_dir or tempfile.gettempdir())
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def _input_ready(self) -> None:
        _require_windows()
        _require_armed(self.armed)

    def screenshot(self, *, target: CCTarget | None = None, region: ScreenRegion | None = None) -> ScreenshotInfo:
        _require_windows()
        try:
            from PIL import ImageGrab
        except Exception as exc:
            raise WindowsComputerControlError("Pillow ImageGrab is unavailable") from exc
        if region is not None:
            region.validate()
            bbox = (region.x, region.y, region.x + region.width, region.y + region.height)
        else:
            bbox = None
        image = ImageGrab.grab(bbox=bbox, all_screens=True)
        base = self.screenshot_dir / f"lumen_f27_{os.getpid()}.png"
        candidate = base
        counter = 0
        while candidate.exists():
            counter += 1
            candidate = self.screenshot_dir / f"lumen_f27_{os.getpid()}_{counter}.png"
        image.save(candidate, format="PNG")
        width, height = image.size
        return ScreenshotInfo(width=width, height=height, artifact_ref=str(candidate), region=region)

    def mouse_move(self, x: int, y: int) -> None:
        self._input_ready()
        if not _USER32.SetCursorPos(int(x), int(y)):
            raise WindowsComputerControlError("SetCursorPos failed")

    def mouse_click(self, x: int, y: int, *, button: str = "left") -> None:
        self._input_ready()
        self.mouse_move(x, y)
        flags = {
            "left": (_MLEFTDOWN, _MLEFTUP),
            "right": (_MRIGHTDOWN, _MRIGHTUP),
            "middle": (_MMIDDLEDOWN, _MMIDDLEUP),
        }
        try:
            down, up = flags[button.strip().lower()]
        except KeyError as exc:
            raise ValueError(f"unsupported mouse button: {button}") from exc
        _USER32.mouse_event(down, 0, 0, 0, 0)
        _USER32.mouse_event(up, 0, 0, 0, 0)

    def mouse_double_click(self, x: int, y: int, *, button: str = "left") -> None:
        self.mouse_click(x, y, button=button)
        self.mouse_click(x, y, button=button)

    def mouse_drag(self, x1: int, y1: int, x2: int, y2: int, *, button: str = "left") -> None:
        self._input_ready()
        if button.strip().lower() != "left":
            raise ValueError("F27 drag currently supports only the left button")
        self.mouse_move(x1, y1)
        _USER32.mouse_event(_MLEFTDOWN, 0, 0, 0, 0)
        self.mouse_move(x2, y2)
        _USER32.mouse_event(_MLEFTUP, 0, 0, 0, 0)

    def scroll(self, delta: int) -> None:
        self._input_ready()
        _USER32.mouse_event(_MWHEEL, 0, 0, int(delta), 0)

    def key_press(self, key: str) -> None:
        self._input_ready()
        code = _vk(key)
        _USER32.keybd_event(code, 0, 0, 0)
        _USER32.keybd_event(code, 0, _KEYEVENTF_KEYUP, 0)

    def key_combo(self, keys: tuple[str, ...]) -> None:
        self._input_ready()
        if not keys:
            raise ValueError("key combo cannot be empty")
        codes = [_vk(key) for key in keys]
        for code in codes:
            _USER32.keybd_event(code, 0, 0, 0)
        for code in reversed(codes):
            _USER32.keybd_event(code, 0, _KEYEVENTF_KEYUP, 0)

    def type_text(self, text: str) -> None:
        self._input_ready()
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        for char in text:
            code = ord(char)
            if code > 0xFFFF:
                raise ValueError("characters outside the Windows UTF-16 BMP are unsupported")
            _USER32.keybd_event(0, code, _KEYEVENTF_UNICODE, 0)
            _USER32.keybd_event(0, code, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP, 0)

    def _verify_foreground(self, handle: int) -> None:
        """Confirm that Windows actually activated the requested window.

        SetForegroundWindow() can return success without the requested window
        becoming the foreground window immediately (or at all, for example
        when Windows foreground-activation rules reject the request). Treat
        that case as a failed focus operation rather than allowing subsequent
        keyboard input to reach an unrelated window.
        """
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if int(_USER32.GetForegroundWindow()) == int(handle):
                return
            time.sleep(0.01)
        raise WindowsComputerControlError(
            f"window focus verification failed for handle {int(handle)}"
        )

    def focus_window(self, target: CCTarget) -> None:
        _require_windows()
        if target.window_handle:
            handle = int(target.window_handle)
            if not _USER32.IsWindow(handle):
                raise WindowsComputerControlError("window handle is not valid")
            _USER32.ShowWindow(handle, _SW_RESTORE)
            if not _USER32.SetForegroundWindow(handle):
                raise WindowsComputerControlError("SetForegroundWindow failed")
            self._verify_foreground(handle)
            return

        pattern = target.window_title_pattern
        if not pattern:
            raise ValueError("focus_window requires window_handle or window_title_pattern")
        regex = re.compile(pattern, re.IGNORECASE)
        found: list[int] = []
        enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        @enum_proc_type
        def callback(hwnd, _lparam):
            length = _USER32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            _USER32.GetWindowTextW(hwnd, buffer, length + 1)
            if regex.search(buffer.value):
                found.append(int(hwnd))
                return False
            return True

        _USER32.EnumWindows(callback, 0)
        if not found:
            raise WindowsComputerControlError("target window not found")
        handle = found[0]
        _USER32.ShowWindow(handle, _SW_RESTORE)
        if not _USER32.SetForegroundWindow(handle):
            raise WindowsComputerControlError("SetForegroundWindow failed")
        self._verify_foreground(handle)
