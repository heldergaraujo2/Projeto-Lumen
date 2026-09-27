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

def test_cc_click_target_live_offline_path_is_window_scoped(tmp_path: Path):
    cv2 = __import__("pytest").importorskip("cv2")
    import numpy as np

    # Create template and screenshot with two identical matches, but only one inside window rect.
    tpl = np.zeros((20, 20), dtype=np.uint8)
    tpl[5:15, 9:11] = 255
    tpl[9:11, 5:15] = 255

    screen = np.zeros((200, 1000), dtype=np.uint8)
    screen[40:60, 100:120] = tpl   # outside
    screen[40:60, 700:720] = tpl   # inside

    artifact = tmp_path / "shot.png"
    cv2.imwrite(str(artifact), screen)

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    tpl_path = templates_dir / "play_button.png"
    cv2.imwrite(str(tpl_path), tpl)

    class _Driver2(_Driver):
        def __init__(self, artifact_path: Path):
            super().__init__(artifact_path)
            self._virtual_origin = (-1000, 0)
            self._window_rect = (-400, 0, 0, 200)  # maps to x1=600..1000

        def screenshot(self, *, target=None):
            # do not overwrite
            return ScreenshotInfo(width=1000, height=200, artifact_ref=str(self.artifact))

        def get_virtual_screen_origin(self) -> tuple[int, int]:
            return self._virtual_origin

        def get_window_rect(self, *, window_title_pattern: str):
            if not isinstance(window_title_pattern, str) or not window_title_pattern.strip():
                return None
            return self._window_rect

    driver = _Driver2(artifact)
    scope = _scope("s1")
    # Inject window_title_pattern so offline path can scope properly.
    scope = CCScope(
        scope_id=scope.scope_id,
        created_at=scope.created_at,
        expires_at=scope.expires_at,
        target=CCTarget(app_name="Desktop", window_title_pattern="Unreal"),
        allowed_actions=scope.allowed_actions,
        limits=scope.limits,
    )

    tool = CcClickTargetLiveTool(
        scopes={"s1": scope},
        driver=driver,
        locator=_Locator(),
        templates_dir=templates_dir,
        audit=_Audit(),
    )

    r = tool.run(
        scope_id="s1",
        target_id="play_button",
        query="Click the Play button",
        offline_threshold=0.99,
        learn=False,
        button="left",
    )
    assert r.ok is True
    assert r.data["used_template"] is True
    # Expected inside match center at x=710, y=50
    assert driver.moved == (710, 50)
    assert driver.clicked == "left"
    assert scope.actions_used == 3
