from __future__ import annotations

from app.computer_control.grounding import GroundedTarget, GroundingSource

from .grounding import ComputerGrounding, NativeFirstResolver
from .models import ComputerObservation, ExecutionMechanism, TargetResolution


class TargetingEngine:
    """Selects a grounded target and never executes an action."""

    def __init__(self, *, min_confidence: float = 0.80):
        self.grounding = ComputerGrounding(min_confidence=min_confidence)
        self.resolver = NativeFirstResolver()

    def resolve(self, observation: ComputerObservation, label: str, *, candidates: tuple[GroundedTarget, ...] = ()):
        if not label or not label.strip():
            raise ValueError("target label cannot be empty")
        all_candidates = self.grounding.candidates(observation, candidates=candidates)
        target, tried, reason = self.resolver.resolve(all_candidates, label=label.strip())
        if target is None:
            return TargetResolution(label.strip(), None, ExecutionMechanism.NONE,
                                     tuple(source.value for source in tried), reason)
        try:
            self.grounding.validate_target(observation, target)
        except PermissionError:
            return TargetResolution(label.strip(), None, ExecutionMechanism.NONE,
                                     tuple(source.value for source in tried), "target_outside_scope")
        mechanism = (
            ExecutionMechanism.NATIVE
            if target.source in {
                GroundingSource.UI_AUTOMATION, GroundingSource.ACCESSIBILITY,
                GroundingSource.NATIVE, GroundingSource.DOM,
            }
            else ExecutionMechanism.COMPUTER_CONTROL
        )
        return TargetResolution(
            label.strip(), target, mechanism,
            tuple(source.value for source in tried), reason
        )
