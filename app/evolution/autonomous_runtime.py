"""Generic mission runtime adapter for Lumen.

This module is repository-side infrastructure. It contains no machine-specific
Ollama, Unreal, MCP endpoint, filesystem, or desktop-control assumptions.
Those remain injected by the local PC environment.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .cognitive_runtime import CognitiveProvider, CognitiveRuntime, RuntimeCycle
from .operational_brain import ActionOutcome, OperationalBrain


class MissionEnvironment(Protocol):
    """Environment adapter implemented by the deployment/runtime."""

    def available_actions(self) -> Sequence[str]:
        """Return currently executable, governed actions."""

    def observe(self) -> Mapping[str, Any]:
        """Return the latest world/runtime observation."""

    def execute(self, action: str, *, context: Mapping[str, Any]) -> ActionOutcome:
        """Execute one action through the environment's existing policy gates."""


@dataclass
class AutonomousMissionRuntime:
    """Binds the persistent brain to an injected execution environment."""

    brain: OperationalBrain
    environment: MissionEnvironment
    provider: CognitiveProvider | None = None
    max_cycles: int = 1
    stop_on_blocked: bool = True

    def __post_init__(self) -> None:
        self.cognitive = CognitiveRuntime(
            self.brain,
            provider=self.provider,
            max_cycles=self.max_cycles,
            stop_on_blocked=self.stop_on_blocked,
        )

    def step(self) -> RuntimeCycle:
        actions = tuple(self.environment.available_actions())
        observation = dict(self.environment.observe())
        return self.cognitive.step(
            actions,
            observation=observation,
            executor=self.environment,
        )

    def run(self) -> tuple[RuntimeCycle, ...]:
        cycles = []
        for _ in range(self.max_cycles):
            if self.brain.state.completed:
                break
            if self.stop_on_blocked and self.brain.state.phase == "BLOCKED":
                break
            cycle = self.step()
            cycles.append(cycle)
            if cycle.decision.action == "done" or self.brain.state.completed:
                break
            if self.stop_on_blocked and self.brain.state.phase == "BLOCKED":
                break
        return tuple(cycles)
