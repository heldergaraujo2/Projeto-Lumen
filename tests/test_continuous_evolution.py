import pytest

from app.evolution import (
    Capability,
    CapabilityMeasurement,
    Candidate,
    CandidateRegistry,
    CapabilityRegistry,
    ContinuousEvolutionMonitor,
    ContinuousEvolutionPlanner,
    EvolutionRisk,
    EvolutionState,
    MonitoringPolicy,
    MonitoringStatus,
    ResearchEvidence,
    ResearchKind,
    ResearchQuery,
    ResearchReport,
)


def setup_monitor():
    candidates = CandidateRegistry()
    capabilities = CapabilityRegistry()
    candidate = Candidate("C-1", "EVOLUTION-000001", "1.0", state=EvolutionState.PROMOTED)
    capabilities.register(Capability("cap-1", "Grounding"))
    candidates.register(candidate)
    monitor = ContinuousEvolutionMonitor(
        candidates=candidates,
        capabilities=capabilities,
        policy=MonitoringPolicy(min_samples=2, degradation_observations=2),
    )
    return monitor, candidates, candidate


def measurement(score):
    return CapabilityMeasurement("cap-1", score, "accuracy", 2, ("post-promotion",))


def test_promotion_must_be_monitored_before_observation():
    monitor, _, candidate = setup_monitor()
    with pytest.raises(ValueError):
        monitor.observe(candidate, measurement=measurement(.9))


def test_start_monitoring_requires_promoted_candidate():
    monitor, candidates, _ = setup_monitor()
    c = Candidate("C-2", "EVOLUTION-000002", "1.0")
    candidates.register(c)
    with pytest.raises(ValueError):
        monitor.start_monitoring(c, baseline=measurement(.9))


def test_start_monitoring_moves_candidate_to_monitored():
    monitor, candidates, candidate = setup_monitor()
    updated = monitor.start_monitoring(candidate, baseline=measurement(.9))
    assert updated.state is EvolutionState.MONITORED
    assert candidates.get("C-1").state is EvolutionState.MONITORED


def test_observation_below_sample_policy_is_rejected():
    monitor, _, candidate = setup_monitor()
    monitor.start_monitoring(candidate, baseline=measurement(.9))
    with pytest.raises(ValueError):
        monitor.observe(candidate, measurement=CapabilityMeasurement("cap-1", .8, "accuracy", 1))


def test_stable_observation_is_recorded():
    monitor, _, candidate = setup_monitor()
    monitor.start_monitoring(candidate, baseline=measurement(.9))
    result = monitor.observe(candidate, measurement=measurement(.91))
    assert result.status is MonitoringStatus.STABLE
    assert result.sample_count == 1
    assert len(monitor.history("C-1")) == 1


def test_single_degradation_triggers_bounded_improvement_proposal():
    monitor, _, candidate = setup_monitor()
    monitor.start_monitoring(candidate, baseline=measurement(.9))
    result = monitor.observe(candidate, measurement=measurement(.8))
    assert result.status is MonitoringStatus.DEGRADED
    trigger = monitor.trigger_if_needed(candidate, result)
    assert trigger is not None
    assert trigger.risk is EvolutionRisk.MEDIUM
    assert trigger.requires_human_approval


def test_repeated_degradation_becomes_regression():
    monitor, _, candidate = setup_monitor()
    monitor.start_monitoring(candidate, baseline=measurement(.9))
    monitor.observe(candidate, measurement=measurement(.8))
    result = monitor.observe(candidate, measurement=measurement(.79))
    assert result.status is MonitoringStatus.REGRESSED
    trigger = monitor.trigger_if_needed(candidate, result)
    assert trigger is not None
    assert trigger.risk is EvolutionRisk.HIGH
    assert trigger.requires_human_approval
    assert len(trigger.observation_ids) == 2


def test_recovery_to_baseline_is_stable():
    monitor, _, candidate = setup_monitor()
    monitor.start_monitoring(candidate, baseline=measurement(.9))
    monitor.observe(candidate, measurement=measurement(.8))
    result = monitor.observe(candidate, measurement=measurement(.9))
    assert result.status is MonitoringStatus.STABLE
    assert monitor.trigger_if_needed(candidate, result) is None


def test_history_is_bounded():
    monitor, _, candidate = setup_monitor()
    monitor.start_monitoring(candidate, baseline=measurement(.9))
    for _ in range(60):
        monitor.observe(candidate, measurement=measurement(.9))
    assert len(monitor.history("C-1")) == 50


def test_monitoring_has_no_execution_surface():
    monitor, _, _ = setup_monitor()
    assert not hasattr(monitor, "execute")
    assert not hasattr(monitor, "deploy")
    assert not hasattr(monitor, "rollback")
    assert not hasattr(monitor, "grant_permission")


def test_trigger_does_not_change_candidate_state():
    monitor, candidates, candidate = setup_monitor()
    monitor.start_monitoring(candidate, baseline=measurement(.9))
    monitor.observe(candidate, measurement=measurement(.8))
    result = monitor.observe(candidate, measurement=measurement(.79))
    trigger = monitor.trigger_if_needed(candidates.get("C-1"), result)
    assert trigger is not None
    assert candidates.get("C-1").state is EvolutionState.MONITORED


def test_planner_links_monitoring_trigger_to_research():
    monitor, _, candidate = setup_monitor()
    monitor.start_monitoring(candidate, baseline=measurement(.9))
    monitor.observe(candidate, measurement=measurement(.8))
    result = monitor.observe(candidate, measurement=measurement(.79))
    trigger = monitor.trigger_if_needed(candidate, result)
    report = ResearchReport(
        ResearchQuery("Q1", "cap-1", "improve grounding"),
        (ResearchEvidence("E1", ResearchKind.PAPER, "paper://1", "method", .8),),
    )
    opportunity = ContinuousEvolutionPlanner().create_opportunity(trigger, report=report)
    assert opportunity.capability_id == "cap-1"
    assert opportunity.evidence_ids == ("E1",)


def test_planner_rejects_wrong_capability():
    monitor, _, candidate = setup_monitor()
    monitor.start_monitoring(candidate, baseline=measurement(.9))
    monitor.observe(candidate, measurement=measurement(.8))
    result = monitor.observe(candidate, measurement=measurement(.79))
    trigger = monitor.trigger_if_needed(candidate, result)
    report = ResearchReport(ResearchQuery("Q1", "other", "x"), ())
    with pytest.raises(ValueError):
        ContinuousEvolutionPlanner().create_opportunity(trigger, report=report)
