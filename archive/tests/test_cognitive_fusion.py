from app.evolution.cognitive_fusion import CapabilityGap, CognitiveFusion, EvolutionHypothesis, Experience, QuantumInspiredOptimizer, ResearchFinding, ToolCandidate, WorldFact

def test_fusion_stacks_layers(tmp_path):
    c = CognitiveFusion(tmp_path, "M")
    c.ingest_world([WorldFact("unreal.ready", True, "mcp")])
    c.learn(ResearchFinding("R1", "vision", "use live observation", ("src",), 0.9))
    c.register_gap(CapabilityGap("unreal.vision", "needs better observation", 0.8))
    c.propose_hypothesis(EvolutionHypothesis("H1", "unreal.vision", "better observation reduces errors", 0.7, "E1"))
    c.observe_experience(Experience("X1", "observe", {}, "observe_unreal", "ok", True, "observation works"))
    ctx = c.planner_context()
    assert ctx["world_facts"][0]["key"] == "unreal.ready"
    assert ctx["research"][0]["finding_id"] == "R1"
    assert ctx["capability_gaps"][0]["capability_id"] == "unreal.vision"
    assert "observation works" in ctx["lessons"]

def test_quantum_inspired_search_reproducible():
    q = QuantumInspiredOptimizer(seed=11)
    a = q.rank([{"id": "a", "score": 1}, {"id": "b", "score": 0.5}])
    b = q.rank([{"id": "a", "score": 1}, {"id": "b", "score": 0.5}])
    assert [x["id"] for x in a] == [x["id"] for x in b]

def test_temporal_learning(tmp_path):
    c = CognitiveFusion(tmp_path, "M")
    c.observe_experience(Experience("1", "o", {}, "observe", "call", True))
    assert "call" in c.planner_context()["temporal_predictions"]["after_last_action"]

def test_high_risk_tool_is_not_admitted(tmp_path):
    c = CognitiveFusion(tmp_path, "M")
    try:
        c.propose_tool(ToolCandidate("T", "danger", (), (), risk="high"))
        assert False
    except PermissionError:
        pass

def test_validation_gate(tmp_path):
    c = CognitiveFusion(tmp_path, "M")
    assert not c.should_promote(tests_passed=True, benchmarked=False, rollback_ready=True)
    assert c.should_promote(tests_passed=True, benchmarked=True, rollback_ready=True)

def test_capability_validation_closes_gap(tmp_path):
    c = CognitiveFusion(tmp_path, "M")
    c.register_gap(CapabilityGap("x", "missing"))
    c.validate_capability("x", "integration test passed")
    assert c.capabilities.is_validated("x")
    assert not c.capabilities.gaps()

def test_snapshot_is_persisted(tmp_path):
    c = CognitiveFusion(tmp_path, "M")
    assert c.persist_snapshot().exists()

def test_world_contradiction(tmp_path):
    c = CognitiveFusion(tmp_path, "M")
    c.ingest_world([WorldFact("x", 1, "a", 0.9)])
    assert c.world.contradiction("x", 2)
