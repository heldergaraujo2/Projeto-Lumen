from __future__ import annotations
from dataclasses import dataclass,field
from datetime import datetime,timedelta,timezone
from typing import FrozenSet,Optional
from .api import CCActionType,CCTarget,ScreenRegion

def _now_utc(): return datetime.now(timezone.utc)

@dataclass(frozen=True)
class CCLimits:
    max_actions_total:int; max_actions_per_minute:int; max_session_seconds:Optional[int]=None
    def validate(self):
        if self.max_actions_total<=0 or self.max_actions_per_minute<=0: raise ValueError("action limits must be > 0")
        if self.max_session_seconds is not None and self.max_session_seconds<=0: raise ValueError("max_session_seconds must be > 0")

@dataclass
class CCScope:
    scope_id:str; created_at:datetime; expires_at:datetime; target:CCTarget
    allowed_actions:FrozenSet[CCActionType]; limits:CCLimits
    allowed_region:Optional[ScreenRegion]=None; actions_used:int=0
    first_action_at:Optional[datetime]=None; last_action_at:Optional[datetime]=None
    _action_times:list[datetime]=field(default_factory=list,repr=False)
    def validate(self):
        if not self.scope_id.strip(): raise ValueError("scope_id must be non-empty")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None: raise ValueError("scope timestamps must be timezone-aware")
        if self.expires_at<=self.created_at: raise ValueError("expires_at must be after created_at")
        if not self.allowed_actions: raise ValueError("allowed_actions must be non-empty")
        self.limits.validate()
        if self.allowed_region: self.allowed_region.validate()
    def is_expired(self,*,now=None): return (now or _now_utc())>=self.expires_at
    def remaining_actions(self): return max(0,self.limits.max_actions_total-self.actions_used)
    def _prune(self,now):
        cutoff=now-timedelta(seconds=60); self._action_times[:]=[t for t in self._action_times if t>cutoff]
    def can_consume_action(self,*,now=None):
        n=now or _now_utc()
        if self.is_expired(now=n) or self.actions_used>=self.limits.max_actions_total: return False
        if self.limits.max_session_seconds is not None and n>=self.created_at+timedelta(seconds=self.limits.max_session_seconds): return False
        self._prune(n); return len(self._action_times)<self.limits.max_actions_per_minute
    def consume_action(self,*,now=None):
        n=now or _now_utc()
        if not self.can_consume_action(now=n): raise PermissionError("scope action budget exceeded or expired")
        self.actions_used+=1; self._action_times.append(n)
        if self.first_action_at is None: self.first_action_at=n
        self.last_action_at=n
    def allows_point(self,x,y): return self.allowed_region is None or self.allowed_region.contains(x,y)
