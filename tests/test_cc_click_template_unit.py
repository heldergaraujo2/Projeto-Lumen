from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.scopes import CCLimits, CCScope
from app.computer_vision.template_match import TemplateMatch
from app.tools.computer_control import CcClickTemplateTool


class _Audit:
    def __init__(self):
        self.records: list[dict] = []

    def record(self, **detail):
        self.records.append(detail)


class _Driver:
    def __init__(self):
        self.moved: tuple[int, int] | None = None
        self.clicked: str | None = None

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
        allowed_actions=frozenset({CCActionType.MOUSE_MOVE, CCActionType.MOUSE_CLICK}),
        limits=CCLimits(max_actions_total=10, max_actions_per_minute=999),
    )


def test_cc_click_template_moves_and_clicks(monkeypatch, tmp_path: Path):
    sp = tmp_path / "screen.png"
    tp = tmp_path / "tpl.png"
    sp.write_bytes(b"dummy")
    tp.write_bytes(b"dummy")

    def _fake_locate_template(*, screenshot_path, template_path, threshold=0.85):
        return TemplateMatch(confidence=0.99, x=10, y=20, w=30, h=40, center_x=25, center_y=40)

    import app.computer_vision.template_match as tm
    monkeypatch.setattr(tm, "locate_template", _fake_locate_template)

    audit = _Audit()
    driver = _Driver()
    scope = _scope("s1")
    tool = CcClickTemplateTool(scopes={"s1": scope}, driver=driver, audit=audit)
    r = tool.run(scope_id="s1", screenshot_artifact_ref=str(sp), template_path=str(tp), threshold=0.85)
    assert r.ok is True
    assert driver.moved == (25, 40)
    assert driver.clicked == "left"
    assert scope.actions_used == 2
    assert audit.records
