from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.computer_control.verification import VerificationResult, VerificationStatus


class RegressionStatus(str, Enum):
    NO_REGRESSION = "no_regression"
    REGRESSION = "regression"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class RegressionResult:
    status: RegressionStatus
    reason: str
    evidence: tuple[str, ...] = ()

    @property
    def safe(self) -> bool:
        return self.status is RegressionStatus.NO_REGRESSION


class RegressionDetector:
    """Deterministic comparison layer; it does not modify runtime state."""

    def compare_fingerprints(self, *, baseline: str | None, candidate: str | None) -> RegressionResult:
        if not baseline or not candidate:
            return RegressionResult(
                RegressionStatus.INCONCLUSIVE,
                "missing_fingerprint",
                tuple(x for x in (baseline, candidate) if x),
            )
        if baseline == candidate:
            return RegressionResult(RegressionStatus.NO_REGRESSION, "fingerprint_match", (baseline,))
        return RegressionResult(
            RegressionStatus.REGRESSION,
            "fingerprint_changed",
            (baseline, candidate),
        )

    def compare_verification(self, result: VerificationResult) -> RegressionResult:
        if result.status is VerificationStatus.INCONCLUSIVE:
            return RegressionResult(RegressionStatus.INCONCLUSIVE, "verification_inconclusive", result.evidence)
        if result.status is VerificationStatus.FAILED:
            return RegressionResult(RegressionStatus.REGRESSION, "verification_failed", result.evidence)
        return RegressionResult(RegressionStatus.NO_REGRESSION, "verification_passed", result.evidence)
