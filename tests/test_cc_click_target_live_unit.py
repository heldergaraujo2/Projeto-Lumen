from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.ai.vision_locator import VisionLocateResult
from app.computer_control.api import CCActionType, CCTarget, ScreenshotInfo
from app.computer_control.scopes import CCLimits, CCScope
from app.tools.computer_control import CcClickTargetLiveTool


class _Audit:
    def __init__(self):
        self.records: list[dict] = []
    def record(self, **detail):
        self.records.append(detail)


class _Driver:
    def __init__(self, artifact: Path):
        self.artifact = artifact
        self.moved: tuple[int, int] | None = None
        self.clicked: str | None = None

    def screenshot(self, *, target=None):
        self.artifact.write_bytes(b"dummy")
        return ScreenshotInfo(width=1000, height=500, artifact_ref=str(self.artifact))

    def mouse_move_to(self, *, x: int, y: int, target=None):
        self.moved = (x, y)
        return (x, y)

    def mouse_click(self, *, button: str = "left", target=None):
        self.clicked = button
        return (0, 0)


class _Locator:
    def locate(self, *, image_path, query: str):
        return VisionLocateResult(
            x_norm=0.45, y_norm=0.30, w_norm=0.10, h_norm=0.20,
            confidence=0.9, provider="openai", model="unit",
        )


def _scope(scope_id: str = "s1") -> CCScope:
    now = datetime.now(timezone.utc)
    return CCScope(
        scope_id=scope_id,
        created_at=now,
        expires_at=now + timedelta(seconds=60),
        target=CCTarget(app_name="Desktop"),
        allowed_actions=frozenset({CCActionType.SCREENSHOT, CCActionType.MOUSE_MOVE, CCActionType.MOUSE_CLICK}),
        limits=CCLimits(max_actions_total=10, max_actions_per_minute=999),
    )


def test_cc_click_target_live_provider_path(tmp_path: Path):
    artifact = tmp_path / "shot.png"
    driver = _Driver(artifact)
    scope = _scope("s1")

    tool = CcClickTargetLiveTool(
        scopes={"s1": scope},
        driver=driver,
        locator=_Locator(),
        templates_dir=tmp_path / "templates",
        audit=_Audit(),
    )

    r = tool.run(
        scope_id="s1",
        target_id="play_button",
        query="Click the Play button",
        offline_threshold=0.85,
        learn=False,
        button="left",
    )
    assert r.ok is True
    assert driver.moved == (500, 200)
    assert driver.clicked == "left"
    assert scope.actions_used == 3
