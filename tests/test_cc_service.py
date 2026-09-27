from datetime import datetime,timedelta,timezone
from app.computer_control.actions import CCActionRequest
from app.computer_control.api import CCActionType,CCTarget
from app.computer_control.fake_driver import FakeComputerControlDriver
from app.computer_control.scopes import CCLimits,CCScope
from app.computer_control.service import ComputerControlService
from app.security.permissions import PermissionLevel,PermissionManager
class FakeActionDriver(FakeComputerControlDriver):
 def __init__(self):super().__init__();self.calls=[]
 def mouse_move(self,x,y):self.calls.append(("move",x,y))
 def mouse_click(self,x,y,button="left"):self.calls.append(("click",x,y,button))
 def mouse_double_click(self,x,y,button="left"):self.calls.append(("double",x,y,button))
 def scroll(self,delta):self.calls.append(("scroll",delta))
 def key_press(self,key):self.calls.append(("press",key))
 def key_combo(self,keys):self.calls.append(("combo",keys))
 def type_text(self,text):self.calls.append(("type",text))
 def focus_window(self,target):self.calls.append(("focus",target.app_name))
def make_scope():
 n=datetime.now(timezone.utc);return CCScope("s",n,n+timedelta(minutes=1),CCTarget(app_name="Lumen"),frozenset({CCActionType.MOUSE_CLICK}),CCLimits(2,10))
def test_service_denies_without_permission():
 d=FakeActionDriver();r=ComputerControlService(permissions=PermissionManager(),driver=d).execute(scope=make_scope(),request=CCActionRequest(CCActionType.MOUSE_CLICK,x=10,y=10));assert not r.success and d.calls==[]
def test_service_executes_after_permission():
 d=FakeActionDriver();p=PermissionManager();p.grant(PermissionLevel.COMPUTER_CONTROL);r=ComputerControlService(permissions=p,driver=d).execute(scope=make_scope(),request=CCActionRequest(CCActionType.MOUSE_CLICK,x=10,y=10));assert r.success and d.calls==[("click",10,10,"left")]
