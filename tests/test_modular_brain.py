from app.evolution.modular_brain import BACKENDS, BackendStatus, ModularBrainProvider, ModularCognitiveBrain
from app.evolution.operational_brain import ActionOutcome, OperationalBrain

class Environment:
    def __init__(self): self.executed = []
    def available_actions(self): return ("research", "observe_unreal")
    def observe(self): return {"objective": "pesquisar como melhorar o projeto"}
    def execute(self, action, *, context):
        self.executed.append(action)
        return ActionOutcome(action=action, success=True, result=f"ok:{action}", new_information=True)

def test_all_researched_frameworks_are_registered():
    assert {x.name for x in BACKENDS} == {"openai_agents", "openhands", "browser_use", "autogen", "langgraph"}

def test_provider_is_advisory_only():
    hints = ModularBrainProvider().plan({"objective": "implementar código"}, ("research",))
    assert "routing" in hints and "openai_agents" in hints

def test_modular_brain_keeps_execution_in_environment(tmp_path):
    brain = OperationalBrain(tmp_path, "m1", "pesquisar como melhorar o projeto")
    env = Environment()
    cycle = ModularCognitiveBrain(brain, max_cycles=1).step(env)
    assert cycle.outcome.success
    assert env.executed == [cycle.decision.action]
    assert cycle.decision.action in env.available_actions()

def test_backend_status_is_non_fatal():
    brain = object.__new__(ModularCognitiveBrain)
    brain.specialist_provider = ModularBrainProvider()
    statuses = brain.backend_status()
    assert all(isinstance(item, BackendStatus) for item in statuses)
    assert {x.name for x in statuses} == {"openai_agents", "openhands", "browser_use", "autogen", "langgraph"}
