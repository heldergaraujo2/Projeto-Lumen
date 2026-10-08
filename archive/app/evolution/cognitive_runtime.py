"""Autonomous cognitive runtime.

Provides the missing execution layer between the OperationalBrain and a
provider/tool environment. It intentionally uses dependency-injected
interfaces so Ollama, MCP/Unreal, web research and tests can be connected
without making the cognitive architecture provider-specific.

This is a functional reproduction of an agent workflow: orient -> reason ->
act -> observe -> learn -> recover -> continue. It is not a copy of any
proprietary model or hidden implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from .operational_brain import ActionOutcome, BrainDecision, OperationalBrain


class CognitiveProvider(Protocol):
    def plan(self, context: Mapping[str, Any], actions: Sequence[str]) -> Mapping[str, Any]:
        """Return optional planner hints. The deterministic brain remains authoritative."""


class CognitiveToolExecutor(Protocol):
    def execute(self, action: str, *, context: Mapping[str, Any]) -> ActionOutcome:
        """Execute one governed action and return evidence."""


@dataclass(frozen=True)
class RuntimeCycle:
    cycle: int
    decision: BrainDecision
    outcome: ActionOutcome
    recovery_started: bool = False


@dataclass
class CognitiveRuntime:
    """Runs one persistent OperationalBrain as a closed cognitive loop."""

    brain: OperationalBrain
    provider: CognitiveProvider | None = None
    max_cycles: int = 1
    stop_on_blocked: bool = True
    history: list[RuntimeCycle] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.max_cycles < 1:
            raise ValueError("max_cycles must be >= 1")

    def step(
        self,
        available_actions: Sequence[str],
        *,
        observation: Mapping[str, Any] | None = None,
        executor: CognitiveToolExecutor,
    ) -> RuntimeCycle:
        context = dict(observation or {})
        context["brain_context"] = self.brain.reasoning_context()

        if self.provider is not None:
            hints = dict(self.provider.plan(context, tuple(available_actions)))
            # Provider suggestions enrich context; they never directly execute.
            context["provider_hints"] = hints

        decision = self.brain.decide(tuple(available_actions), context=context)
        outcome = self.brain.execute(
            decision,
            lambda action: executor.execute(action, context=self.brain.reasoning_context()),
        )

        recovery_started = False
        if not outcome.success:
            recovery_started = self.brain.recover(
                decision.action,
                reason=outcome.error or outcome.result,
            )

        cycle = RuntimeCycle(
            cycle=self.brain.state.cycle,
            decision=decision,
            outcome=outcome,
            recovery_started=recovery_started,
        )
        self.history.append(cycle)

        if self.stop_on_blocked and self.brain.state.phase == "BLOCKED":
            return cycle
        return cycle

    def run(
        self,
        available_actions: Sequence[str],
        *,
        executor: CognitiveToolExecutor,
        observation: Mapping[str, Any] | None = None,
    ) -> tuple[RuntimeCycle, ...]:
        cycles: list[RuntimeCycle] = []
        for _ in range(self.max_cycles):
            if self.brain.state.completed or (self.stop_on_blocked and self.brain.state.phase == "BLOCKED"):
                break
            cycle = self.step(available_actions, observation=observation, executor=executor)
            cycles.append(cycle)
            if cycle.decision.action == "done" or self.brain.state.completed:
                break
            if self.stop_on_blocked and self.brain.state.phase == "BLOCKED":
                break
        return tuple(cycles)
