from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

class CCActionType(str, Enum):
    SCREENSHOT="screenshot"; MOUSE_MOVE="mouse_move"; MOUSE_CLICK="mouse_click"
    MOUSE_DOUBLE_CLICK="mouse_double_click"; MOUSE_RIGHT_CLICK="mouse_right_click"
    MOUSE_DRAG="mouse_drag"; SCROLL="scroll"; KEY_PRESS="key_press"; KEY_TYPE="key_type"
    KEY_COMBO="key_combo"; CLIPBOARD_READ="clipboard_read"; CLIPBOARD_WRITE="clipboard_write"
    WINDOW_FOCUS="window_focus"; WINDOW_MINIMIZE="window_minimize"
    WINDOW_MAXIMIZE="window_maximize"; WINDOW_CLOSE="window_close"

@dataclass(frozen=True)
class CCTarget:
    app_name: Optional[str]=None; process_name: Optional[str]=None
    window_title_pattern: Optional[str]=None; window_handle: Optional[int]=None

@dataclass(frozen=True)
class ScreenRegion:
    x:int; y:int; width:int; height:int
    def validate(self):
        if self.x<0 or self.y<0 or self.width<=0 or self.height<=0: raise ValueError("invalid screen region")
    def contains(self,x:int,y:int)->bool:
        self.validate(); return self.x<=x<self.x+self.width and self.y<=y<self.y+self.height
    def contains_box(self,x:int,y:int,w:int,h:int)->bool:
        self.validate(); return w>0 and h>0 and self.x<=x and self.y<=y and x+w<=self.x+self.width and y+h<=self.y+self.height

@dataclass(frozen=True)
class ScreenshotInfo:
    width:int; height:int; artifact_ref:Optional[str]=None; region:Optional[ScreenRegion]=None

@dataclass(frozen=True)
class WindowInfo:
    handle:int; title:str; process_id:int|None=None; process_name:str|None=None
    bounds:ScreenRegion|None=None; visible:bool=True

class ComputerControlDriver(Protocol):
    def screenshot(self,*,target:CCTarget|None=None,region:ScreenRegion|None=None)->ScreenshotInfo: ...
    def mouse_move(self,x:int,y:int)->None: ...
    def mouse_click(self,x:int,y:int,*,button:str="left")->None: ...
    def mouse_double_click(self,x:int,y:int,*,button:str="left")->None: ...
    def mouse_drag(self,x1:int,y1:int,x2:int,y2:int,*,button:str="left")->None: ...
    def scroll(self,delta:int)->None: ...
    def key_press(self,key:str)->None: ...
    def key_combo(self,keys:tuple[str,...])->None: ...
    def type_text(self,text:str)->None: ...
    def focus_window(self,target:CCTarget)->None: ...
