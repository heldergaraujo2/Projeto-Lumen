from pathlib import Path

from app.evolution.autonomous_loop import GitGuard


def test_runtime_state_is_not_treated_as_source_dirty():
    assert GitGuard.is_runtime_state("data/learning/knowledge.json")
    assert GitGuard.is_runtime_state("data/evolution/mission.json")
    assert GitGuard.is_runtime_state("./data/evolution/autonomous_progress.json")
    assert not GitGuard.is_runtime_state("app/evolution/autonomous_loop.py")
    assert not GitGuard.is_runtime_state("tests/test_autonomous_evolution_runtime_state.py")


def test_tracked_dirty_ignores_runtime_state():
    guard = object.__new__(GitGuard)
    guard.status = lambda: [
        " M data/learning/knowledge.json",
        " M data/evolution/mission.json",
        " M app/evolution/autonomous_loop.py",
    ]

    assert guard.tracked_dirty() is True


def test_changed_since_excludes_runtime_state():
    guard = object.__new__(GitGuard)

    class Result:
        returncode = 0
        stdout = (
            "data/learning/knowledge.json\\n"
            "data/evolution/mission.json\\n"
            "app/evolution/autonomous_loop.py\\n"
        )
        stderr = ""

    guard.run = lambda *args, **kwargs: Result()

    assert guard.changed_since("abc") == ["app/evolution/autonomous_loop.py"]


def test_commit_rejects_runtime_only_changes():
    guard = object.__new__(GitGuard)
    guard.run = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("git should not run for runtime-only changes")
    )

    try:
        guard.commit(["data/learning/knowledge.json"], "runtime")
    except Exception as exc:
        assert str(exc) == "no source changes"
    else:
        raise AssertionError("expected runtime-only commit to be rejected")
