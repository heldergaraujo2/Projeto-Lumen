from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

from .api import CCTarget, ScreenRegion
from .vision import VisionObservation


class GroundingSource(str, Enum):
    UI_AUTOMATION = "ui_automation"
    ACCESSIBILITY = "accessibility"
    NATIVE = "native"
    DOM = "dom"
    TEMPLATE = "template"
    OCR = "ocr"
    VISION = "vision"
    SLATE = "slate"


@dataclass(frozen=True)
class GroundedTarget:
    label: str
    source: GroundingSource
    confidence: float
    x: int
    y: int
    width: int
    height: int
    window: CCTarget | None = None
    evidence: str | None = None

    def validate(self) -> None:
        if not self.label.strip():
            raise ValueError("invalid grounded target label")
        if not isinstance(self.source, GroundingSource):
            raise ValueError("invalid grounding source")
        if not 0 <= self.confidence <= 1:
            raise ValueError("invalid grounded target confidence")
        if min(self.x, self.y) < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("invalid grounded target bounds")
        if self.evidence is not None and not isinstance(self.evidence, str):
            raise ValueError("grounded target evidence must be a string")

    def center(self) -> tuple[int, int]:
        self.validate()
        return self.x + self.width // 2, self.y + self.height // 2


class GroundingEngine:
    """Converts observations into safe, structured, screenshot-bound targets."""

    DEFAULT_ORDER = (
        GroundingSource.UI_AUTOMATION,
        GroundingSource.ACCESSIBILITY,
        GroundingSource.NATIVE,
        GroundingSource.SLATE,
        GroundingSource.DOM,
        GroundingSource.TEMPLATE,
        GroundingSource.OCR,
        GroundingSource.VISION,
    )

    def __init__(
        self,
        *,
        min_confidence: float = 0.80,
        source_order: Sequence[GroundingSource] = DEFAULT_ORDER,
    ):
        if not 0 < min_confidence <= 1:
            raise ValueError("min_confidence must be in (0,1]")
        order = tuple(source_order)
        if not order or len(set(order)) != len(order):
            raise ValueError("source_order must contain unique sources")
        if set(order) != set(self.DEFAULT_ORDER):
            raise ValueError("source_order must contain every grounding source exactly once")
        self.min_confidence = min_confidence
        self.source_order = order

    @staticmethod
    def normalize_label(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("label must be a string")
        normalized = unicodedata.normalize("NFKC", value).strip().casefold()
        return " ".join(normalized.split())

    def labels_match(self, left: str, right: str) -> bool:
        return self.normalize_label(left) == self.normalize_label(right)

    def from_vision(self, observation: VisionObservation) -> tuple[GroundedTarget, ...]:
        observation.validate()
        targets = tuple(
            GroundedTarget(
                e.label,
                GroundingSource.VISION,
                e.confidence,
                e.x,
                e.y,
                e.width,
                e.height,
                evidence=e.text,
            )
            for e in observation.elements
            if e.confidence >= self.min_confidence
        )
        return self.deduplicate(targets)

    def from_native(self, elements: Iterable[object]) -> tuple[GroundedTarget, ...]:
        """Adapt NativeElement-like objects without importing the Windows layer."""
        targets: list[GroundedTarget] = []
        for element in elements:
            grounded = getattr(element, "grounded", None)
            if not callable(grounded):
                raise TypeError("native element must provide grounded()")
            target = grounded(confidence=1.0)
            target.validate()
            targets.append(target)
        return self.deduplicate(targets)

    def deduplicate(self, candidates: Iterable[GroundedTarget]) -> tuple[GroundedTarget, ...]:
        """Keep the strongest geometrically identical candidate per source/label."""
        best: dict[tuple[GroundingSource, str, int, int, int, int], GroundedTarget] = {}
        for candidate in candidates:
            candidate.validate()
            key = (
                candidate.source,
                self.normalize_label(candidate.label),
                candidate.x,
                candidate.y,
                candidate.width,
                candidate.height,
            )
            previous = best.get(key)
            if previous is None or candidate.confidence > previous.confidence:
                best[key] = candidate
        return tuple(best.values())

    def validate_for_scope(
        self,
        target: GroundedTarget,
        *,
        scope_region: ScreenRegion | None,
        screenshot_width: int,
        screenshot_height: int,
        expected_window: CCTarget | None = None,
    ) -> tuple[int, int]:
        target.validate()
        if screenshot_width <= 0 or screenshot_height <= 0:
            raise ValueError("screenshot dimensions must be positive")
        if target.x + target.width > screenshot_width or target.y + target.height > screenshot_height:
            raise PermissionError("target outside screenshot")
        if scope_region is not None and not scope_region.contains_box(
            target.x, target.y, target.width, target.height
        ):
            raise PermissionError("target outside authorized region")
        if target.confidence < self.min_confidence:
            raise PermissionError("grounding confidence below threshold")
        if expected_window is not None and target.window is not None and target.window != expected_window:
            raise PermissionError("target belongs to an unexpected window")
        return target.center()

    def eligible(
        self,
        candidates: Iterable[GroundedTarget],
        *,
        scope_region: ScreenRegion | None,
        screenshot_width: int,
        screenshot_height: int,
        expected_window: CCTarget | None = None,
    ) -> tuple[GroundedTarget, ...]:
        eligible: list[GroundedTarget] = []
        for candidate in candidates:
            try:
                self.validate_for_scope(
                    candidate,
                    scope_region=scope_region,
                    screenshot_width=screenshot_width,
                    screenshot_height=screenshot_height,
                    expected_window=expected_window,
                )
            except (PermissionError, ValueError):
                continue
            eligible.append(candidate)
        return self.deduplicate(eligible)


class TargetResolver:
    """Resolves only eligible candidates, honoring structured-first source priority."""

    def __init__(self, *, source_order: Sequence[GroundingSource] = GroundingEngine.DEFAULT_ORDER):
        order = tuple(source_order)
        if not order or len(set(order)) != len(order) or set(order) != set(GroundingEngine.DEFAULT_ORDER):
            raise ValueError("source_order must contain every grounding source exactly once")
        self.source_order = order

    def resolve(
        self,
        candidates: Iterable[GroundedTarget],
        *,
        label: str,
    ) -> tuple[GroundedTarget | None, tuple[GroundingSource, ...], str]:
        if not label.strip():
            raise ValueError("target label cannot be empty")
        groups = {source: [] for source in self.source_order}
        normalized = GroundingEngine.normalize_label(label)
        for candidate in candidates:
            candidate.validate()
            if (
                candidate.source in groups
                and GroundingEngine.normalize_label(candidate.label) == normalized
            ):
                groups[candidate.source].append(candidate)

        tried: list[GroundingSource] = []
        for source in self.source_order:
            tried.append(source)
            if groups[source]:
                target = max(groups[source], key=lambda item: item.confidence)
                return target, tuple(tried), f"resolved_by_{source.value}"
        return None, tuple(tried), "target_not_found"
