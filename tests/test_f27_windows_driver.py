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



def _fake_user32(monkeypatch, *, foreground, set_foreground=True):
    import app.computer_control.windows_driver as module

    class FakeUser32:
        def IsWindow(self, hwnd):
            return True

        def ShowWindow(self, hwnd, command):
            return 1

        def SetForegroundWindow(self, hwnd):
            return 1 if set_foreground else 0

        def GetForegroundWindow(self):
            return foreground

    fake = FakeUser32()
    monkeypatch.setattr(module, "_USER32", fake)
    return module


def test_focus_window_verifies_foreground_handle(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows-only driver")

    module = _fake_user32(monkeypatch, foreground=12345)

    driver = WindowsComputerControlDriver(armed=True)
    driver.focus_window(module.CCTarget(window_handle=12345))


def test_focus_window_rejects_false_foreground_success(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows-only driver")

    module = _fake_user32(monkeypatch, foreground=67890)

    driver = WindowsComputerControlDriver(armed=True)
    with pytest.raises(WindowsComputerControlError, match="focus verification failed"):
        driver.focus_window(module.CCTarget(window_handle=12345))


def test_focus_window_reports_set_foreground_failure(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows-only driver")

    module = _fake_user32(monkeypatch, foreground=67890, set_foreground=False)

    driver = WindowsComputerControlDriver(armed=True)
    with pytest.raises(WindowsComputerControlError, match="SetForegroundWindow failed"):
        driver.focus_window(module.CCTarget(window_handle=12345))
