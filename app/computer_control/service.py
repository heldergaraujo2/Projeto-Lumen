from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from time import monotonic
from app.security.permissions import PermissionLevel,PermissionManager
from .actions import CCActionRequest,action_point
from .api import CCActionType,ComputerControlDriver
from .audit import CCAuditEvent,make_cc_audit_event
from .policy import CCDecision,evaluate_cc_action
from .scopes import CCScope

@dataclass(frozen=True)
class CCExecutionResult:
    success:bool; decision:CCDecision; audit:CCAuditEvent; error:str|None=None

class ComputerControlService:
    def __init__(self,*,permissions:PermissionManager,driver:ComputerControlDriver):
        self.permissions=permissions; self.driver=driver
    def execute(self,*,scope:CCScope,request:CCActionRequest):
        request.validate(); now=datetime.now(timezone.utc)
        decision=evaluate_cc_action(has_computer_control_permission=self.permissions.is_granted(PermissionLevel.COMPUTER_CONTROL),scope=scope,action=request.action,now=now)
        start=monotonic()
        if not decision.allowed:
            ev=make_cc_audit_event(operation="computer_control",scope_id=scope.scope_id,action_type=request.action,decision="denied",denied_reason=decision.reason,duration_ms=int((monotonic()-start)*1000))
            return CCExecutionResult(False,decision,ev,decision.reason)
        try:
            self._execute_driver(scope,request); scope.consume_action(now=now)
            ev=make_cc_audit_event(operation="computer_control",scope_id=scope.scope_id,action_type=request.action,decision="allowed",duration_ms=int((monotonic()-start)*1000))
            return CCExecutionResult(True,decision,ev)
        except Exception as exc:
            ev=make_cc_audit_event(operation="computer_control",scope_id=scope.scope_id,action_type=request.action,decision="allowed",denied_reason="execution_failed",duration_ms=int((monotonic()-start)*1000))
            return CCExecutionResult(False,decision,ev,str(exc))
    def _execute_driver(self,scope,request):
        if request.action==CCActionType.SCREENSHOT:self.driver.screenshot(target=scope.target,region=request.region or scope.allowed_region);return
        if request.action==CCActionType.WINDOW_FOCUS:self.driver.focus_window(scope.target);return
        if request.action in {CCActionType.MOUSE_MOVE,CCActionType.MOUSE_CLICK,CCActionType.MOUSE_DOUBLE_CLICK,CCActionType.MOUSE_RIGHT_CLICK}:
            x,y=action_point(request)
            if not scope.allows_point(x,y):raise PermissionError("point outside authorized region")
            if request.action==CCActionType.MOUSE_MOVE:self.driver.mouse_move(x,y)
            elif request.action==CCActionType.MOUSE_CLICK:self.driver.mouse_click(x,y)
            elif request.action==CCActionType.MOUSE_DOUBLE_CLICK:self.driver.mouse_double_click(x,y)
            else:self.driver.mouse_click(x,y,button="right")
            return
        if request.action==CCActionType.SCROLL:self.driver.scroll(request.delta or 0);return
        if request.action==CCActionType.KEY_PRESS:self.driver.key_press(request.keys[0]);return
        if request.action==CCActionType.KEY_COMBO:self.driver.key_combo(request.keys);return
        if request.action==CCActionType.KEY_TYPE:self.driver.type_text(request.text or "");return
        raise NotImplementedError(request.action.value)
