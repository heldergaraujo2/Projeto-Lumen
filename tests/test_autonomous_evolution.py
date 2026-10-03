from pathlib import Path

import pytest

from app.evolution.autonomous_loop import AutonomousEvolutionLoop, EvolutionConfig, EvolutionLoopError


def config(repo: Path, **kwargs) -> EvolutionConfig:
    fast_test = kwargs.setdefault(
        "fast_test",
        ("python", "-m", "pytest", "tests/test_autonomous_evolution.py", "-q"),
    )
    del fast_test
    test_file = repo / "tests" / "test_autonomous_evolution.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("# isolated fast-test fixture\n", encoding="utf-8")
    return EvolutionConfig(
        repo=repo,
        goal="test autonomous evolution",
        branch="feature/web-research-agent",
        **kwargs,
    )


def test_fast_test_points_to_existing_regression_suite():
    cfg = EvolutionConfig(repo=Path.cwd(), goal="goal")
    fast_test_path = next((Path(part) for part in cfg.fast_test if part.endswith(".py")), None)
    assert fast_test_path is not None
    assert (cfg.repo / fast_test_path).is_file()


def test_missing_fast_test_is_rejected(tmp_path):
    cfg = config(tmp_path, fast_test=("python", "-m", "pytest", "tests/missing_fast_test.py", "-q"))
    with pytest.raises(EvolutionLoopError, match="fast test"):
        cfg.validate()


def test_apply_rejects_protected_paths(tmp_path):
    loop = AutonomousEvolutionLoop(config(tmp_path))
    with pytest.raises(EvolutionLoopError, match="protected path"):
        loop.apply([{"path": "app/policy.py", "content": "x"}], [])


def test_apply_rejects_preexisting_untracked_file(tmp_path):
    loop = AutonomousEvolutionLoop(config(tmp_path))
    with pytest.raises(EvolutionLoopError, match="pre-existing untracked"):
        loop.apply([{"path": "scratch.py", "content": "x"}], ["?? scratch.py"])


def test_apply_creates_new_file(tmp_path):
    loop = AutonomousEvolutionLoop(config(tmp_path))
    created = loop.apply([{"path": "app/generated.py", "content": "VALUE = 1\n"}], [])
    assert created == [tmp_path / "app" / "generated.py"]


def test_cycle_commits_only_after_both_tests_pass(tmp_path):
    loop = AutonomousEvolutionLoop(config(tmp_path, max_attempts_per_cycle=1))
    calls = []
    loop.git.branch = lambda: "feature/web-research-agent"
    loop.git.tracked_dirty = lambda: False
    loop.git.head = lambda: "abc"
    loop.git.status = lambda: []
    loop.git.changed_since = lambda sha: ["app/generated.py"]
    loop.git.commit = lambda paths, message: calls.append(("commit", paths, message)) or "def"
    loop.model.chat = lambda system, prompt: '{"summary":"test","changes":[{"path":"app/generated.py","content":"VALUE = 1\\n"}],"commit_message":"test evolution"}'
    results = iter([(True, "fast ok"), (True, "full ok")])
    loop.run_tests = lambda command: next(results)
    assert loop.cycle(1) == "def"
    assert calls == [("commit", ["app/generated.py"], "test evolution")]


def test_cycle_rolls_back_when_fast_test_fails(tmp_path):
    loop = AutonomousEvolutionLoop(config(tmp_path, max_attempts_per_cycle=1))
    rollback = []
    loop.git.branch = lambda: "feature/web-research-agent"
    loop.git.tracked_dirty = lambda: False
    loop.git.head = lambda: "abc"
    loop.git.status = lambda: []
    loop.git.changed_since = lambda sha: ["app/generated.py"]
    loop.git.rollback = lambda sha, paths: rollback.append((sha, paths))
    loop.model.chat = lambda system, prompt: '{"summary":"test","changes":[{"path":"app/generated.py","content":"VALUE = 1\\n"}],"commit_message":"test evolution"}'
    loop.run_tests = lambda command: (False, "file or directory not found")
    assert loop.cycle(1) == "rolled_back"
    assert rollback == [("abc", ["app/generated.py"])]
