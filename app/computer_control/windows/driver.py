from __future__ import annotations
import os,uuid
from pathlib import Path
from ..api import CCTarget,ScreenRegion,ScreenshotInfo,WindowInfo
class WindowsComputerControlDriver:
    def __init__(self,*,artifact_dir):
        if os.name!="nt":raise OSError("WindowsComputerControlDriver requires Windows")
        self.artifact_dir=Path(artifact_dir).resolve();self.artifact_dir.mkdir(parents=True,exist_ok=True)
    def _u(self):
        import ctypes;return ctypes.windll.user32
    def screenshot(self,*,target=None,region=None):
        try:from PIL import ImageGrab
        except ImportError as e:raise RuntimeError("Pillow required for screenshots") from e
        im=ImageGrab.grab(all_screens=True)
        if region:region.validate();im=im.crop((region.x,region.y,region.x+region.width,region.y+region.height))
        p=self.artifact_dir/f"screen_{uuid.uuid4().hex}.png";im.save(p,"PNG");return ScreenshotInfo(im.width,im.height,str(p),region)
    def mouse_move(self,x,y):self._point(x,y);self._u().SetCursorPos(x,y)
    def mouse_click(self,x,y,*,button="left"):
        self.mouse_move(x,y);flags={"left":(2,4),"right":(8,16),"middle":(32,64)}
        if button not in flags:raise ValueError("unsupported mouse button")
        d,u=flags[button];self._u().mouse_event(d,0,0,0,0);self._u().mouse_event(u,0,0,0,0)
    def mouse_double_click(self,x,y,*,button="left"):self.mouse_click(x,y,button=button);self.mouse_click(x,y,button=button)
    def mouse_drag(self,x1,y1,x2,y2,*,button="left"):
        self.mouse_move(x1,y1);flags={"left":(2,4),"right":(8,16)}
        if button not in flags:raise ValueError("unsupported drag button")
        self._u().mouse_event(flags[button][0],0,0,0,0);self.mouse_move(x2,y2);self._u().mouse_event(flags[button][1],0,0,0,0)
    def scroll(self,delta):self._u().mouse_event(0x0800,0,0,int(delta),0)
    def key_press(self,key):self._keybd(self._vk(key))
    def key_combo(self,keys):
        v=[self._vk(k) for k in keys]
        for k in v:self._u().keybd_event(k,0,0,0)
        for k in reversed(v):self._u().keybd_event(k,0,2,0)
    def _keybd(self,vk):self._u().keybd_event(vk,0,0,0);self._u().keybd_event(vk,0,2,0)
    def type_text(self,text):
        for ch in text:
            code=ord(ch);self._u().keybd_event(0,code,4,0);self._u().keybd_event(0,code,6,0)
    def focus_window(self,target):
        hwnd=self._find_window(target)
        if not hwnd:raise RuntimeError("target window not found")
        self._u().SetForegroundWindow(hwnd)
    def list_windows(self):
        import ctypes
        u=self._u();out=[];CB=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
        def cb(hwnd,_):
            if not u.IsWindowVisible(hwnd):return True
            n=u.GetWindowTextLengthW(hwnd);b=ctypes.create_unicode_buffer(n+1);u.GetWindowTextW(hwnd,b,n+1)
            if b.value:out.append(WindowInfo(int(hwnd),b.value))
            return True
        u.EnumWindows(CB(cb),0);return tuple(out)
    def _find_window(self,target):
        if target.window_handle and self._u().IsWindow(target.window_handle):return target.window_handle
        import re
        for w in self.list_windows():
            if target.window_title_pattern and re.search(target.window_title_pattern,w.title) is None:continue
            return w.handle
        return None
    def _point(self,x,y):
        if not (0<=x<self._u().GetSystemMetrics(0) and 0<=y<self._u().GetSystemMetrics(1)):raise ValueError("coordinate outside primary display")
    @staticmethod
    def _vk(key):
        names={"ENTER":13,"ESC":27,"TAB":9,"SPACE":32,"BACKSPACE":8,"CTRL":17,"ALT":18,"SHIFT":16,"WIN":91,"LEFT":37,"UP":38,"RIGHT":39,"DOWN":40}
        k=key.upper()
        if k in names:return names[k]
        if len(k)==1:return ord(k)
        if k.startswith("F") and k[1:].isdigit() and 1<=int(k[1:])<=24:return 0x70+int(k[1:])-1
        raise ValueError(f"unsupported key: {key}")
