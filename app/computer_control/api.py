from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


class CCActionType(str, Enum):
    """High-level action types that Computer Control may perform.

    MVP focuses on SCREENSHOT via FakeDriver. Other actions are declared for forward-compat,
    but are not implemented in CC-2.
    """

    SCREENSHOT = "screenshot"
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    SCROLL = "scroll"
    KEY_TYPE = "key_type"
    KEY_COMBO = "key_combo"


@dataclass(frozen=True)
class CCTarget:
    """A minimal target descriptor for scoping (no OS handles in the MVP core)."""

    app_name: Optional[str] = None
    process_name: Optional[str] = None
    window_title_pattern: Optional[str] = None


@dataclass(frozen=True)
class ScreenshotInfo:
    """Metadata-only screenshot result.

    IMPORTANT: this object must never carry raw screenshot bytes.
    If an artifact is produced, reference it by id/path hash via artifact_ref.
    """

    width: int
    height: int
    artifact_ref: Optional[str] = None


class ComputerControlDriver(Protocol):
    """Driver interface for CC execution.

    Implementations:
    - FakeDriver (CC-2): deterministic, no OS interaction
    - Windows driver (CC-4): OS integration, lives in app/computer_control/windows/driver.py
    """

    def screenshot(self, *, target: Optional[CCTarget] = None) -> ScreenshotInfo: ...


    def mouse_move(
        self, *, dx: int, dy: int, target: Optional[CCTarget] = None
    ) -> tuple[int, int]: ...


    def mouse_click(
        self, *, button: str = "left", target: Optional[CCTarget] = None
    ) -> tuple[int, int]: ...


    def mouse_click_at(
        self, *, dx: int, dy: int, button: str = "left", target: Optional[CCTarget] = None
    ) -> tuple[int, int]: ...
