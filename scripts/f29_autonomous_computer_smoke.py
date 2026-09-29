"""F29 real autonomous computer-agent smoke gate.

This smoke is intentionally benign: the only physical action is moving the mouse
to a vision-grounded target. A checkpoint remains mandatory.

PowerShell:
    $env:LUMEN_F29_PHYSICAL_CONFIRM="YES"
    $env:LUMEN_F29_APPROVE="YES"
    $env:LUMEN_F29_TARGET_LABEL="PowerShell"
    $env:LUMEN_OLLAMA_VISION_MODEL="qwen3-vl:2b-instruct"
    python scripts/f29_autonomous_computer_smoke.py

The first confirmation arms the physical test. The second confirms the
one-shot checkpoint approval. No click, typing, scroll, focus, close, or other
destructive action is performed.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.computer_control.actions import CCActionRequest
from app.computer_control.api import CCActionType, CCTarget, ScreenRegion
from app.computer_control.autonomous_agent import (
    ComputerAgentLimits,
    ComputerAgentState,
    ComputerPlan,
    VisionComputerAgent,
)
from app.computer_control.service import ComputerControlService
from app.computer_control.scopes import CCLimits, CCScope
from app.computer_control.verification import (
    VerificationExpectation,
    VerificationResult,
    VerificationStatus,
)
from app.computer_control.vision import OllamaVisionProvider, VisionRequest
from app.computer_control.vision_grounding import VisionGroundingPipeline
from app.security.permissions import PermissionLevel, PermissionManager


@dataclass(frozen=True)
class MovePlanner:
    target_label: str

    def plan(self, *, goal, observation, previous_reason="") -> ComputerPlan:
        return ComputerPlan(
            action=CCActionRequest(
                CCActionType.MOUSE_MOVE,
                target=observation.target,
            ),
            expectation=VerificationExpectation(
                "target_visible",
                self.target_label,
            ),
            target_label=self.target_label,
        )


@dataclass(frozen=True)
class VisibleVerifier:
    def verify(self, *, expectation, observation) -> VerificationResult:
        found = observation.target is not None
        return VerificationResult(
            VerificationStatus.VERIFIED if found else VerificationStatus.FAILED,
            "target_visible" if found else "target_not_visible",
            (expectation.value or "",),
        )


def main() -> int:
    if sys.platform != "win32":
        print("F29: NOT_EXECUTED — real autonomous smoke requires Windows.")
        return 2
    if os.environ.get("LUMEN_F29_PHYSICAL_CONFIRM") != "YES":
        print("F29: NOT_EXECUTED — set LUMEN_F29_PHYSICAL_CONFIRM=YES.")
        return 2

    from app.computer_control.windows_driver import WindowsComputerControlDriver

    evidence_dir = Path(os.environ.get("TEMP", ".")) / "LumenF29"
    driver = WindowsComputerControlDriver(armed=True, screenshot_dir=evidence_dir)
    info = driver.screenshot()

    target_label = os.environ.get("LUMEN_F29_TARGET_LABEL", "PowerShell")
    model = os.environ.get("LUMEN_OLLAMA_VISION_MODEL", "qwen3-vl:2b-instruct")

    permissions = PermissionManager(granted=(PermissionLevel.COMPUTER_CONTROL,))
    service = ComputerControlService(
        permissions=permissions,
        driver=driver,
        require_checkpoint=True,
    )
    created = datetime.now(timezone.utc)
    scope = CCScope(
        scope_id="F29-REAL-SMOKE",
        created_at=created,
        expires_at=created + timedelta(minutes=2),
        target=CCTarget(app_name="PowerShell"),
        allowed_actions=frozenset({CCActionType.MOUSE_MOVE}),
        limits=CCLimits(max_actions_total=1, max_actions_per_minute=1),
        allowed_region=ScreenRegion(0, 0, info.width, info.height),
    )
    scope.validate()

    provider = OllamaVisionProvider(model=model)
    agent = VisionComputerAgent(
        computer_control=service,
        vision=VisionGroundingPipeline(provider),
        planner=MovePlanner(target_label),
        verifier=VisibleVerifier(),
        limits=ComputerAgentLimits(max_cycles=2, max_replans=0, max_recoveries=0),
    )
    request = VisionRequest(
        Path(info.artifact_ref),
        f"Find ONE visible interactive UI element matching this target label: {target_label!r}.",
        max_output_tokens=128,
    )

    first = agent.run(
        goal=f"move the mouse to {target_label}",
        scope=scope,
        screenshot_request=request,
        target_label=target_label,
    )
    print(f"F29 screenshot: PASS ({info.width}x{info.height}) -> {info.artifact_ref}")
    print(f"F29 provider: {provider.name}:{provider.model}")
    print(f"F29 first state: {first.state.value}")
    print(f"F29 checkpoint: {first.pending_checkpoint_id or 'NONE'}")

    if first.state is not ComputerAgentState.WAITING_APPROVAL:
        print("F29: FAIL — expected checkpoint before physical action.")
        return 1
    if os.environ.get("LUMEN_F29_APPROVE") != "YES":
        print("F29: NOT_EXECUTED — checkpoint not approved; set LUMEN_F29_APPROVE=YES.")
        return 2

    second = agent.run(
        goal=f"move the mouse to {target_label}",
        scope=scope,
        screenshot_request=request,
        target_label=target_label,
        approved_checkpoint_id=first.pending_checkpoint_id,
    )
    print(f"F29 final state: {second.state.value}")
    print(f"F29 cycles: {second.cycles}")
    print(f"F29 replans: {second.replans}")
    print(f"F29 recoveries: {second.recoveries}")
    print("F29 physical action: MOUSE_MOVE ONLY")
    print("F29 click/typing/scroll/focus: NOT EXECUTED")

    if second.state is not ComputerAgentState.COMPLETED:
        print("F29: FAIL — autonomous closed loop did not complete.")
        return 1

    print("F29: PASS — Goal -> Plan -> Observe -> Target -> Checkpoint -> Action -> Verify -> Success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
