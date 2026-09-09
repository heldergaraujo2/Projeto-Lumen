from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Optional


@dataclass(frozen=True)
class VisionLocateResult:
    # normalized bbox in [0..1]
    x_norm: float
    y_norm: float
    w_norm: float
    h_norm: float
    confidence: float
    provider: str
    model: str

    @property
    def center_x_norm(self) -> float:
        return float(self.x_norm + self.w_norm / 2.0)

    @property
    def center_y_norm(self) -> float:
        return float(self.y_norm + self.h_norm / 2.0)


class VisionLocator(Protocol):
    def locate(self, *, image_path: str | Path, query: str) -> Optional[VisionLocateResult]: ...
