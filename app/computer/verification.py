from __future__ import annotations

from app.computer_control.verification import ComputerVerifier, VerificationResult, VerificationStatus
from .models import ComputerObservation


class IntelligenceVerifier:
    def __init__(self, verifier: ComputerVerifier | None = None):
        self.verifier = verifier or ComputerVerifier()

    def target(self, observation: ComputerObservation, *, label: str) -> VerificationResult:
        found = any(item.label.casefold() == label.casefold() for item in observation.elements)
        return self.verifier.verify_target_visible(found=found, expected_label=label)

    def state_changed(self, before: ComputerObservation, after: ComputerObservation) -> VerificationResult:
        changed = before.fingerprint != after.fingerprint
        return VerificationResult(
            VerificationStatus.VERIFIED if changed else VerificationStatus.INCONCLUSIVE,
            "state_changed" if changed else "state_unchanged",
            (before.fingerprint, after.fingerprint),
        )
