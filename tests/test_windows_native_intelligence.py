from app.computer.windows_native import FakeWindowsNativeBackend,NativeElement,NativeWindow,WindowsNativeIntelligence
from app.computer_control.api import CCTarget,ScreenRegion
from app.computer_control.grounding import GroundingSource

def fixture():
    w=NativeWindow(101,"Unreal Editor",ScreenRegion(0,0,1280,720),42,"UnrealEditor.exe")
    b=NativeElement("Compile","button",ScreenRegion(900,40,100,32),"CompileButton","Button",True,w.target())
    p=NativeElement("Play","button",ScreenRegion(800,40,80,32),window=w.target())
    return w,b,FakeWindowsNativeBackend((w,),{101:(b,p)})

def test_bounded_backend():
    w,_,backend=fixture();i=WindowsNativeIntelligence(backend)
    assert i.list_windows()==(w,)
    assert len(i.inspect_window(w,max_depth=2,max_elements=1))==1
    assert backend.calls==[("list_windows",0),("descendants",101)]

def test_window_matching():
    w,_,backend=fixture();i=WindowsNativeIntelligence(backend)
    assert i.find_window(CCTarget(window_handle=101,window_title_pattern="Unreal",process_name="UnrealEditor.exe"))==w
    assert i.find_window(CCTarget(window_handle=999)) is None

def test_structured_element_lookup():
    w,b,backend=fixture();assert WindowsNativeIntelligence(backend).find_element(w.target(),"Compile")==b

def test_native_element_grounding():
    _,b,_=fixture();t=b.grounded();assert t.source is GroundingSource.UI_AUTOMATION and t.center()==(950,56)

def test_action_is_request_only():
    _,b,backend=fixture();r=WindowsNativeIntelligence(backend).plan_action(b,reason="compile")
    assert r.action=="invoke" and r.element is b and backend.calls==[]

def test_limits_and_invalid_label():
    w,_,backend=fixture();i=WindowsNativeIntelligence(backend)
    try:i.find_element(w.target()," ")
    except ValueError:pass
    else:raise AssertionError("expected ValueError")
    try:i.inspect_window(w,max_elements=0)
    except ValueError:pass
    else:raise AssertionError("expected ValueError")

def test_invalid_element():
    try:NativeElement("","button",None).validate()
    except ValueError:pass
    else:raise AssertionError("expected ValueError")

def test_windows_backend_is_lazy_on_non_windows():
    import os
    if os.name!="nt":
        try:__import__("app.computer.windows_uia",fromlist=["WindowsUIABackend"]).WindowsUIABackend()
        except OSError:pass
        else:raise AssertionError("expected Windows-only backend")


def test_windows_uia_initializer_uses_registered_clsid(monkeypatch):
    import sys
    import types

    calls = {}

    class FakeCUIAutomation:
        pass

    class FakeIUIAutomation:
        pass

    class FakeClient:
        def GetModule(self, name):
            calls["module"] = name
            return object()
        def CreateObject(self, cls, *, interface, clsctx):
            calls["cls"] = cls
            calls["interface"] = interface
            calls["clsctx"] = clsctx
            return object()

    fake_comtypes = types.ModuleType("comtypes")
    fake_comtypes.CLSCTX_INPROC_SERVER = 1
    fake_comtypes.COMError = type("COMError", (Exception,), {})
    fake_client = FakeClient()
    fake_comtypes.client = fake_client

    fake_gen = types.ModuleType("comtypes.gen")
    fake_uia_client = types.SimpleNamespace(
        CUIAutomation=FakeCUIAutomation,
        IUIAutomation=FakeIUIAutomation,
    )
    fake_gen.UIAutomationClient = fake_uia_client

    monkeypatch.setitem(sys.modules, "comtypes", fake_comtypes)
    monkeypatch.setitem(sys.modules, "comtypes.client", fake_client)
    monkeypatch.setitem(sys.modules, "comtypes.gen", fake_gen)

    class FakeOS:
        name = "nt"

    monkeypatch.setattr("os.name", "nt")

    from app.computer_control.windows.uia import WindowsUIAutomation

    adapter = WindowsUIAutomation()
    assert adapter._uia is not None
    assert calls["module"] == "UIAutomationCore.dll"
    assert calls["cls"] is FakeCUIAutomation
    assert calls["interface"] is FakeIUIAutomation
    assert calls["clsctx"] == 1


def test_windows_process_info_extracts_pid_and_executable_name(monkeypatch):
    import ctypes
    from app.computer_control.windows.driver import WindowsComputerControlDriver

    class FakeUser32:
        def GetWindowThreadProcessId(self, hwnd, pid_ptr):
            assert hwnd.value == 999
            pid_ptr._obj.value = 6764
            return 1

    class FakeKernel32:
        def OpenProcess(self, access, inherit_handle, pid):
            assert access == 0x1000
            assert pid == 6764
            return 123
        def QueryFullProcessImageNameW(self, handle, flags, buffer, size_ptr):
            assert handle == 123
            buffer.value = r"C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
            size_ptr._obj.value = len(buffer.value)
            return 1
        def CloseHandle(self, handle):
            assert handle == 123
            return 1

    class FakeWindll:
        user32 = FakeUser32()
        kernel32 = FakeKernel32()

    monkeypatch.setattr(ctypes, "windll", FakeWindll(), raising=False)
    driver = object.__new__(WindowsComputerControlDriver)
    assert driver._process_info(999) == (6764, "UnrealEditor.exe")


def test_windows_uia_walk_skips_null_com_element(monkeypatch):
    import types
    from app.computer.windows_uia import WindowsUIABackend

    class FakeElement:
        pass

    valid = FakeElement()
    invalid = FakeElement()
    child = FakeElement()

    class FakeAdapter:
        def element_info(self, element):
            if element is invalid:
                raise ValueError("NULL COM pointer access")
            from app.computer_control.windows.uia import UIElementInfo
            return UIElementInfo("Play", "button", ScreenRegion(10, 20, 80, 30))

    class FakeWalker:
        def GetFirstChildElement(self, element):
            return None
        def GetNextSiblingElement(self, element):
            return None

    fake_uia = types.SimpleNamespace(ControlViewWalker=FakeWalker())
    backend = object.__new__(WindowsUIABackend)
    backend._adapter = FakeAdapter()
    backend._adapter._uia = fake_uia
    window = NativeWindow(1, "Unreal Editor", ScreenRegion(0, 0, 1280, 720), 42, "UnrealEditor.exe")

    elements = backend._walk(invalid, window, max_depth=1, max_elements=8)
    assert elements == ()
    elements = backend._walk(valid, window, max_depth=1, max_elements=8)
    assert len(elements) == 1
    assert elements[0].name == "Play"
