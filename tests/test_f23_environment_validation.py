"""F23 — testes determinísticos do gate de ambiente.

Os testes são deliberadamente não-físicos: CI não deve declarar que mouse,
teclado, UI Automation ou Unreal foram testados só porque roda em Windows.
"""
from __future__ import annotations

import sys

from app.validation.environment import (
    detect_environment,
    physical_validation_status,
    unreal_validation_status,
)


def test_environment_detection_is_structured_and_side_effect_free():
    env = detect_environment()
    assert env.os_name
    assert env.platform
    assert env.python
    assert isinstance(env.interactive_session, bool)
    assert isinstance(env.display_available, bool)
    assert env.to_dict()["windows_native"] is (sys.platform == "win32")


def test_physical_validation_never_claimed_by_environment_detection():
    env = detect_environment()
    assert env.physical_validation_allowed is False
    assert physical_validation_status(env) == "NOT_EXECUTED"


def test_unreal_validation_never_claimed_by_environment_detection():
    env = detect_environment()
    assert env.unreal_validation_allowed is False
    assert unreal_validation_status(env) == "NOT_EXECUTED"


def test_windows_does_not_imply_physical_or_unreal_validation(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    env = detect_environment()
    assert env.windows_native is True
    assert env.display_available is True
    assert env.physical_validation_allowed is False
    assert env.unreal_validation_allowed is False
