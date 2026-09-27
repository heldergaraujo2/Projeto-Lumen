from __future__ import annotations

from pathlib import Path

import pytest

from app.computer_vision.template_match import locate_template


def test_locate_template_finds_simple_square(tmp_path: Path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    screen = np.zeros((120, 160), dtype=np.uint8)
    # white square at (x=60..79, y=40..59)
    screen[40:60, 60:80] = 255
    tpl = screen[40:60, 60:80].copy()

    sp = tmp_path / "screen.png"
    tp = tmp_path / "tpl.png"
    assert cv2.imwrite(str(sp), screen)
    assert cv2.imwrite(str(tp), tpl)

    m = locate_template(screenshot_path=sp, template_path=tp, threshold=0.99)
    assert m is not None
    assert m.x == 60 and m.y == 40
    assert m.w == 20 and m.h == 20
    assert m.center_x == 70 and m.center_y == 50


def test_locate_template_returns_none_when_below_threshold(tmp_path: Path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    screen = np.zeros((60, 60), dtype=np.uint8)
    tpl = (np.ones((10, 10), dtype=np.uint8) * 127)

    sp = tmp_path / "screen.png"
    tp = tmp_path / "tpl.png"
    assert cv2.imwrite(str(sp), screen)
    assert cv2.imwrite(str(tp), tpl)

    m = locate_template(screenshot_path=sp, template_path=tp, threshold=0.99)
    assert m is None
