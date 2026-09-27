from __future__ import annotations

from collections.abc import Iterable

from app.computer_control.grounding import GroundedTarget, GroundingEngine, GroundingSource, TargetResolver

from .models import ComputerObservation


class ComputerGrounding:
    """Lumen-owned grounding boundary around the existing validator."""

    def __init__(self, *, min_confidence: float = 0.80):
        self.engine = GroundingEngine(min_confidence=min_confidence)

    def candidates(self, observation: ComputerObservation, *, candidates: Iterable[GroundedTarget] | None = None):
        observation.validate()
        supplied = tuple(candidates or ())
        for target in supplied:
            target.validate()
        observed = tuple(observation.elements)
        return supplied + observed

    def validate_target(self, observation: ComputerObservation, target: GroundedTarget):
        return self.engine.validate_for_scope(
            target,
            scope_region=observation.allowed_region,
            screenshot_width=observation.width,
            screenshot_height=observation.height,
        )


class NativeFirstResolver:
    def __init__(self):
        self.resolver = TargetResolver()

    def resolve(self, candidates, *, label):
        return self.resolver.resolve(candidates, label=label)
