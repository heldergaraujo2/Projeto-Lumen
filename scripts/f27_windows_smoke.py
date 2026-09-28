"""F27 — explicit real Windows smoke validation.

Run only on the real Windows machine that owns the interactive desktop:

    set LUMEN_F27_PHYSICAL_CONFIRM=YES
    python scripts/f27_windows_smoke.py

The script moves the mouse to a safe point and types a short marker only
when the explicit confirmation variable is present.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.computer_control.windows_driver import WindowsComputerControlDriver


def main() -> int:
    if sys.platform != "win32":
        print("F27: NOT_EXECUTED — this gate requires Windows.")
        return 2
    if os.environ.get("LUMEN_F27_PHYSICAL_CONFIRM") != "YES":
        print("F27: NOT_EXECUTED — set LUMEN_F27_PHYSICAL_CONFIRM=YES to arm the smoke test.")
        return 2

    driver = WindowsComputerControlDriver(
        armed=True,
        screenshot_dir=Path(os.environ.get("TEMP", ".")) / "LumenF27",
    )
    info = driver.screenshot()
    print(f"F27 screenshot: PASS ({info.width}x{info.height}) -> {info.artifact_ref}")
    x, y = info.width // 2, info.height // 2
    driver.mouse_move(x, y)
    print(f"F27 mouse move: PASS ({x},{y})")
    driver.type_text("LUMEN_F27_SMOKE")
    print("F27 keyboard typing: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
