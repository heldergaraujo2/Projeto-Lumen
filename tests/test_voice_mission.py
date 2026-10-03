from app.evolution.voice_mission import (
    VOICE_GOAL,
    VOICE_MISSION_ID,
    VOICE_ACCEPTANCE_CRITERIA,
    VoiceMissionSpec,
)


def test_voice_mission_is_self_development_and_does_not_require_unreal():
    spec = VoiceMissionSpec()
    assert spec.mission_id == VOICE_MISSION_ID
    assert spec.requires_unreal is False
    assert "microfone" in spec.goal.lower()
    assert "pesquisar" in spec.goal.lower()
    assert "testes" in spec.goal.lower()


def test_voice_mission_has_end_to_end_acceptance_criteria():
    spec = VoiceMissionSpec()
    context = spec.planner_context()
    assert tuple(context["acceptance_criteria"]) == VOICE_ACCEPTANCE_CRITERIA
    assert "UI" in VOICE_GOAL
    assert "STT" in VOICE_GOAL
    assert "TTS" in VOICE_GOAL


def test_voice_mission_is_not_complete_from_partial_evidence():
    spec = VoiceMissionSpec()
    evidence = {criterion: True for criterion in VOICE_ACCEPTANCE_CRITERIA[:-1]}
    assert spec.missing_criteria(evidence) == (VOICE_ACCEPTANCE_CRITERIA[-1],)
    assert spec.is_complete(evidence) is False


def test_voice_mission_requires_all_acceptance_evidence():
    spec = VoiceMissionSpec()
    evidence = {criterion: True for criterion in VOICE_ACCEPTANCE_CRITERIA}
    assert spec.missing_criteria(evidence) == ()
    assert spec.is_complete(evidence) is True
