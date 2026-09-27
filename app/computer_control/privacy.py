from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .api import ScreenRegion

@dataclass(frozen=True)
class ScreenshotPolicy:
    allow_external_provider:bool=False; allow_persistence:bool=False; max_bytes:int=10_000_000
    allowed_region:ScreenRegion|None=None
    def validate(self):
        if self.max_bytes<=0: raise ValueError("max_bytes must be > 0")
        if self.allowed_region:self.allowed_region.validate()

def validate_artifact_for_vision(path:Path,policy:ScreenshotPolicy):
    policy.validate()
    if not path.is_file():raise FileNotFoundError(path)
    if path.stat().st_size>policy.max_bytes:raise PermissionError("screenshot exceeds privacy policy size limit")

def assert_provider_allowed(policy:ScreenshotPolicy,*,provider_is_external:bool):
    if provider_is_external and not policy.allow_external_provider:raise PermissionError("external vision provider disabled")
