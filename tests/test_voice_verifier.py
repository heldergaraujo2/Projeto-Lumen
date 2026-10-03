import json

from app.evolution.voice_mission import VOICE_ACCEPTANCE_CRITERIA
from app.evolution.voice_verifier import VoiceMissionVerifier


def test_voice_verifier_requires_runtime_evidence(tmp_path):
    verifier = VoiceMissionVerifier(tmp_path / "voice_validation.json")
    ok, missing, evidence = verifier.verify()
    assert ok is False
    assert missing == VOICE_ACCEPTANCE_CRITERIA
    assert evidence == {}


def test_voice_verifier_accepts_only_complete_evidence(tmp_path):
    path = tmp_path / "voice_validation.json"
    payload = {criterion: True for criterion in VOICE_ACCEPTANCE_CRITERIA}
    payload["source"] = "runtime"
    path.write_text(json.dumps(payload), encoding="utf-8")

    ok, missing, evidence = VoiceMissionVerifier(path).verify()

    assert ok is True
    assert missing == ()
    assert evidence["source"] == "runtime"


def test_voice_verifier_reports_partial_runtime_evidence(tmp_path):
    path = tmp_path / "voice_validation.json"
    path.write_text(
        json.dumps({criterion: True for criterion in VOICE_ACCEPTANCE_CRITERIA[:3]}),
        encoding="utf-8",
    )
    ok, missing, _ = VoiceMissionVerifier(path).verify()
    assert ok is False
    assert missing == VOICE_ACCEPTANCE_CRITERIA[3:]
