"""Evidence verifier for the autonomous voice mission.

The verifier deliberately does not infer real microphone/audio success from
source files or imports. A runtime validation harness must produce a JSON
evidence document with every acceptance criterion set to true.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.evolution.voice_mission import VoiceMissionSpec


class VoiceMissionVerifier:
    def __init__(self, path: str | Path, spec: VoiceMissionSpec | None = None) -> None:
        self.path = Path(path)
        self.spec = spec or VoiceMissionSpec()

    def load_evidence(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("voice validation evidence must be an object")
        return raw

    def verify(self) -> tuple[bool, tuple[str, ...], dict[str, Any]]:
        evidence = self.load_evidence()
        missing = self.spec.missing_criteria(evidence)
        return not missing, missing, evidence
