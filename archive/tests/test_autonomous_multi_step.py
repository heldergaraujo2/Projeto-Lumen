import pytest

from app.autonomy import (
    AutonomousMultiStepAgent, AutonomyGrant, AutonomyLimits, MultiStep, MultiStepTask,
    RunState, StepState,
)


class FakeExecutor:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def execute(self, step):
        self.calls.append(step.step_id)
        outcome = self.outcomes.pop(0) if self.outcomes else (True, "verified")
        return outcome


def task(count):
    return MultiStepTask(
        "task-1", "complete test task",
        tuple(MultiStep(f"s{i}", f"step {i}", object()) for i in range(count))
    )


def grant(max_steps=5, approved=True):
    return AutonomyGrant("grant-1", "scope-1", max_steps, approved)


def test_authorization_requires_human_approval():
    agent = AutonomousMultiStepAgent.create()
    with pytest.raises(PermissionError):
        agent.validate_authorization(grant=grant(approved=False), task=task(1))


def test_authorization_respects_step_budget():
    agent = AutonomousMultiStepAgent.create(limits=AutonomyLimits(max_steps=2))
    with pytest.raises(PermissionError):
        agent.validate_authorization(grant=grant(3), task=task(3))


def test_runs_steps_in_order_and_completes():
    agent = AutonomousMultiStepAgent.create()
    executor = FakeExecutor([(True, "verified"), (True, "verified"), (True, "verified")])
    result = agent.run(task=task(3), grant=grant(), executor=executor)
    assert result.state is RunState.COMPLETED
    assert executor.calls == ["s0", "s1", "s2"]
    assert all(x.state is StepState.VERIFIED for x in result.steps)


def test_failure_uses_bounded_retry_then_completes():
    agent = AutonomousMultiStepAgent.create(limits=AutonomyLimits(max_step_attempts=2))
    executor = FakeExecutor([(False, "temporary busy"), (True, "verified")])
    result = agent.run(task=task(1), grant=grant(), executor=executor)
    assert result.state is RunState.COMPLETED
    assert result.recoveries == 1
    assert result.steps[0].attempts == 2


def test_security_failure_is_terminal_and_blocked():
    agent = AutonomousMultiStepAgent.create()
    executor = FakeExecutor([(False, "permission denied")])
    result = agent.run(task=task(1), grant=grant(), executor=executor)
    assert result.state is RunState.BLOCKED
    assert result.steps[0].state is StepState.BLOCKED
    assert len(executor.calls) == 1


def test_recovery_budget_stops_infinite_loop():
    agent = AutonomousMultiStepAgent.create(
        limits=AutonomyLimits(max_recoveries=1, max_step_attempts=3)
    )
    executor = FakeExecutor([(False, "temporary busy"), (False, "temporary busy"), (True, "verified")])
    result = agent.run(task=task(1), grant=grant(), executor=executor)
    assert result.state is RunState.FAILED
    assert result.steps[0].state is StepState.FAILED
    assert result.recoveries == 2


def test_step_requesting_human_approval_is_blocked_from_autonomous_run():
    agent = AutonomousMultiStepAgent.create()
    risky = MultiStep("risky", "risky", object(), requires_human_approval=True)
    with pytest.raises(PermissionError):
        agent.validate_authorization(
            grant=grant(), task=MultiStepTask("t", "t", (risky,))
        )


def test_step_count_limit_is_enforced():
    agent = AutonomousMultiStepAgent.create(limits=AutonomyLimits(max_steps=2))
    with pytest.raises(PermissionError):
        agent.run(task=task(3), grant=grant(2), executor=FakeExecutor([]))


def test_empty_task_is_rejected():
    agent = AutonomousMultiStepAgent.create()
    with pytest.raises(ValueError):
        agent.validate_authorization(
            grant=grant(), task=MultiStepTask("x", "x", ())
        )


def test_workflow_suggestion_is_optional_and_non_executing():
    agent = AutonomousMultiStepAgent.create()
    assert agent.suggest_workflow(goal="qualquer coisa") == ()
