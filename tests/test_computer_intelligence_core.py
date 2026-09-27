from datetime import datetime,timedelta,timezone
import pytest
from app.computer_control.actions import CCActionRequest
from app.computer_control.api import CCActionType,CCTarget,ScreenRegion
from app.computer_control.grounding import GroundedTarget,GroundingEngine,GroundingSource,TargetResolver
from app.computer_control.recovery import RecoveryAction,RecoveryEngine
from app.computer_control.scopes import CCLimits,CCScope
def scope():
 n=datetime(2026,1,1,tzinfo=timezone.utc)
 return CCScope("s",n,n+timedelta(minutes=5),CCTarget(app_name="Lumen"),frozenset({CCActionType.MOUSE_CLICK}),CCLimits(3,2),allowed_region=ScreenRegion(10,10,100,100))
def test_rate_limit_is_enforced():
 s=scope();s.consume_action(now=s.created_at+timedelta(seconds=1));s.consume_action(now=s.created_at+timedelta(seconds=2))
 with pytest.raises(PermissionError):s.consume_action(now=s.created_at+timedelta(seconds=3))
 s.consume_action(now=s.created_at+timedelta(seconds=62))
def test_scope_region_is_fail_closed():
 s=scope();assert s.allows_point(20,20);assert not s.allows_point(0,0)
def test_grounding_requires_confidence_and_bounds():
 from app.computer_control.vision import VisionElement,VisionObservation
 obs=VisionObservation("test","model",200,200,(VisionElement("Compile",.95,20,20,30,20),))
 target=GroundingEngine(min_confidence=.9).from_vision(obs)[0]
 assert target.center()==(35,30)
 assert GroundingEngine(min_confidence=.9).validate_for_scope(target,scope_region=ScreenRegion(0,0,100,100),screenshot_width=200,screenshot_height=200)==(35,30)
 with pytest.raises(PermissionError):GroundingEngine(min_confidence=.9).validate_for_scope(target,scope_region=ScreenRegion(0,0,20,20),screenshot_width=200,screenshot_height=200)
def test_structured_first_resolution():
 candidates=[GroundedTarget("Compile",GroundingSource.VISION,.99,20,20,20,20),GroundedTarget("Compile",GroundingSource.UI_AUTOMATION,.80,30,30,20,20)]
 target,_,reason=TargetResolver().resolve(candidates,label="Compile")
 assert target and target.source is GroundingSource.UI_AUTOMATION and reason=="resolved_by_ui_automation"
def test_action_contract_rejects_missing_input():
 with pytest.raises(ValueError):CCActionRequest(CCActionType.MOUSE_CLICK).validate()
def test_recovery_is_bounded():
 r=RecoveryEngine(max_attempts=1);assert r.decide(failure_reason="target_not_found",attempt=0).action is RecoveryAction.REFIND_TARGET;assert r.decide(failure_reason="target_not_found",attempt=1).action is RecoveryAction.ABORT
