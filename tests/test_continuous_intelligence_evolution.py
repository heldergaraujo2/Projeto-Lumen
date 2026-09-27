import pytest
from app.evolution.continuous import MonitoringStatus
from app.evolution.continuous_intelligence import (
    ContinuousIntelligenceEvolution, ContinuousIntelligencePlan, IntelligenceCycleState,
    IntelligenceObservation, IntelligenceTrigger
)

def obs(id="CI-EV-000001", score=.8, baseline=.8):
    return IntelligenceObservation(id, "reasoning", score, 10, "fixture", baseline)

def test_policy_validation():
    with pytest.raises(ValueError): ContinuousIntelligenceEvolution(min_samples=0)
    with pytest.raises(ValueError): ContinuousIntelligenceEvolution(degradation_threshold=-1)

def test_cycle_observation_and_assessment():
    e=ContinuousIntelligenceEvolution()
    c=e.start_cycle("reasoning", .8)
    o=obs()
    e.observe(o)
    updated=e.assess(c.cycle_id,o)
    assert updated.state is IntelligenceCycleState.ASSESSED
    assert updated.latest_score == .8

def test_degradation_triggers_new_cycle_work():
    e=ContinuousIntelligenceEvolution()
    c=e.start_cycle("reasoning", .8)
    o=obs(score=.6)
    updated=e.assess(c.cycle_id,o)
    assert updated.state is IntelligenceCycleState.TRIGGERED
    trigger=e.trigger(c.cycle_id)
    assert isinstance(trigger, IntelligenceTrigger)
    assert trigger.status is MonitoringStatus.REGRESSED
    plan=e.plan(trigger,actions=("research", "benchmark", "security_review"))
    assert isinstance(plan, ContinuousIntelligencePlan)
    assert plan.isolated and plan.requires_human_approval
    assert e.counts()=={"observations":1,"cycles":1,"triggers":1,"plans":1}

def test_trigger_requires_degradation():
    e=ContinuousIntelligenceEvolution()
    c=e.start_cycle("reasoning", .8)
    e.assess(c.cycle_id,obs(score=.81))
    assert e.trigger(c.cycle_id) is None

def test_observation_rejects_wrong_capability_or_baseline():
    e=ContinuousIntelligenceEvolution(); c=e.start_cycle("reasoning",.8)
    with pytest.raises(ValueError): e.assess(c.cycle_id,IntelligenceObservation("CI-EV-2","vision",.7,10,"x",.8))
    with pytest.raises(ValueError): e.assess(c.cycle_id,IntelligenceObservation("CI-EV-3","reasoning",.7,10,"x",.7))

def test_observation_sample_floor_and_duplicate():
    e=ContinuousIntelligenceEvolution(min_samples=5); e.start_cycle("reasoning",.8)
    with pytest.raises(ValueError): e.observe(IntelligenceObservation("CI-EV-1","reasoning",.8,1,"x",.8))
    e.observe(obs())
    with pytest.raises(ValueError): e.observe(obs())

def test_trigger_and_plan_validation():
    with pytest.raises(ValueError): IntelligenceTrigger("bad","CI-CYCLE-1","reasoning",MonitoringStatus.REGRESSED,"x",__import__('app.evolution.models',fromlist=['EvolutionRisk']).EvolutionRisk.HIGH,()).validate()
    with pytest.raises(ValueError): ContinuousIntelligencePlan("CI-PLAN-1","CI-TRIGGER-1","reasoning",("x",),(),False,True).validate()

def test_digest_is_deterministic():
    e=ContinuousIntelligenceEvolution(); c=e.start_cycle("reasoning",.8); e.assess(c.cycle_id,obs(score=.6)); e.trigger(c.cycle_id)
    assert e.digest()==e.digest() and len(e.digest())==64

def test_history_is_bounded():
    e=ContinuousIntelligenceEvolution(history_limit=2)
    e.observe(IntelligenceObservation("CI-EV-1","reasoning",.8,1,"x",.8))
    e.observe(IntelligenceObservation("CI-EV-2","reasoning",.8,1,"x",.8))
    e.observe(IntelligenceObservation("CI-EV-3","reasoning",.8,1,"x",.8))
    assert e.counts()["observations"]==2

def test_security_surface_is_non_executing():
    names=set(dir(ContinuousIntelligenceEvolution))
    forbidden={"execute","run_model","train","infer","deploy","download_model","grant_permission","change_policy","disable_audit","widen_scope","run_browser","run_tool","execute_driver"}
    assert not names.intersection(forbidden)

def test_cycle_requires_human_approval_when_active():
    c=__import__('app.evolution.continuous_intelligence',fromlist=['IntelligenceCycle'] ).IntelligenceCycle("CI-CYCLE-1","reasoning",IntelligenceCycleState.WAITING_GATES,.8,.6,("CI-EV-1",),"degraded",__import__('app.evolution.models',fromlist=['EvolutionRisk']).EvolutionRisk.HIGH,False)
    with pytest.raises(ValueError): c.validate()

def test_invalid_assessment_is_atomic_and_does_not_record_observation():
    e=ContinuousIntelligenceEvolution()
    c=e.start_cycle("reasoning", .8)
    bad=IntelligenceObservation("CI-EV-BAD","vision",.6,10,"fixture",.8)
    with pytest.raises(ValueError):
        e.assess(c.cycle_id,bad)
    assert e.counts()["observations"] == 0


def test_duplicate_trigger_is_rejected():
    e=ContinuousIntelligenceEvolution()
    c=e.start_cycle("reasoning", .8)
    e.assess(c.cycle_id,obs(score=.6))
    e.trigger(c.cycle_id)
    with pytest.raises(ValueError):
        e.trigger(c.cycle_id)


def test_duplicate_plan_is_rejected():
    e=ContinuousIntelligenceEvolution()
    c=e.start_cycle("reasoning", .8)
    e.assess(c.cycle_id,obs(score=.6))
    trigger=e.trigger(c.cycle_id)
    e.plan(trigger,actions=("research",))
    with pytest.raises(ValueError):
        e.plan(trigger,actions=("benchmark",))


def test_threshold_boundary_is_not_regression():
    e=ContinuousIntelligenceEvolution(degradation_threshold=.1)
    c=e.start_cycle("reasoning", .8)
    updated=e.assess(c.cycle_id,obs(score=.7))
    assert updated.state is IntelligenceCycleState.ASSESSED


def test_assessment_rejects_invalid_sample_without_mutation():
    e=ContinuousIntelligenceEvolution(min_samples=5)
    c=e.start_cycle("reasoning", .8)
    bad=IntelligenceObservation("CI-EV-SMALL","reasoning",.7,1,"fixture",.8)
    with pytest.raises(ValueError):
        e.assess(c.cycle_id,bad)
    assert e.counts()["observations"] == 0


def test_plan_rejects_unregistered_trigger():
    e=ContinuousIntelligenceEvolution()
    c=e.start_cycle("reasoning", .8)
    trigger=IntelligenceTrigger("CI-TRIGGER-999999",c.cycle_id,"reasoning",MonitoringStatus.REGRESSED,"degraded",__import__('app.evolution.models',fromlist=['EvolutionRisk']).EvolutionRisk.HIGH,("CI-EV-1",))
    with pytest.raises(KeyError):
        e.plan(trigger,actions=("research",))
