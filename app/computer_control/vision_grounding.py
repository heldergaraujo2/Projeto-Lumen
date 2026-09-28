"""F28 — real screenshot -> vision -> grounding pipeline.

This layer produces an action candidate; it never executes it. Execution remains
owned by ComputerControlService and its Permission/Policy/Scope/Checkpoint
chain.
"""
from __future__ import annotations

from dataclasses import dataclass

from .api import CCTarget, ScreenRegion
from .grounding import GroundedTarget, GroundingEngine, TargetResolver
from .vision import VisionObservation, VisionProvider, VisionRequest


@dataclass(frozen=True)
class VisionGroundingResult:
    observation: VisionObservation
    candidates: tuple[GroundedTarget, ...]
    target: GroundedTarget | None
    tried_sources: tuple[str, ...]
    reason: str

    def validate(self) -> None:
        self.observation.validate()
        for candidate in self.candidates:
            candidate.validate()
        if self.target is not None:
            self.target.validate()
            if self.target not in self.candidates:
                raise ValueError("resolved target must be an eligible candidate")


class VisionGroundingPipeline:
    """Observe one screenshot and resolve one safe target without execution."""

    def __init__(
        self,
        provider: VisionProvider,
        *,
        grounding: GroundingEngine | None = None,
        resolver: TargetResolver | None = None,
    ) -> None:
        self.provider = provider
        self.grounding = grounding or GroundingEngine()
        self.resolver = resolver or TargetResolver()

    def observe_and_resolve(
        self,
        request: VisionRequest,
        *,
        label: str,
        scope_region: ScreenRegion | None = None,
        expected_window: CCTarget | None = None,
    ) -> VisionGroundingResult:
        observation = self.provider.observe(request)
        observation.validate()
        candidates = self.grounding.from_vision(observation)
        candidates = self.grounding.eligible(
            candidates,
            scope_region=scope_region,
            screenshot_width=observation.width,
            screenshot_height=observation.height,
            expected_window=expected_window,
        )
        target, tried, reason = self.resolver.resolve(candidates, label=label)
        result = VisionGroundingResult(
            observation=observation,
            candidates=candidates,
            target=target,
            tried_sources=tuple(source.value for source in tried),
            reason=reason,
        )
        result.validate()
        return result
