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
