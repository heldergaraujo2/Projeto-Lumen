from datetime import datetime,timezone,timedelta
from app.computer_control.api import CCActionType,CCTarget
from app.computer_control.session import CCGrantRequest,CCSessionManager
def test_cc_grant_is_session_only():
 n=datetime(2026,1,1,tzinfo=timezone.utc);m=CCSessionManager()
 s=m.grant(CCGrantRequest(CCTarget(app_name="UnrealEditor"),frozenset({CCActionType.SCREENSHOT})),now=n)
 assert s.scope_id=="cc-000001" and m.get(s.scope_id) is s
 m.revoke(s.scope_id);assert m.get(s.scope_id) is None
def test_expired_scope_is_not_active():
 n=datetime(2026,1,1,tzinfo=timezone.utc);m=CCSessionManager()
 s=m.grant(CCGrantRequest(CCTarget(app_name="x"),frozenset({CCActionType.SCREENSHOT}),duration_seconds=1),now=n)
 assert s in m.active(now=n);assert s not in m.active(now=n+timedelta(seconds=2))
