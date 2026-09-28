# F27 — Real Windows Computer Validation

## Objetivo

F27 is the operational gate between the implemented Computer Control
contracts and a real Windows desktop. The phase adds a native Windows
driver, a fail-closed physical arming gate, deterministic safety tests, and
an explicit smoke runner.

## Delivered

- app/computer_control/windows_driver.py: real mouse, keyboard, focus and screenshot support.
- tests/test_f27_windows_driver.py: safety and fail-closed contract tests.
- scripts/f27_windows_smoke.py: explicit physical gate using
  LUMEN_F27_PHYSICAL_CONFIRM=YES.
- .github/workflows/windows-validation.yml: Windows CI compile and full pytest.
- Hosted CI does not count as proof of physical desktop validation.

## Security invariants

1. The native driver is never an authority source.
2. Input is blocked while disarmed.
3. Production execution remains behind PermissionManager, Policy, Scope,
   and Checkpoint.
4. The smoke runner requires explicit environment confirmation.
5. No test or CI job can infer physical validation from win32 alone.
6. Screenshots are stored as evidence artifacts, not embedded in audit events.

## Status semantics

- IMPLEMENTED: code and automated safety validation complete.
- WINDOWS_CI_GREEN: automated Windows environment validation complete.
- PHYSICAL_SMOKE_PENDING: real interactive mouse/keyboard screenshot smoke
  has not been executed on the user's Windows desktop.
- F27_COMPLETE: only after Windows CI and explicit physical smoke evidence.
