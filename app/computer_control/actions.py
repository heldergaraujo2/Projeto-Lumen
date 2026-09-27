from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .api import CCActionType,ScreenRegion
from .grounding import GroundedTarget

@dataclass(frozen=True)
class CCActionRequest:
    action:CCActionType; x:int|None=None; y:int|None=None; target:GroundedTarget|None=None
    text:str|None=None; keys:tuple[str,...]=(); delta:int|None=None; region:ScreenRegion|None=None
    metadata:dict[str,Any]|None=None
    def validate(self):
        mouse={CCActionType.MOUSE_MOVE,CCActionType.MOUSE_CLICK,CCActionType.MOUSE_DOUBLE_CLICK,CCActionType.MOUSE_RIGHT_CLICK}
        if self.action in mouse and self.x is None and self.target is None: raise ValueError("mouse action requires coordinates or target")
        if self.action in {CCActionType.KEY_TYPE,CCActionType.CLIPBOARD_WRITE} and self.text is None: raise ValueError("text required")
        if self.action in {CCActionType.KEY_PRESS,CCActionType.KEY_COMBO} and not self.keys: raise ValueError("keys required")
        if self.action==CCActionType.SCROLL and self.delta is None: raise ValueError("scroll delta required")
        if self.region: self.region.validate()
        if self.target: self.target.validate()

def action_point(request):
    request.validate()
    if request.x is not None and request.y is not None:return request.x,request.y
    if request.target:return request.target.center()
    raise ValueError("no action point")
