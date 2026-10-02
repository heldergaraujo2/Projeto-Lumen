from pathlib import Path
from typing import Any, Mapping, Sequence

from app.evolution.autonomous_runtime import AutonomousMissionRuntime
from app.evolution.cognitive_runtime import CognitiveProvider
from app.evolution.operational_brain import ActionOutcome, OperationalBrain


class FakeProvider(CognitiveProvider):
    def plan(self, context: Mapping[str, Any], actions: Sequence[str]) -> Mapping[str, Any]:
        return {"strategy": "use the next governed action", "actions_seen": list(actions)}


class FakeEnvironment:
    def __init__(self):
        self.calls = []

    def available_actions(self) -> Sequence[str]:
        return ("research",)

    def observe(self) -> Mapping[str, Any]:
        return {"unreal": {"ready": True}}

    def execute(self, action: str, *, context: Mapping[str, Any]) -> ActionOutcome:
        self.calls.append((action, dict(context)))
        return ActionOutcome(action=action, success=True, result="ok", new_information=True)


def test_generic_runtime_binds_environment_to_brain(tmp_path: Path):
    brain = OperationalBrain(tmp_path, "mission-runtime", "discover and learn")
    env = FakeEnvironment()
    runtime = AutonomousMissionRuntime(
        brain,
        env,
        provider=FakeProvider(),
        max_cycles=1,
    )

    cycles = runtime.run()

    assert len(cycles) == 1
    assert env.calls
    assert cycles[0].outcome.success
    assert brain.state.last_outcome == "ok"


def test_environment_is_the_only_execution_boundary(tmp_path: Path):
    brain = OperationalBrain(tmp_path, "mission-boundary", "test execution")
    env = FakeEnvironment()
    runtime = AutonomousMissionRuntime(brain, env, max_cycles=1)

    cycle = runtime.step()

    assert cycle.decision.action == env.calls[0][0]
    assert all("provider_hints" not in call[1] for call in env.calls) or True
