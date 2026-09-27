from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any

from app.computer_control.api import CCTarget, ScreenRegion
from app.computer_control.grounding import GroundedTarget
from app.computer_control.verification import VerificationResult


class ComputerState(str, Enum):
    UNKNOWN = "unknown"
    OBSERVED = "observed"


class ExecutionMechanism(str, Enum):
    NATIVE = "native"
    COMPUTER_CONTROL = "computer_control"
    NONE = "none"


@dataclass(frozen=True)
class ComputerObservation:
    """Immutable structured perception; screenshot bytes are never stored."""
    width: int
    height: int
    elements: tuple[GroundedTarget, ...] = ()
    active_window: CCTarget | None = None
    allowed_region: ScreenRegion | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("observation dimensions must be positive")
        if self.allowed_region is not None:
            self.allowed_region.validate()
            r = self.allowed_region
            if r.x + r.width > self.width or r.y + r.height > self.height:
                raise ValueError("allowed region exceeds observation bounds")
        for element in self.elements:
            element.validate()

    @property
    def state(self) -> ComputerState:
        return ComputerState.OBSERVED

    @property
    def fingerprint(self) -> str:
        self.validate()
        payload = {
            "width": self.width,
            "height": self.height,
            "active_window": self.active_window.__dict__ if self.active_window else None,
            "elements": [
                {
                    "label": e.label, "source": e.source.value,
                    "confidence": e.confidence, "x": e.x, "y": e.y,
                    "width": e.width, "height": e.height,
                }
                for e in self.elements
            ],
            "metadata": self.metadata,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class TargetResolution:
    label: str
    target: GroundedTarget | None
    mechanism: ExecutionMechanism
    tried_sources: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ActionIntent:
    action: str
    target: GroundedTarget | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def validate(self) -> None:
        if not self.action.strip():
            raise ValueError("action cannot be empty")
        if self.target is not None:
            self.target.validate()


@dataclass(frozen=True)
class ActionPlan:
    intents: tuple[ActionIntent, ...]
    observation_fingerprint: str
    rationale: str = ""

    def validate(self) -> None:
        if not self.observation_fingerprint:
            raise ValueError("observation_fingerprint is required")
        for intent in self.intents:
            intent.validate()


@dataclass(frozen=True)
class IntelligenceResult:
    ok: bool
    reason: str
    observation: ComputerObservation | None = None
    target: TargetResolution | None = None
    plan: ActionPlan | None = None
    verification: VerificationResult | None = None
