from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from app.computer_control.api import CCTarget, ScreenRegion
from app.computer_control.grounding import GroundedTarget, GroundingSource

@dataclass(frozen=True)
class NativeWindow:
    handle:int
    title:str
    bounds:ScreenRegion|None=None
    process_id:int|None=None
    process_name:str|None=None
    visible:bool=True
    def target(self)->CCTarget:
        return CCTarget(window_title_pattern=self.title or None,window_handle=self.handle,process_name=self.process_name)

@dataclass(frozen=True)
class NativeElement:
    name:str
    control_type:str
    bounds:ScreenRegion|None
    automation_id:str|None=None
    class_name:str|None=None
    enabled:bool=True
    window:CCTarget|None=None
    native_reference:object|None=None
    def validate(self)->None:
        if not self.name.strip(): raise ValueError("native element name cannot be empty")
        if self.bounds is not None: self.bounds.validate()
    def grounded(self,*,confidence:float=1.0)->GroundedTarget:
        self.validate()
        if self.bounds is None: raise ValueError("native element has no bounds")
        return GroundedTarget(self.name,GroundingSource.UI_AUTOMATION,confidence,self.bounds.x,self.bounds.y,self.bounds.width,self.bounds.height,self.window,self.control_type)

@dataclass(frozen=True)
class NativeActionRequest:
    action:str
    element:NativeElement
    reason:str=""
    def validate(self)->None:
        if not self.action.strip(): raise ValueError("native action cannot be empty")
        self.element.validate()

class WindowsNativeBackend(Protocol):
    def list_windows(self)->tuple[NativeWindow,...]: ...
    def descendants(self,window:NativeWindow,*,max_depth:int=8,max_elements:int=256)->tuple[NativeElement,...]: ...

class WindowsNativeIntelligence:
    """Structured Windows perception and native-action planning; never executes OS actions."""
    def __init__(self,backend:WindowsNativeBackend|None=None):
        self._backend=backend or self._build_backend()
    @staticmethod
    def _build_backend()->WindowsNativeBackend:
        from app.computer.windows_uia import WindowsUIABackend
        return WindowsUIABackend()
    def list_windows(self)->tuple[NativeWindow,...]: return self._backend.list_windows()
    def find_window(self,target:CCTarget)->NativeWindow|None:
        import re
        for w in self.list_windows():
            if target.window_handle is not None and w.handle!=target.window_handle: continue
            if target.window_title_pattern and re.search(target.window_title_pattern,w.title) is None: continue
            if target.process_name and (w.process_name or "").casefold()!=target.process_name.casefold(): continue
            if target.app_name and target.app_name.casefold() not in w.title.casefold(): continue
            return w
        return None
    def inspect_window(self,window:NativeWindow,*,max_depth:int=8,max_elements:int=256)->tuple[NativeElement,...]:
        if max_depth<0: raise ValueError("max_depth must be >= 0")
        if not 1<=max_elements<=4096: raise ValueError("max_elements must be between 1 and 4096")
        return self._backend.descendants(window,max_depth=max_depth,max_elements=max_elements)
    def find_element(self,target:CCTarget,label:str,*,max_depth:int=8,max_elements:int=256)->NativeElement|None:
        if not label.strip(): raise ValueError("label cannot be empty")
        w=self.find_window(target)
        if w is None: return None
        wanted=label.casefold()
        return next((e for e in self.inspect_window(w,max_depth=max_depth,max_elements=max_elements) if e.name.casefold()==wanted),None)
    def plan_action(self,element:NativeElement,*,action:str="invoke",reason:str="")->NativeActionRequest:
        r=NativeActionRequest(action,element,reason);r.validate();return r

class FakeWindowsNativeBackend:
    def __init__(self,windows:tuple[NativeWindow,...],elements:dict[int,tuple[NativeElement,...]]):
        self.windows=windows;self.elements=elements;self.calls=[]
    def list_windows(self): self.calls.append(("list_windows",0));return self.windows
    def descendants(self,window,*,max_depth=8,max_elements=256):
        self.calls.append(("descendants",window.handle));return self.elements.get(window.handle,())[:max_elements]
