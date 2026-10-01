"""F27 — Windows driver safety/contract tests.

These tests never send real mouse/keyboard input. Physical execution belongs
to the explicit F27 smoke runner on a real interactive Windows session.
"""
from __future__ import annotations

import os
import pytest

from app.computer_control.windows_driver import (
    WindowsComputerControlError,
    WindowsComputerControlDriver,
)


def test_windows_driver_is_disarmed_by_default():
    if os.name != "nt":
        pytest.skip("Windows-only driver")
    driver = WindowsComputerControlDriver()
    assert driver.armed is False
    with pytest.raises(WindowsComputerControlError, match="disarmed"):
        driver.key_press("ENTER")


def test_windows_driver_requires_explicit_arm_for_input():
    if os.name != "nt":
        pytest.skip("Windows-only driver")
    driver = WindowsComputerControlDriver(armed=False)
    with pytest.raises(WindowsComputerControlError):
        driver.mouse_move(1, 1)


def test_non_windows_fails_closed():
    if os.name == "nt":
        pytest.skip("non-Windows contract test")
    with pytest.raises(WindowsComputerControlError, match="requires Windows"):
        WindowsComputerControlDriver()


def test_focus_window_verifies_foreground_handle(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows-only driver")

    import app.computer_control.windows_driver as module

    handle = 12345
    calls = {"set": 0, "restore": 0}
    monkeypatch.setattr(module._USER32, "IsWindow", lambda hwnd: True)
    monkeypatch.setattr(
        module._USER32,
        "ShowWindow",
        lambda hwnd, command: calls.__setitem__("restore", calls["restore"] + 1),
    )
    monkeypatch.setattr(
        module._USER32,
        "SetForegroundWindow",
        lambda hwnd: calls.__setitem__("set", calls["set"] + 1) or 1,
    )
    monkeypatch.setattr(module._USER32, "GetForegroundWindow", lambda: handle)

    driver = WindowsComputerControlDriver(armed=True)
    driver.focus_window(module.CCTarget(window_handle=handle))

    assert calls["set"] == 1
    assert calls["restore"] == 1


def test_focus_window_rejects_false_foreground_success(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows-only driver")

    import app.computer_control.windows_driver as module

    handle = 12345
    monkeypatch.setattr(module._USER32, "IsWindow", lambda hwnd: True)
    monkeypatch.setattr(module._USER32, "ShowWindow", lambda hwnd, command: 1)
    monkeypatch.setattr(module._USER32, "SetForegroundWindow", lambda hwnd: 1)
    monkeypatch.setattr(module._USER32, "GetForegroundWindow", lambda: 67890)

    driver = WindowsComputerControlDriver(armed=True)
    with pytest.raises(WindowsComputerControlError, match="focus verification failed"):
        driver.focus_window(module.CCTarget(window_handle=handle))


def test_focus_window_reports_set_foreground_failure(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows-only driver")

    import app.computer_control.windows_driver as module

    handle = 12345
    monkeypatch.setattr(module._USER32, "IsWindow", lambda hwnd: True)
    monkeypatch.setattr(module._USER32, "ShowWindow", lambda hwnd, command: 1)
    monkeypatch.setattr(module._USER32, "SetForegroundWindow", lambda hwnd: 0)
    monkeypatch.setattr(module._USER32, "GetForegroundWindow", lambda: 67890)

    driver = WindowsComputerControlDriver(armed=True)
    with pytest.raises(WindowsComputerControlError, match="SetForegroundWindow failed"):
        driver.focus_window(module.CCTarget(window_handle=handle))
