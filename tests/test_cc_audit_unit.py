from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.computer_control.api import ScreenshotInfo
from app.computer_control.audit import CCAuditEvent, make_cc_audit_event, sanitize_summary
from app.computer_control.fake_driver import FakeComputerControlDriver

UTC = timezone.utc


def test_sanitize_summary_collapses_whitespace_and_truncates() -> None:
    assert sanitize_summary(None) is None
    assert sanitize_summary("a\n b\t c") == "a b c"

    long = "x" * 500
    s = sanitize_summary(long, max_len=10)
    assert s is not None
    assert len(s) == 10
    assert s.endswith("…")


def test_audit_event_validate_rejects_naive_timestamp_and_bad_decision_and_negative_duration() -> None:
    with pytest.raises(ValueError):
        CCAuditEvent(operation="cc_action_done", timestamp=datetime(2020, 1, 1)).validate()  # naive

    aware_ts = datetime(2020, 1, 1, tzinfo=UTC)

    with pytest.raises(ValueError):
        CCAuditEvent(operation="cc_action_done", timestamp=aware_ts, decision="maybe").validate()

    with pytest.raises(ValueError):
        CCAuditEvent(operation="cc_action_done", timestamp=aware_ts, duration_ms=-1).validate()

    # ok
    CCAuditEvent(operation="cc_action_done", timestamp=aware_ts, decision="allowed", duration_ms=0).validate()


def test_make_cc_audit_event_to_dict_is_json_safe_and_metadata_only() -> None:
    ev = make_cc_audit_event(
        operation="cc_action_done",
        target_summary="hello\nworld",
        decision="allowed",
        duration_ms=12,
        artifact_ref="fake:screenshot:1",
    )
    d = ev.to_dict()
    assert d["operation"] == "cc_action_done"
    assert d["decision"] == "allowed"
    assert d["duration_ms"] == 12
    assert d["artifact_ref"] == "fake:screenshot:1"
    assert d["target_summary"] == "hello world"

    # Ensure we are not leaking prohibited payload fields
    assert "screenshot_bytes" not in d
    assert "typed_text" not in d
    assert "image_bytes" not in d


def test_fake_driver_returns_metadata_only_screenshotinfo() -> None:
    drv = FakeComputerControlDriver(width=320, height=200)
    s1 = drv.screenshot()
    s2 = drv.screenshot()

    assert isinstance(s1, ScreenshotInfo)
    assert (s1.width, s1.height) == (320, 200)
    assert s1.artifact_ref == "fake:screenshot:1"
    assert s2.artifact_ref == "fake:screenshot:2"

    # Contract: ScreenshotInfo must not have any bytes payload
    assert not hasattr(s1, "bytes")
    assert not hasattr(s1, "data")
