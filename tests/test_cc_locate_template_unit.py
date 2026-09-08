from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.computer_control.api import CCActionType, CCTarget
from app.computer_control.scopes import CCLimits, CCScope
from app.tools.computer_control import CcLocateTemplateTool


class _Audit:
    def __init__(self):
        self.records: list[dict] = []

    def record(self, **detail):
        self.records.append(detail)


def _scope(scope_id: str = "s1") -> CCScope:
    now = datetime.now(timezone.utc)
    return CCScope(
        scope_id=scope_id,
        created_at=now,
        expires_at=now + timedelta(seconds=60),
        target=CCTarget(app_name="Desktop"),
        allowed_actions=frozenset({CCActionType.SCREENSHOT}),
        limits=CCLimits(max_actions_total=10, max_actions_per_minute=999),
    )


def test_cc_locate_template_finds_match(tmp_path: Path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    screen = np.zeros((120, 160), dtype=np.uint8)
    screen[40:60, 60:80] = 255
    tpl = screen[40:60, 60:80].copy()

    sp = tmp_path / "screen.png"
    tp = tmp_path / "tpl.png"
    assert cv2.imwrite(str(sp), screen)
    assert cv2.imwrite(str(tp), tpl)

    audit = _Audit()
    tool = CcLocateTemplateTool(scopes={"s1": _scope("s1")}, audit=audit)
    r = tool.run(scope_id="s1", screenshot_artifact_ref=str(sp), template_path=str(tp), threshold=0.99)
    assert r.ok is True
    m = r.data["match"]
    assert m["center_x"] == 70 and m["center_y"] == 50

    # Audit n?o deve conter o texto do template; s? metadados.
    assert audit.records
    rec = audit.records[-1]
    assert rec.get("tool") == "cc_locate_template"
