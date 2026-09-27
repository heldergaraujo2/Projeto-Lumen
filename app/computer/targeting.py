from __future__ import annotations

from app.computer_control.grounding import GroundedTarget, GroundingSource, TargetResolver

from .grounding import ComputerGrounding, NativeFirstResolver
from .models import ComputerObservation, ExecutionMechanism, TargetResolution


class TargetingEngine:
    """Selects an eligible grounded target and never executes an action."""

    def __init__(self, *, min_confidence: float = 0.80):
        self.grounding = ComputerGrounding(min_confidence=min_confidence)
        self.resolver = NativeFirstResolver()

    def resolve(
        self,
        observation: ComputerObservation,
        label: str,
        *,
        candidates: tuple[GroundedTarget, ...] = (),
    ) -> TargetResolution:
        if not label or not label.strip():
            raise ValueError("target label cannot be empty")

        all_candidates = self.grounding.candidates(observation, candidates=candidates)
        eligible = self.grounding.eligible(
            all_candidates,
            scope_region=observation.allowed_region,
            screenshot_width=observation.width,
            screenshot_height=observation.height,
            expected_window=observation.active_window,
        )
        target, tried, reason = self.resolver.resolve(eligible, label=label.strip())

        if target is None:
            normalized = self.grounding.engine.normalize_label(label)
            had_matching_candidate = any(
                self.grounding.engine.normalize_label(item.label) == normalized
                for item in all_candidates
            )
            if had_matching_candidate:
                reason = "target_not_eligible"
            return TargetResolution(
                label.strip(),
                None,
                ExecutionMechanism.NONE,
                tuple(source.value for source in tried),
                reason,
            )

        mechanism = (
            ExecutionMechanism.NATIVE
            if target.source
            in {
                GroundingSource.UI_AUTOMATION,
                GroundingSource.ACCESSIBILITY,
                GroundingSource.NATIVE,
                GroundingSource.DOM,
            }
            else ExecutionMechanism.COMPUTER_CONTROL
        )
        return TargetResolution(
            label.strip(),
            target,
            mechanism,
            tuple(source.value for source in tried),
            reason,
        )
