from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    def __init__(self, artifact: Path):
        self.artifact = artifact
        self.moved: tuple[int, int] | None = None
        self.clicked: str | None = None

    def screenshot(self, *, target=None):
        # arquivo precisa existir
        self.artifact.write_bytes(b"dummy")
        return ScreenshotInfo(width=10, height=10, artifact_ref=str(self.artifact))

    def mouse_move_to(self, *, x: int, y: int, target=None):
        self.moved = (x, y)
        return (x, y)

    def mouse_click(self, *, button: str = "left", target=None):
        self.clicked = button
        return (0, 0)


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


def test_cc_click_template_live_screenshots_locates_and_clicks(monkeypatch, tmp_path: Path):
    template = tmp_path / "tpl.png"
    template.write_bytes(b"dummy")

    artifact = tmp_path / "shot.png"
    driver = _Driver(artifact)

    def _fake_locate_template(*, screenshot_path, template_path, threshold=0.85):
        return TemplateMatch(confidence=0.99, x=1, y=2, w=3, h=4, center_x=50, center_y=60)

    import app.computer_vision.template_match as tm
    monkeypatch.setattr(tm, "locate_template", _fake_locate_template)

    scope = _scope("s1")
    tool = CcClickTemplateLiveTool(scopes={"s1": scope}, driver=driver, audit=_Audit())
    r = tool.run(scope_id="s1", template_path=str(template), threshold=0.85, button="left")
    assert r.ok is True
    assert driver.moved == (50, 60)
    assert driver.clicked == "left"
    assert scope.actions_used == 3
