from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Iterable
from .api import CCTarget,ScreenRegion
from .vision import VisionObservation

class GroundingSource(str,Enum):
    UI_AUTOMATION="ui_automation"; ACCESSIBILITY="accessibility"; NATIVE="native"; DOM="dom"
    TEMPLATE="template"; OCR="ocr"; VISION="vision"

@dataclass(frozen=True)
class GroundedTarget:
    label:str; source:GroundingSource; confidence:float; x:int; y:int; width:int; height:int
    window:CCTarget|None=None; evidence:str|None=None
    def validate(self):
        if not self.label.strip() or not 0<=self.confidence<=1 or min(self.x,self.y)<0 or self.width<=0 or self.height<=0: raise ValueError("invalid grounded target")
    def center(self): self.validate(); return self.x+self.width//2,self.y+self.height//2

class GroundingEngine:
    def __init__(self,*,min_confidence=.80):
        if not 0<min_confidence<=1: raise ValueError("min_confidence must be in (0,1]")
        self.min_confidence=min_confidence
    def from_vision(self,observation:VisionObservation):
        observation.validate()
        return tuple(sorted((
            GroundedTarget(e.label,GroundingSource.VISION,e.confidence,e.x,e.y,e.width,e.height,evidence=e.text)
            for e in observation.elements if e.confidence>=self.min_confidence
        ),key=lambda x:(-x.confidence,x.label.casefold())))
    def validate_for_scope(self,target,*,scope_region,screenshot_width,screenshot_height):
        target.validate()
        if target.x+target.width>screenshot_width or target.y+target.height>screenshot_height: raise PermissionError("target outside screenshot")
        if scope_region and not scope_region.contains_box(target.x,target.y,target.width,target.height): raise PermissionError("target outside authorized region")
        if target.confidence<self.min_confidence: raise PermissionError("grounding confidence below threshold")
        return target.center()

class TargetResolver:
    ORDER=(GroundingSource.UI_AUTOMATION,GroundingSource.ACCESSIBILITY,GroundingSource.NATIVE,GroundingSource.DOM,GroundingSource.TEMPLATE,GroundingSource.OCR,GroundingSource.VISION)
    def resolve(self,candidates:Iterable[GroundedTarget],*,label):
        groups={s:[] for s in self.ORDER}
        for c in candidates:
            c.validate()
            if c.label.casefold()==label.casefold() and c.source in groups: groups[c.source].append(c)
        tried=[]
        for s in self.ORDER:
            tried.append(s)
            if groups[s]: return max(groups[s],key=lambda x:x.confidence),tuple(tried),f"resolved_by_{s.value}"
        return None,tuple(tried),"target_not_found"
