"""Explicit coordinate-space contracts for computer-control execution.

Observation coordinates are non-negative pixels relative to the captured frame.
Windows screen coordinates are absolute screen coordinates in the Windows
virtual desktop, which may be negative on monitors left/above the primary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CoordinateSpace(str, Enum):
    OBSERVATION = "observation"
    WINDOWS_SCREEN = "windows_screen"


@dataclass(frozen=True)
class CoordinateTransform:
    """Translate observation pixels to Windows screen coordinates.

    The origin is the Windows virtual-desktop coordinate represented by
    observation pixel (0, 0). No scaling is performed.
    """

    source: CoordinateSpace
    origin_x: int = 0
    origin_y: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.source, CoordinateSpace):
            raise TypeError("source must be a CoordinateSpace")
        if not isinstance(self.origin_x, int) or not isinstance(self.origin_y, int):
            raise TypeError("coordinate origins must be integers")
        if self.source is CoordinateSpace.WINDOWS_SCREEN and (
            self.origin_x != 0 or self.origin_y != 0
        ):
            raise ValueError("windows_screen coordinates cannot carry an observation origin")

    def to_windows_screen(self, x: int, y: int) -> tuple[int, int]:
        if not isinstance(x, int) or not isinstance(y, int):
            raise TypeError("coordinates must be integers")
        if self.source is CoordinateSpace.WINDOWS_SCREEN:
            return x, y
        return x + self.origin_x, y + self.origin_y

    def metadata(self) -> dict[str, object]:
        return {
            "coordinate_space": self.source.value,
            "coordinate_origin_x": self.origin_x,
            "coordinate_origin_y": self.origin_y,
        }
