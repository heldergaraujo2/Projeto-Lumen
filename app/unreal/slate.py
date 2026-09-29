"""F30 — Convert Unreal Slate Inspector snapshots into safe grounded UI targets."""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

from app.computer_control.api import CCTarget
from app.computer_control.grounding import GroundedTarget, GroundingSource

_REF = re.compile(r"\[ref=(?P<ref>[A-Za-z0-9_-]+)\]|\bref=(?P<ref2>[A-Za-z0-9_-]+)")
_POS_SIZE = re.compile(
    r"\bpos=\(\s*(?P<x>-?\d+)\s*,\s*(?P<y>-?\d+)\s*\)"
    r"\s+size=\(\s*(?P<w>\d+)\s*,\s*(?P<h>\d+)\s*\)"
)
_QUOTED_LABEL = re.compile(r'(?P<label>"[^"]+"|\'[^\']+\')')

def _clean_label(value: str) -> str:
    value = re.sub(r"\[ref=[^]]+\]", "", value)
    value = re.sub(r"\bref=[A-Za-z0-9_-]+", "", value)
    value = re.sub(r"\bpos=\([^)]*\)", "", value)
    value = re.sub(r"\bsize=\([^)]*\)", "", value)
    value = re.sub(r"\bsrc=\S+", "", value)
    value = value.strip(" \t-:|")
    match = _QUOTED_LABEL.search(value)
    if match:
        value = match.group("label")[1:-1]
    value = re.sub(r"^\s*(?:button|textbox|tab|menu|combobox|checkbox|window|image|panel|slider|list|tree|toolbar)\s+", "", value, flags=re.I)
    return value.strip()

def _text_items(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        # Unreal MCP wraps the Slate tree as JSON inside the text content.
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                decoded = None
            if decoded is not None:
                yield from _text_items(decoded)
    elif isinstance(value, dict):
        for key in ("text", "returnValue", "result"):
            if key in value:
                yield from _text_items(value[key])
        for key, item in value.items():
            if key not in {"text", "returnValue", "result"}:
                yield from _text_items(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _text_items(item)

def _dict_target(value: dict[str, Any], window: CCTarget | None) -> GroundedTarget | None:
    ref = value.get("ref") or value.get("reference")
    bounds = value.get("bounds") or value.get("rect")
    if not ref or not isinstance(bounds, dict):
        return None
    label = value.get("label") or value.get("text") or value.get("name") or value.get("title")
    if not isinstance(label, str) or not label.strip():
        return None
    try:
        x, y = int(bounds["x"]), int(bounds["y"])
        w, h = int(bounds["width"]), int(bounds["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        return None
    return GroundedTarget(
        label.strip(), GroundingSource.SLATE, 1.0, x, y, w, h, window,
        evidence=f"slate_ref={ref}",
    )

def _dict_targets(value: Any, window: CCTarget | None) -> Iterable[GroundedTarget]:
    if isinstance(value, dict):
        target = _dict_target(value, window)
        if target is not None:
            yield target
        for item in value.values():
            yield from _dict_targets(item, window)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _dict_targets(item, window)

def _line_target(line: str, window: CCTarget | None, *, origin_x: int = 0, origin_y: int = 0) -> GroundedTarget | None:
    ref_match = _REF.search(line)
    geometry = _POS_SIZE.search(line)
    if not ref_match or not geometry:
        return None
    label = _clean_label(line)
    if not label:
        return None
    g = geometry.groupdict()
    return GroundedTarget(
        label,
        GroundingSource.SLATE,
        1.0,
        int(g["x"]) - origin_x, int(g["y"]) - origin_y, int(g["w"]), int(g["h"]),
        window,
        evidence=f"slate_ref={ref_match.group('ref') or ref_match.group('ref2')}",
    )

class SlateGroundingAdapter:
    """Parse only structured Slate geometry into GroundedTarget values.

    The adapter never executes MCP actions. Targets remain subject to the normal
    grounding, scope, checkpoint and ComputerControlService gates.
    """

    def __init__(self, *, min_width: int = 1, min_height: int = 1):
        if min_width <= 0 or min_height <= 0:
            raise ValueError("minimum target dimensions must be positive")
        self.min_width = min_width
        self.min_height = min_height

    def targets_from_snapshot(
        self,
        result: Any,
        *,
        window: CCTarget | None = None,
    ) -> tuple[GroundedTarget, ...]:
        candidates: list[GroundedTarget] = []
        candidates.extend(_dict_targets(result, window))
        texts = tuple(_text_items(result))
        # Unreal Slate reports coordinates in virtual-desktop space. When the
        # editor is on a monitor left of the primary display, x can be negative.
        # Normalize that origin into the observation's non-negative coordinate
        # space while preserving relative geometry.
        if origin_x == 0:
            positions = [_POS_SIZE.search(line) for text in texts for line in text.splitlines()]
            negative_x = [int(match.group("x")) for match in positions if match and int(match.group("x")) < 0]
            if negative_x:
                origin_x = min(negative_x)
        for text in texts:
            for line in text.splitlines():
                target = _line_target(line, window, origin_x=origin_x, origin_y=origin_y)
                if target is not None:
                    candidates.append(target)
        unique: dict[tuple[str, int, int, int, int], GroundedTarget] = {}
        for target in candidates:
            target.validate()
            if target.width < self.min_width or target.height < self.min_height:
                continue
            key = (target.label.casefold(), target.x, target.y, target.width, target.height)
            unique[key] = target
        return tuple(unique.values())
