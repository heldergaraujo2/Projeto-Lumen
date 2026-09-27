from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.computer_control.api import CCActionType, CCTarget, ScreenshotInfo
from app.computer_control.scopes import CCLimits, CCScope
from app.computer_vision.template_match import TemplateMatch
from app.tools.computer_control import CcClickTemplateLiveTool


class _Audit:
    def __init__(self):
        self.records: list[dict] = []

    def record(self, **detail):
        self.records.append(detail)


class _Driver:
    def __init__(
        self,
        artifact: Path,
        *,
        virtual_origin: tuple[int, int] = (0, 0),
        window_rect: tuple[int, int, int, int] | None = (0, 0, 10, 10),
    ):
        self.artifact = artifact
        self.moved: tuple[int, int] | None = None
        self.clicked: str | None = None
        self._virtual_origin = virtual_origin
        self._window_rect = window_rect

    def screenshot(self, *, target=None):
        # arquivo precisa existir (mas nao sobrescreve se ja existir)
        if not self.artifact.exists():
            self.artifact.write_bytes(b"dummy")
        return ScreenshotInfo(width=10, height=10, artifact_ref=str(self.artifact))

    def get_virtual_screen_origin(self) -> tuple[int, int]:
        return self._virtual_origin

    def get_window_rect(self, *, window_title_pattern: str):
        # deterministic: return configured rect if pattern provided
        if not isinstance(window_title_pattern, str) or not window_title_pattern.strip():
            return None
        return self._window_rect

    def mouse_move_to(self, *, x: int, y: int, target=None):
        self.moved = (x, y)
        return (x, y)

    def mouse_click(self, *, button: str = "left", target=None):
        self.clicked = button
        return (0, 0)


def _scope(scope_id: str = "s1", *, window_title_pattern: str = "Unreal") -> CCScope:
    now = datetime.now(timezone.utc)
    return CCScope(
        scope_id=scope_id,
        created_at=now,
        expires_at=now + timedelta(seconds=60),
        target=CCTarget(app_name="Desktop", window_title_pattern=window_title_pattern),
        allowed_actions=frozenset({CCActionType.SCREENSHOT, CCActionType.MOUSE_MOVE, CCActionType.MOUSE_CLICK}),
        limits=CCLimits(max_actions_total=10, max_actions_per_minute=999),
    )


def test_cc_click_template_live_screenshots_locates_and_clicks(monkeypatch, tmp_path: Path):
    template = tmp_path / "tpl.png"
    template.write_bytes(b"dummy")

    artifact = tmp_path / "shot.png"
    driver = _Driver(artifact, virtual_origin=(0, 0), window_rect=(0, 0, 10, 10))

    called: dict = {}

    def _fake_locate_template(*, screenshot_path, template_path, threshold=0.85, search_box=None):
        called["search_box"] = search_box
        return TemplateMatch(confidence=0.99, x=1, y=2, w=3, h=4, center_x=5, center_y=6)

    import app.computer_vision.template_match as tm
    monkeypatch.setattr(tm, "locate_template", _fake_locate_template)

    scope = _scope("s1", window_title_pattern="Unreal")
    tool = CcClickTemplateLiveTool(scopes={"s1": scope}, driver=driver, audit=_Audit())
    r = tool.run(scope_id="s1", template_path=str(template), threshold=0.85, button="left")

    assert r.ok is True
    # top 30% of (0..10) => y2=3
    assert called["search_box"] == (0, 0, 10, 3)
    assert driver.moved == (5, 6)
    assert driver.clicked == "left"
    assert scope.actions_used == 3


def test_cc_click_template_live_fail_closed_when_window_rect_not_found(tmp_path: Path):
    template = tmp_path / "tpl.png"
    template.write_bytes(b"dummy")

    artifact = tmp_path / "shot.png"
    driver = _Driver(artifact, virtual_origin=(0, 0), window_rect=None)

    scope = _scope("s1", window_title_pattern="Unreal")
    tool = CcClickTemplateLiveTool(scopes={"s1": scope}, driver=driver, audit=_Audit())
    r = tool.run(scope_id="s1", template_path=str(template), threshold=0.85, button="left")

    assert r.ok is False
    assert r.error == "window_rect_not_found"
    assert scope.actions_used == 1  # screenshot consumed, then fail-closed before move/click


def test_cc_click_template_live_scopes_to_window_top_with_negative_virtual_origin_and_two_matches(tmp_path: Path):
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    # Build a non-uniform template (avoid std==0 edge case).
    tpl = np.zeros((20, 20), dtype=np.uint8)
    tpl[5:15, 9:11] = 255
    tpl[9:11, 5:15] = 255

    screen = np.zeros((200, 1000), dtype=np.uint8)

    # Place two identical matches: one outside the Unreal window, one inside.
    # Left match at x=100 (outside), right match at x=700 (inside).
    screen[40:60, 100:120] = tpl
    screen[40:60, 700:720] = tpl

    artifact = tmp_path / "shot.png"
    template = tmp_path / "tpl.png"
    cv2.imwrite(str(artifact), screen)
    cv2.imwrite(str(template), tpl)

    # Simulate multi-monitor where virtual origin is negative (monitor to the left).
    # Virtual origin = (-1000, 0), so pixel x = virtual_x - (-1000) = virtual_x + 1000.
    # Define Unreal window rect in *virtual coords* covering only the right match:
    # left=-400 => x1=600; right=0 => x2=1000.
    driver = _Driver(
        artifact,
        virtual_origin=(-1000, 0),
        window_rect=(-400, 0, 0, 200),
    )

    scope = _scope("s1", window_title_pattern="Unreal")
    tool = CcClickTemplateLiveTool(scopes={"s1": scope}, driver=driver, audit=_Audit())
    r = tool.run(scope_id="s1", template_path=str(template), threshold=0.99, button="left")

    assert r.ok is True
    # Expected center of right match at x=700+10, y=40+10
    assert driver.moved == (710, 50)
    assert driver.clicked == "left"
    assert scope.actions_used == 3
