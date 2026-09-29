from __future__ import annotations
from app.computer.windows_native import NativeElement, NativeWindow

class WindowsUIABackend:
    """Bounded UI Automation backend; COM is loaded only on Windows."""
    def __init__(self):
        import os
        if os.name!="nt": raise OSError("WindowsUIABackend requires Windows")
        try:
            from app.computer_control.windows.uia import WindowsUIAutomation
        except ImportError as exc:
            raise RuntimeError("Windows UI Automation adapter is unavailable") from exc
        self._adapter=WindowsUIAutomation()
    def list_windows(self):
        from app.computer_control.windows.driver import WindowsComputerControlDriver
        import tempfile
        d=WindowsComputerControlDriver(artifact_dir=tempfile.gettempdir())
        return tuple(NativeWindow(w.handle,w.title,w.bounds,w.process_id,w.process_name,w.visible) for w in d.list_windows())
    def descendants(self,window,*,max_depth=8,max_elements=256):
        root=self._adapter.root()
        native_root=None
        try:
            from comtypes.gen import UIAutomationClient
            condition=self._adapter._uia.CreatePropertyCondition(UIAutomationClient.UIA_NativeWindowHandlePropertyId,int(window.handle))
            native_root=root.FindFirst(UIAutomationClient.TreeScope_Descendants,condition)
        except Exception:
            native_root=None
        if not native_root: return ()
        return self._walk(native_root,window,max_depth=max_depth,max_elements=max_elements)
    def _walk(self,root,window,*,max_depth,max_elements):
        from collections import deque
        out=[];queue=deque([(root,0)]);walker=self._adapter._uia.ControlViewWalker
        while queue and len(out)<max_elements:
            element,depth=queue.popleft()
            if not element:
                continue
            try:
                info=self._adapter.element_info(element)
            except ValueError:
                continue
            out.append(NativeElement(info.name,info.control_type,info.bounds,info.automation_id,info.class_name,info.enabled,window.target(),element))
            if depth>=max_depth: continue
            try:
                child=walker.GetFirstChildElement(element)
            except Exception:
                child=None
            while child and len(out)+len(queue)<max_elements:
                queue.append((child,depth+1))
                try:
                    child=walker.GetNextSiblingElement(child)
                except Exception:
                    child=None
        return tuple(out)
