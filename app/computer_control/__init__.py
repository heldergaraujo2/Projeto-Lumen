"""Computer Control core (pure modules).

CC-2 introduces a pure core + FakeDriver for tests.
OS-specific automation must live outside app/tools/ and outside this package core,
except in dedicated platform driver modules (e.g., app/computer_control/windows/driver.py).
"""
