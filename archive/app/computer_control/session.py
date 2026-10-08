from __future__ import annotations
from datetime import datetime,timedelta,timezone
from dataclasses import dataclass
from .api import CCActionType,CCTarget,ScreenRegion
from .scopes import CCLimits,CCScope
@dataclass(frozen=True)
class CCGrantRequest:
    target:CCTarget; actions:frozenset[CCActionType]; duration_seconds:int=300
    max_actions_total:int=100; max_actions_per_minute:int=30; max_session_seconds:int|None=None
    allowed_region:ScreenRegion|None=None
class CCSessionManager:
    """Session-only CC authority; never persisted and never implied by WRITE/TERMINAL."""
    def __init__(self):self._scopes={};self._counter=0
    def grant(self,request:CCGrantRequest,*,now:datetime|None=None):
        n=now or datetime.now(timezone.utc)
        if n.tzinfo is None or request.duration_seconds<=0:raise ValueError("invalid grant")
        self._counter+=1
        s=CCScope(f"cc-{self._counter:06d}",n,n+timedelta(seconds=request.duration_seconds),request.target,request.actions,CCLimits(request.max_actions_total,request.max_actions_per_minute,request.max_session_seconds),request.allowed_region)
        s.validate();self._scopes[s.scope_id]=s;return s
    def revoke(self,scope_id):self._scopes.pop(scope_id,None)
    def get(self,scope_id):return self._scopes.get(scope_id)
    def active(self,*,now=None):
        n=now or datetime.now(timezone.utc);return tuple(s for s in self._scopes.values() if not s.is_expired(now=n))
