"""F28 real-provider smoke gate.

Runs only when explicitly armed. On Windows it captures one real screenshot
through the native driver and sends it to the local Ollama multimodal provider.
No mouse/keyboard action is executed and no ComputerControl permission is
granted by this script.

PowerShell:
    $env:LUMEN_F28_PHYSICAL_CONFIRM="YES"
    $env:LUMEN_OLLAMA_VISION_MODEL="qwen3-vl:2b-instruct"
    python scripts/f28_vision_smoke.py

Optional:
    $env:LUMEN_OLLAMA_VISION_MODEL="qwen3-vl:2b-instruct"
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.computer_control.vision import OllamaVisionProvider, VisionRequest
from app.computer_control.vision_grounding import VisionGroundingPipeline


def main() -> int:
    if sys.platform != "win32":
        print("F28: NOT_EXECUTED — real screenshot smoke requires Windows.")
        return 2
    if os.environ.get("LUMEN_F28_PHYSICAL_CONFIRM") != "YES":
        print("F28: NOT_EXECUTED — set LUMEN_F28_PHYSICAL_CONFIRM=YES.")
        return 2

    from app.computer_control.windows_driver import WindowsComputerControlDriver

    evidence_dir = Path(os.environ.get("TEMP", ".")) / "LumenF28"
    driver = WindowsComputerControlDriver(armed=False, screenshot_dir=evidence_dir)
    # Screenshot is observation only; physical input remains disarmed.
    info = driver.screenshot()

    model = os.environ.get("LUMEN_OLLAMA_VISION_MODEL", "qwen3-vl:2b-instruct")
    provider = OllamaVisionProvider(model=model)
    result = VisionGroundingPipeline(provider).observe_and_resolve(
        VisionRequest(
            Path(info.artifact_ref),
            "Identify visible interactive UI elements. Return their labels and pixel bounding boxes.",
        ),
        label=os.environ.get("LUMEN_F28_TARGET_LABEL", "Compile"),
    )

    print(f"F28 screenshot: PASS ({info.width}x{info.height}) -> {info.artifact_ref}")
    print(f"F28 provider: {provider.name}:{provider.model}")
    print(f"F28 elements: {len(result.candidates)}")
    if result.target is None:
        print("F28 target: NOT_FOUND (vision provider worked; no matching label)")
    else:
        print(
            "F28 target: PASS "
            f"{result.target.label} @ {result.target.center()} "
            f"confidence={result.target.confidence:.3f}"
        )
    print("F28 physical input: DISARMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
