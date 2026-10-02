from app.learning.runtime import LearningRuntime, LearningStore


def test_repeated_research_finding_is_not_saved_twice(tmp_path):
    runtime = LearningRuntime(LearningStore(tmp_path / "knowledge.json"))
    finding = {
        "query": "Unreal MCP capability",
        "claim": "A reusable capability exists.",
        "evidence": ("https://example.test/source",),
        "confidence": 0.25,
    }

    _, first = runtime.ingest_research("Unreal MCP capability", [finding])
    _, second = runtime.ingest_research("Unreal MCP capability", [finding])

    assert len(first) == 1
    assert len(second) == 0
    assert runtime.store.counts()["knowledge"] == 1
