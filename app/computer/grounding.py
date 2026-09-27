from __future__ import annotations

from collections.abc import Iterable

from app.computer_control.grounding import (
    GroundedTarget,
    GroundingEngine,
    GroundingSource,
    TargetResolver,
)

from .models import ComputerObservation


class ComputerGrounding:
    """Lumen-owned grounding boundary around observation and native candidates."""

    def __init__(self, *, min_confidence: float = 0.80):
        self.engine = GroundingEngine(min_confidence=min_confidence)

    def candidates(
        self,
        observation: ComputerObservation,
        *,
        candidates: Iterable[GroundedTarget] | None = None,
    ) -> tuple[GroundedTarget, ...]:
        observation.validate()
        supplied = tuple(candidates or ())
        for target in supplied:
            target.validate()
        return self.engine.deduplicate(supplied + tuple(observation.elements))

    def from_native(self, elements: Iterable[object]) -> tuple[GroundedTarget, ...]:
        return self.engine.from_native(elements)

    def from_vision(self, observation) -> tuple[GroundedTarget, ...]:
        return self.engine.from_vision(observation)

    def eligible(
        self,
        candidates: Iterable[GroundedTarget],
        *,
        scope_region,
        screenshot_width: int,
        screenshot_height: int,
        expected_window=None,
    ) -> tuple[GroundedTarget, ...]:
        return self.engine.eligible(
            candidates,
            scope_region=scope_region,
            screenshot_width=screenshot_width,
            screenshot_height=screenshot_height,
            expected_window=expected_window,
        )

    def validate_target(self, observation: ComputerObservation, target: GroundedTarget):
        return self.engine.validate_for_scope(
            target,
            scope_region=observation.allowed_region,
            screenshot_width=observation.width,
            screenshot_height=observation.height,
            expected_window=observation.active_window,
        )


class NativeFirstResolver:
    def __init__(self):
        self.resolver = TargetResolver()

    def resolve(self, candidates, *, label):
        return self.resolver.resolve(candidates, label=label)
