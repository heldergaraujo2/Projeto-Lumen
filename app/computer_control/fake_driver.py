from __future__ import annotations

from typing import Optional

from .api import CCTarget, ScreenshotInfo


class FakeComputerControlDriver:
    """Deterministic driver for unit tests (no OS interaction).

    IMPORTANT:
    - Does not capture real screen.
    - Does not write files.
    - Returns metadata-only ScreenshotInfo (no bytes).
    """

    def __init__(self, *, width: int = 800, height: int = 600, artifact_prefix: str = "fake:screenshot:"):
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be > 0")
        self._width = width
        self._height = height
        self._artifact_prefix = artifact_prefix
        self._counter = 0
        self._x = 0
        self._y = 0

    def screenshot(self, *, target: Optional[CCTarget] = None) -> ScreenshotInfo:
        # target is accepted for API compatibility; fake driver does not use it.
        self._counter += 1
        artifact_ref = f"{self._artifact_prefix}{self._counter}"
        return ScreenshotInfo(width=self._width, height=self._height, artifact_ref=artifact_ref)

    def mouse_move(self, *, dx: int, dy: int, target: Optional[CCTarget] = None) -> tuple[int, int]:
        # target accepted for API compatibility; fake driver does not use it.
        if not isinstance(dx, int) or isinstance(dx, bool):
            raise TypeError("dx must be int")
        if not isinstance(dy, int) or isinstance(dy, bool):
            raise TypeError("dy must be int")
        self._x += dx
        self._y += dy
        return (self._x, self._y)

    def mouse_click(self, *, button: str = "left", target: Optional[CCTarget] = None) -> tuple[int, int]:
        # target accepted for API compatibility; fake driver does not use it.
        if button != "left":
            raise ValueError("only left button is supported in MVP")
        return (self._x, self._y)

    def mouse_click_at(
        self, *, dx: int, dy: int, button: str = "left", target: Optional[CCTarget] = None
    ) -> tuple[int, int]:
        # target accepted for API compatibility; fake driver does not use it.
        if button != "left":
            raise ValueError("only left button is supported in MVP")
        if not isinstance(dx, int) or isinstance(dx, bool):
            raise TypeError("dx must be int")
        if not isinstance(dy, int) or isinstance(dy, bool):
            raise TypeError("dy must be int")
        self._x += dx
        self._y += dy
        return (self._x, self._y)

    def key_type(self, *, text: str, target: Optional[CCTarget] = None) -> int:
        # target accepted for API compatibility; fake driver does not use it.
        if not isinstance(text, str):
            raise TypeError("text must be str")
        return len(text)

    def focus_window(self, *, target: CCTarget) -> bool:
        # Deterministic: succeed only if a title pattern is provided.
        if not isinstance(target, CCTarget):
            raise TypeError("target must be CCTarget")
        pat = target.window_title_pattern
        return bool(isinstance(pat, str) and pat.strip())

    def wait_for_window(self, *, target: CCTarget, timeout_s: int) -> bool:
        # Deterministic: same rule as focus_window; no real waiting.
        if not isinstance(target, CCTarget):
            raise TypeError("target must be CCTarget")
        if not isinstance(timeout_s, int) or isinstance(timeout_s, bool) or timeout_s <= 0:
            raise ValueError("timeout_s must be positive int")
        pat = target.window_title_pattern
        return bool(isinstance(pat, str) and pat.strip())
