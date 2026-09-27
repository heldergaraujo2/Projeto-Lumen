from __future__ import annotations

from typing import Protocol

from app.computer_control.api import CCTarget
from app.computer_control.vision import VisionObservation

from .models import ComputerObservation


class PerceptionProvider(Protocol):
    def observe(self) -> ComputerObservation:
        ...


class VisionObservationPerception:
    """Adapter from the existing VisionObservation contract."""

    def __init__(self, observation: VisionObservation, *, active_window: CCTarget | None = None):
        self._observation = observation
        self._active_window = active_window

    def observe(self) -> ComputerObservation:
        self._observation.validate()
        from app.computer_control.grounding import GroundedTarget, GroundingSource
        return ComputerObservation(
            width=self._observation.width,
            height=self._observation.height,
            elements=tuple(
                GroundedTarget(
                    label=e.label, source=GroundingSource.VISION,
                    confidence=e.confidence, x=e.x, y=e.y,
                    width=e.width, height=e.height, evidence=e.text,
                )
                for e in self._observation.elements
            ),
            active_window=self._active_window,
        )


class PerceptionPipeline:
    """Validates and freezes structured observations before downstream use."""

    def __init__(self, provider: PerceptionProvider):
        self.provider = provider

    def observe(self) -> ComputerObservation:
        observation = self.provider.observe()
        observation.validate()
        return observation
