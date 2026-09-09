from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI  # type: ignore[import-not-found]

from app.ai.vision_locator import VisionLocateResult


class OpenAIVisionLocator:
    """Locate UI target in an image using OpenAI vision.

    Returns a normalized bounding box (0..1) plus confidence (0..1).
    """

    def __init__(self, *, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.environ.get("LUMEN_VISION_MODEL", "gpt-4o-mini")
        self._client = OpenAI(api_key=api_key)

    def locate(self, *, image_path: str | Path, query: str) -> Optional[VisionLocateResult]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be non-empty string")

        p = Path(image_path)
        if not p.exists():
            raise FileNotFoundError(f"image not found: {p}")

        b64 = base64.b64encode(p.read_bytes()).decode("ascii")

        prompt = "\n".join(
            [
                "You are a precise UI locator.",
                "Given the screenshot, find the UI element described by the query.",
                "Return ONLY valid JSON with this schema:",
                "{"
                "\"found\": boolean, "
                "\"x_norm\": number, \"y_norm\": number, \"w_norm\": number, \"h_norm\": number, "
                "\"confidence\": number"
                "}",
                "All *_norm fields must be in [0,1]. confidence in [0,1].",
                "If not found, return: {\"found\": false}.",
                f"Query: {query.strip()}",
            ]
        )

        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )

        text = resp.choices[0].message.content or ""
        data = json.loads(text)

        if not isinstance(data, dict) or not data.get("found", False):
            return None

        def clamp01(v: float) -> float:
            return max(0.0, min(1.0, float(v)))

        x = clamp01(float(data["x_norm"]))
        y = clamp01(float(data["y_norm"]))
        w = clamp01(float(data["w_norm"]))
        h = clamp01(float(data["h_norm"]))
        c = clamp01(float(data.get("confidence", 0.5)))

        if w <= 0.0 or h <= 0.0:
            return None

        return VisionLocateResult(
            x_norm=x,
            y_norm=y,
            w_norm=w,
            h_norm=h,
            confidence=c,
            provider="openai",
            model=self.model,
        )
