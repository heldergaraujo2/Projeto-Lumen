"""Lumen Modular Self-Expanding Brain.

Composes Lumen's native cognitive/evolution stack with optional open agent
backends without surrendering authority, security, checkpoints or rollback.
External frameworks are capability providers, not authorities.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import importlib.util
from typing import Any, Mapping, Protocol, Sequence
from .autonomous_runtime import MissionEnvironment
from .cognitive_runtime import CognitiveProvider, RuntimeCycle
from .operational_brain import OperationalBrain

@dataclass(frozen=True)
class BackendSpec:
    name: str
    role: str
    packages: tuple[str, ...]
    strengths: tuple[str, ...]
    optional: bool = True

@dataclass(frozen=True)
class BackendStatus:
    name: str
    available: bool
    packages: tuple[str, ...]
    reason: str = ""

BACKENDS: tuple[BackendSpec, ...] = (
    BackendSpec("openai_agents", "agent_orchestration", ("agents",),
                ("tools", "handoffs", "guardrails", "sessions", "mcp", "voice")),
    BackendSpec("openhands", "software_engineering", ("openhands",),
                ("workspace", "coding", "execution", "skills", "memory", "mcp")),
    BackendSpec("browser_use", "browser_automation", ("browser_use",),
                ("web", "browser", "computer_use")),
    BackendSpec("autogen", "multi_agent", ("autogen_agentchat", "autogen_core"),
                ("handoffs", "multi_agent", "memory", "mcp")),
    BackendSpec("langgraph", "durable_orchestration", ("langgraph",),
                ("state", "persistence", "recovery", "human_in_loop")),
)

class BrainBackend(Protocol):
    spec: BackendSpec
    def available(self) -> bool: ...
    def enrich(self, context: Mapping[str, Any], actions: Sequence[str]) -> Mapping[str, Any]: ...

class OptionalBackend:
    def __init__(self, spec: BackendSpec) -> None:
        self.spec = spec
    def available(self) -> bool:
        return any(importlib.util.find_spec(pkg) is not None for pkg in self.spec.packages)
    def enrich(self, context: Mapping[str, Any], actions: Sequence[str]) -> Mapping[str, Any]:
        if not self.available():
            return {"available": False, "backend": self.spec.name}
        return {"available": True, "backend": self.spec.name, "role": self.spec.role,
                "strengths": self.spec.strengths, "actions_seen": tuple(actions)}

class ModularBrainProvider:
    """Aggregates optional specialist capabilities into provider hints.

    It deliberately does not execute tools. OperationalBrain remains the
    decision authority and MissionEnvironment remains the execution authority.
    """
    def __init__(self, backends: Sequence[BrainBackend] | None = None) -> None:
        self.backends = tuple(backends or (OptionalBackend(spec) for spec in BACKENDS))
    def plan(self, context: Mapping[str, Any], actions: Sequence[str]) -> Mapping[str, Any]:
        hints: dict[str, Any] = {}
        for backend in self.backends:
            try:
                hints[backend.spec.name] = dict(backend.enrich(context, actions))
            except Exception as exc:
                hints[backend.spec.name] = {"available": False, "backend": backend.spec.name,
                                            "reason": f"{type(exc).__name__}: {exc}"}
        hints["routing"] = self._route(context, actions, hints)
        return hints
    @staticmethod
    def _route(context: Mapping[str, Any], actions: Sequence[str],
               hints: Mapping[str, Any]) -> Mapping[str, Any]:
        objective = str(context.get("objective", "")).lower()
        candidates: list[str] = []
        if any(x in objective for x in ("site", "browser", "web", "internet")):
            candidates.append("browser_use")
        if any(x in objective for x in ("code", "program", "software", "implement")):
            candidates.extend(("openhands", "openai_agents"))
        if any(x in objective for x in ("multiple", "specialist", "parallel")):
            candidates.append("autogen")
        if any(x in objective for x in ("long", "resume", "checkpoint", "persistent")):
            candidates.append("langgraph")
        candidates.append("openai_agents")
        available = tuple(name for name in candidates if bool(hints.get(name, {}).get("available")))
        return {"preferred_backends": available, "governed_actions": tuple(actions)}

@dataclass
class ModularCognitiveBrain:
    brain: OperationalBrain
    provider: CognitiveProvider | None = None
    specialist_provider: ModularBrainProvider = field(default_factory=ModularBrainProvider)
    max_cycles: int = 1
    def __post_init__(self) -> None:
        from .cognitive_runtime import CognitiveRuntime
        self.runtime = CognitiveRuntime(self.brain, provider=self.provider or self.specialist_provider,
                                        max_cycles=self.max_cycles)
    def step(self, environment: MissionEnvironment) -> RuntimeCycle:
        return self.runtime.step(tuple(environment.available_actions()),
                                 observation=dict(environment.observe()), executor=environment)
    def run(self, environment: MissionEnvironment) -> tuple[RuntimeCycle, ...]:
        return self.runtime.run(tuple(environment.available_actions()),
                                observation=dict(environment.observe()), executor=environment)
    def backend_status(self) -> tuple[BackendStatus, ...]:
        statuses = []
        for backend in self.specialist_provider.backends:
            try:
                ok = bool(backend.available())
                statuses.append(BackendStatus(backend.spec.name, ok, backend.spec.packages,
                                              "" if ok else "optional backend not installed"))
            except Exception as exc:
                statuses.append(BackendStatus(backend.spec.name, False, backend.spec.packages,
                                              f"{type(exc).__name__}: {exc}"))
        return tuple(statuses)
    def architecture_snapshot(self) -> dict[str, Any]:
        return {"brain": self.brain.snapshot(),
                "backends": [asdict(x) for x in self.backend_status()],
                "principle": "external frameworks advise; Lumen governance decides and executes"}
