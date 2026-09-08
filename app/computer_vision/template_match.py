from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import importlib


@dataclass(frozen=True)
class TemplateMatch:
    confidence: float
    x: int
    y: int
    w: int
    h: int
    center_x: int
    center_y: int


def _import_cv2():
    try:
        return importlib.import_module("cv2")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "OpenCV (cv2) n?o est? instalado. Instale opencv-python para usar vis?o local."
        ) from exc


def locate_template(
    *,
    screenshot_path: str | Path,
    template_path: str | Path,
    threshold: float = 0.90,
) -> Optional[TemplateMatch]:
    """Localiza um template dentro de um screenshot via matchTemplate (offline).

    Retorna None se n?o encontrar acima do threshold.
    """
    if not (isinstance(threshold, (int, float)) and 0.0 < float(threshold) <= 1.0):
        raise ValueError("threshold deve ser float em (0..1].")

    sp = Path(screenshot_path)
    tp = Path(template_path)
    if not sp.exists():
        raise FileNotFoundError(f"screenshot n?o existe: {sp}")
    if not tp.exists():
        raise FileNotFoundError(f"template n?o existe: {tp}")

    cv2 = _import_cv2()

    screen = cv2.imread(str(sp), cv2.IMREAD_GRAYSCALE)
    tpl = cv2.imread(str(tp), cv2.IMREAD_GRAYSCALE)
    if screen is None:
        raise ValueError(f"Falha ao ler screenshot como imagem: {sp}")
    if tpl is None:
        raise ValueError(f"Falha ao ler template como imagem: {tp}")

    th, tw = tpl.shape[:2]
    sh, sw = screen.shape[:2]
    if th <= 0 or tw <= 0:
        raise ValueError("template inv?lido (dimens?es <= 0).")
    if th > sh or tw > sw:
        return None

        # matchTemplate: templates uniformes (baixa vari?ncia) quebram CCOEFF_NORMED.
    # Fallback para SQDIFF_NORMED (menor ? melhor) quando o template ? quase constante.
    tpl_std = float(tpl.std())
    if tpl_std < 1e-6:
        method = cv2.TM_SQDIFF_NORMED
        res = cv2.matchTemplate(screen, tpl, method)
        min_val, _max_val, min_loc, _max_loc = cv2.minMaxLoc(res)
        conf = 1.0 - float(min_val)
        if conf < float(threshold):
            return None
        x, y = min_loc
    else:
        method = cv2.TM_CCOEFF_NORMED
        res = cv2.matchTemplate(screen, tpl, method)
        _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(res)
        conf = float(max_val)
        if conf < float(threshold):
            return None
        x, y = max_loc

    w, h = int(tw), int(th)
    return TemplateMatch(
        confidence=conf,
        x=int(x),
        y=int(y),
        w=w,
        h=h,
        center_x=int(x + w // 2),
        center_y=int(y + h // 2),
    )
