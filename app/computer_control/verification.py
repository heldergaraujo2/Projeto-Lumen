from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    reason: str
    evidence: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return self.status is VerificationStatus.VERIFIED


@dataclass(frozen=True)
class VerificationExpectation:
    """Explicit post-condition; verification never grants execution authority."""

    kind: str
    value: str | None = None

    def validate(self) -> None:
        allowed = {
            "target_visible",
            "target_absent",
            "window_focused",
            "state_changed",
            "state_unchanged",
        }
        if self.kind not in allowed:
            raise ValueError("unsupported verification expectation")
        if self.kind in {"target_visible", "target_absent", "window_focused"} and not self.value:
            raise ValueError("verification value is required")


class ComputerVerifier:
    def verify_target_visible(self, *, found, expected_label):
        return VerificationResult(
            VerificationStatus.VERIFIED if found else VerificationStatus.FAILED,
            "target_visible" if found else "target_not_visible",
            (expected_label,),
        )

    def verify_target_absent(self, *, found, expected_label):
        return VerificationResult(
            VerificationStatus.FAILED if found else VerificationStatus.VERIFIED,
            "target_still_visible" if found else "target_absent",
            (expected_label,),
        )

    def verify_window(self, *, focused, expected):
        return VerificationResult(
            VerificationStatus.VERIFIED if focused else VerificationStatus.FAILED,
            "window_focused" if focused else "window_not_focused",
            (expected,),
        )

    def verify_state_transition(self, *, before_fingerprint, after_fingerprint, changed: bool):
        if not before_fingerprint or not after_fingerprint:
            return VerificationResult(
                VerificationStatus.INCONCLUSIVE,
                "missing_state_fingerprint",
                tuple(x for x in (before_fingerprint, after_fingerprint) if x),
            )
        return VerificationResult(
            VerificationStatus.VERIFIED if changed else VerificationStatus.FAILED,
            "state_changed" if changed else "state_unchanged",
            (before_fingerprint, after_fingerprint),
        )

    def verify_expectation(
        self, *, expectation: VerificationExpectation, found=None, focused=None,
        before_fingerprint=None, after_fingerprint=None
    ):
        expectation.validate()
        if expectation.kind == "target_visible":
            return self.verify_target_visible(found=bool(found), expected_label=expectation.value)
        if expectation.kind == "target_absent":
            return self.verify_target_absent(found=bool(found), expected_label=expectation.value)
        if expectation.kind == "window_focused":
            return self.verify_window(focused=bool(focused), expected=expectation.value)
        changed = before_fingerprint != after_fingerprint
        return self.verify_state_transition(
            before_fingerprint=before_fingerprint,
            after_fingerprint=after_fingerprint,
            changed=changed if expectation.kind == "state_changed" else not changed,
        )

    def require_verified(self, result: VerificationResult):
        if result.status is not VerificationStatus.VERIFIED:
            raise RuntimeError("computer action not verified: " + result.reason)
