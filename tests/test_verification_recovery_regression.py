from app.computer_control.verification import (
    ComputerVerifier,
    VerificationExpectation,
    VerificationStatus,
)
from app.computer_control.recovery import FailureKind, RecoveryAction, RecoveryEngine
from app.computer.regression import RegressionDetector, RegressionStatus


def test_verification_requires_explicit_postcondition():
    result = ComputerVerifier().verify_expectation(
        expectation=VerificationExpectation("target_visible", "Compile"),
        found=True,
    )
    assert result.status is VerificationStatus.VERIFIED
    assert result.verified


def test_target_absence_is_a_valid_verified_outcome():
    result = ComputerVerifier().verify_target_absent(found=False, expected_label="Save")
    assert result.status is VerificationStatus.VERIFIED


def test_state_transition_detects_unchanged_state_as_failure():
    result = ComputerVerifier().verify_state_transition(
        before_fingerprint="before",
        after_fingerprint="before",
        changed=False,
    )
    assert result.status is VerificationStatus.FAILED


def test_missing_state_is_inconclusive_not_success():
    result = ComputerVerifier().verify_state_transition(
        before_fingerprint=None,
        after_fingerprint="after",
        changed=True,
    )
    assert result.status is VerificationStatus.INCONCLUSIVE


def test_invalid_expectation_fails_closed():
    try:
        ComputerVerifier().verify_expectation(
            expectation=VerificationExpectation("unknown"),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid verification expectation was accepted")


def test_recovery_classifies_security_failure_as_terminal():
    result = RecoveryEngine(max_attempts=5).decide(
        failure_reason="denied_scope_revalidation",
        attempt=0,
    )
    assert result.action is RecoveryAction.ABORT
    assert result.failure_kind in {FailureKind.PERMISSION, FailureKind.SCOPE}


def test_recovery_is_bounded_and_transient_can_retry():
    engine = RecoveryEngine(max_attempts=1)
    assert engine.decide(failure_reason="timeout", attempt=0).action is RecoveryAction.RETRY
    assert engine.decide(failure_reason="timeout", attempt=1).action is RecoveryAction.ABORT


def test_target_and_window_recovery_do_not_grant_authority():
    engine = RecoveryEngine(max_attempts=2)
    target = engine.decide(failure_reason="target_not_found", attempt=0)
    window = engine.decide(failure_reason="window_not_focused", attempt=0)
    assert target.action is RecoveryAction.REFIND_TARGET
    assert window.action is RecoveryAction.REFOCUS_WINDOW
    assert target.failure_kind is FailureKind.TARGET
    assert window.failure_kind is FailureKind.WINDOW


def test_negative_attempt_is_rejected():
    try:
        RecoveryEngine().decide(failure_reason="timeout", attempt=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative recovery attempt was accepted")


def test_regression_detector_is_deterministic():
    detector = RegressionDetector()
    same = detector.compare_fingerprints(baseline="abc", candidate="abc")
    changed = detector.compare_fingerprints(baseline="abc", candidate="xyz")
    missing = detector.compare_fingerprints(baseline="abc", candidate=None)
    assert same.status is RegressionStatus.NO_REGRESSION
    assert changed.status is RegressionStatus.REGRESSION
    assert missing.status is RegressionStatus.INCONCLUSIVE


def test_failed_verification_is_regression_evidence():
    from app.computer_control.verification import VerificationResult

    result = RegressionDetector().compare_verification(
        VerificationResult(VerificationStatus.FAILED, "target_not_visible", ("Compile",))
    )
    assert result.status is RegressionStatus.REGRESSION


def test_inconclusive_verification_never_becomes_safe_regression_result():
    from app.computer_control.verification import VerificationResult

    result = RegressionDetector().compare_verification(
        VerificationResult(VerificationStatus.INCONCLUSIVE, "missing_state_fingerprint")
    )
    assert result.status is RegressionStatus.INCONCLUSIVE
    assert not result.safe
