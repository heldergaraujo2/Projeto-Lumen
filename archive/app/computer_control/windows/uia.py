from __future__ import annotations
from dataclasses import dataclass
from ..api import ScreenRegion
@dataclass(frozen=True)
class UIElementInfo:
    name:str;control_type:str;bounds:ScreenRegion|None=None;automation_id:str|None=None;enabled:bool=True;class_name:str|None=None
class WindowsUIAutomation:
    def __init__(self):
        import os
        if os.name!="nt":raise OSError("WindowsUIAutomation requires Windows")
        try:import comtypes.client
        except ImportError as e:raise RuntimeError("comtypes is required for UI Automation") from e
        self._uia=comtypes.client.CreateObject("UIAutomationClient.CUIAutomation")
    def root(self):return self._uia.GetRootElement()
    def element_info(self,element):
        r=element.CurrentBoundingRectangle
        return UIElementInfo(str(element.CurrentName or ""),str(element.CurrentLocalizedControlType or ""),ScreenRegion(r.left,r.top,r.right-r.left,r.bottom-r.top),str(element.CurrentAutomationId or "") or None,bool(element.CurrentIsEnabled),str(element.CurrentClassName or "") or None)
