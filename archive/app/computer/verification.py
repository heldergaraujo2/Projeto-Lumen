from __future__ import annotations

from app.computer_control.verification import ComputerVerifier, VerificationExpectation, VerificationResult
from .models import ComputerObservation


class IntelligenceVerifier:
    def __init__(self, verifier: ComputerVerifier | None = None):
        self.verifier = verifier or ComputerVerifier()

    def target(self, observation: ComputerObservation, *, label: str) -> VerificationResult:
        found = any(item.label.casefold() == label.casefold() for item in observation.elements)
        return self.verifier.verify_target_visible(found=found, expected_label=label)

    def target_absent(self, observation: ComputerObservation, *, label: str) -> VerificationResult:
        found = any(item.label.casefold() == label.casefold() for item in observation.elements)
        return self.verifier.verify_target_absent(found=found, expected_label=label)

    def state_changed(self, before: ComputerObservation, after: ComputerObservation) -> VerificationResult:
        return self.verifier.verify_expectation(
            expectation=VerificationExpectation("state_changed"),
            before_fingerprint=before.fingerprint,
            after_fingerprint=after.fingerprint,
        )

    def state_unchanged(self, before: ComputerObservation, after: ComputerObservation) -> VerificationResult:
        return self.verifier.verify_expectation(
            expectation=VerificationExpectation("state_unchanged"),
            before_fingerprint=before.fingerprint,
            after_fingerprint=after.fingerprint,
        )

    def window_focused(self, *, focused: bool, expected: str) -> VerificationResult:
        return self.verifier.verify_expectation(
            expectation=VerificationExpectation("window_focused", expected),
            focused=focused,
        )
