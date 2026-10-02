from pathlib import Path

from app.learning.runtime import KnowledgeStatus, LearningRuntime, LearningStore


def test_research_is_persisted_as_reusable_candidate_knowledge(tmp_path: Path):
    runtime = LearningRuntime(LearningStore(tmp_path / "knowledge.json"))

    goal, items = runtime.ingest_research(
        "Unreal MCP tool discovery",
        [
            {
                "query": "Unreal MCP tool discovery",
                "claim": "The MCP server advertises toolsets that can be inspected before calls.",
                "evidence": ("https://example.test/mcp",),
            }
        ],
    )

    assert goal.status == "researched"
    assert len(items) == 1
    assert items[0].status is KnowledgeStatus.CANDIDATE

    reloaded = LearningRuntime(LearningStore(tmp_path / "knowledge.json"))
    recent = reloaded.recent_knowledge()
    assert recent[0].claim.startswith("The MCP server advertises")
    assert recent[0].evidence == ("https://example.test/mcp",)


def test_research_knowledge_can_be_reused_without_marking_it_verified(tmp_path: Path):
    runtime = LearningRuntime(LearningStore(tmp_path / "knowledge.json"))
    _, items = runtime.ingest_research(
        "C++ Unreal",
        [{"query": "C++ Unreal", "claim": "Use a bounded compile-and-test loop.", "sources": ("source-a", "source-b")}],
    )

    recalled = runtime.recall("C++ Unreal", verified_only=False)
    verified = runtime.recall("C++ Unreal", verified_only=True)

    assert [x.knowledge_id for x in recalled] == [items[0].knowledge_id]
    assert verified == ()


def test_research_truncates_oversized_web_finding_to_store_limit(tmp_path: Path):
    store = LearningStore(tmp_path / "knowledge.json", max_text=256)
    runtime = LearningRuntime(store)

    _, items = runtime.ingest_research(
        "Unreal MCP",
        [{"query": "Unreal MCP", "claim": "x" * 2000, "evidence": ("source",)}],
    )

    assert len(items) == 1
    assert len(items[0].claim) == 256
    assert items[0].claim == "x" * 256
