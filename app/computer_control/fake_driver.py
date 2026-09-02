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

    def screenshot(self, *, target: Optional[CCTarget] = None) -> ScreenshotInfo:
        # target is accepted for API compatibility; fake driver does not use it.
        self._counter += 1
        artifact_ref = f"{self._artifact_prefix}{self._counter}"
        return ScreenshotInfo(width=self._width, height=self._height, artifact_ref=artifact_ref)
