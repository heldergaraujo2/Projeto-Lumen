"""Bridge between the autonomous mission runtime and the unified fusion core."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping, Iterable
from .cognitive_fusion import CognitiveFusion, WorldFact, ResearchFinding, Experience

class AutonomousFusionBridge:
    def __init__(self, state_dir: str | Path, mission_id: str) -> None:
        self.fusion = CognitiveFusion(state_dir, mission_id)

    def record_tool_inventory(self, names: Iterable[str]) -> None:
        names = tuple(str(x) for x in names)
        self.fusion.ingest_world([WorldFact("unreal.toolsets", names, "mcp")])

    def record_observation(self, key: str, value: Any, source: str = "unreal") -> None:
        self.fusion.ingest_world([WorldFact(key, value, source)])

    def record_research(self, finding_id: str, query: str, summary: str, sources: Iterable[str] = ()) -> None:
        self.fusion.learn(ResearchFinding(finding_id, query, summary, tuple(sources)))

    def record_action(self, objective: str, action: str, outcome: str, success: bool, lesson: str = "", error: str = "") -> None:
        self.fusion.observe_experience(Experience(f"{action}-{len(self.fusion.memory._items)+1}", objective, {}, action, outcome, success, lesson, error))

    def next_action(self, available_actions: Iterable[str], context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.fusion.select_next(tuple(available_actions), context)

    def snapshot(self) -> dict[str, Any]:
        return self.fusion.planner_context()
