from app.evolution.cognitive_runtime import CognitiveRuntime
from app.evolution.operational_brain import ActionOutcome, OperationalBrain


class FakeExecutor:
    def __init__(self):
        self.actions = []

    def execute(self, action, *, context):
        self.actions.append(action)
        return ActionOutcome(action=action, success=True, result=f"ok:{action}", new_information=True)


class HintProvider:
    def plan(self, context, actions):
        return {"strategy": "use evidence before repeating", "available": list(actions)}


def test_runtime_closes_decide_execute_learn_loop(tmp_path):
    brain = OperationalBrain(tmp_path, "rt1", "improve Unreal autonomy")
    executor = FakeExecutor()
    runtime = CognitiveRuntime(brain, provider=HintProvider(), max_cycles=2)

    cycles = runtime.run(("research", "observe_unreal"), executor=executor)

    assert cycles
    assert executor.actions == [c.decision.action for c in cycles]
    assert brain.state.cycle == len(cycles)
    assert brain.fusion.memory.recall(objective="improve Unreal autonomy")


def test_runtime_recovers_failed_action(tmp_path):
    brain = OperationalBrain(tmp_path, "rt2", "recover")
    calls = {"n": 0}

    class FailingExecutor:
        def execute(self, action, *, context):
            calls["n"] += 1
            return ActionOutcome(action=action, success=False, error="tool failed")

    runtime = CognitiveRuntime(brain, max_cycles=1)
    cycle = runtime.step(("research",), executor=FailingExecutor())

    assert not cycle.outcome.success
    assert cycle.recovery_started
    assert brain.state.phase == "RESEARCH"
    assert calls["n"] == 1


def test_runtime_never_allows_provider_to_execute(tmp_path):
    brain = OperationalBrain(tmp_path, "rt3", "safety")
    executed = []

    class MaliciousHint:
        def plan(self, context, actions):
            executed.append("provider-planned")
            return {"action": "delete_everything"}

    executor = FakeExecutor()
    runtime = CognitiveRuntime(brain, provider=MaliciousHint(), max_cycles=1)
    cycle = runtime.step(("research",), executor=executor)

    assert "provider-planned" in executed
    assert "delete_everything" not in executor.actions
    assert cycle.decision.action == "research"
