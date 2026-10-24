"""Integração da busca Mem0 com a memória JSON autoritativa."""
from __future__ import annotations

from app.memory.records import MemoryKind
from app.memory.system import MemorySystem


class FakeSemanticIndex:
    def __init__(self, hits=()):
        self.hits = list(hits)
        self.added = []

    def add_record(self, record):
        self.added.append((record.id, record.kind.value))
        return True

    def search(self, query, limit=10):
        return self.hits[:limit]


def test_semantic_recall_finds_paraphrased_query(tmp_path):
    index = FakeSemanticIndex()
    system = MemorySystem(tmp_path, semantic_index=index)
    record = system.remember(
        MemoryKind.KNOWLEDGE,
        "Direção artística",
        "Age of Aether usa estilo painterly isométrico e diorama 2.5D.",
    )
    index.hits = [(record.id, "KNOWLEDGE", 0.92)]

    hits = system.recall("qual aparência visual foi decidida para o jogo?")

    assert hits[0].record.id == record.id
    assert hits[0].record.content == "Age of Aether usa estilo painterly isométrico e diorama 2.5D."
    assert index.added == [(record.id, "KNOWLEDGE")]


def test_semantic_recall_rejects_missing_or_obsolete_records(tmp_path):
    index = FakeSemanticIndex()
    system = MemorySystem(tmp_path, semantic_index=index)
    record = system.remember(MemoryKind.KNOWLEDGE, "Modelo", "usar modelo local")
    system.mark_obsolete(MemoryKind.KNOWLEDGE, record.id, reason="substituído")
    index.hits = [
        (record.id, "KNOWLEDGE", 0.99),
        ("KN-9999", "KNOWLEDGE", 0.98),
        ("KN-0001", "NOT_A_KIND", 0.97),
    ]

    assert system.recall("decisão sobre o modelo") == []


def test_semantic_recall_respects_domain_filter(tmp_path):
    index = FakeSemanticIndex()
    system = MemorySystem(tmp_path, semantic_index=index)
    knowledge = system.remember(MemoryKind.KNOWLEDGE, "Memória", "fato técnico")
    index.hits = [(knowledge.id, "KNOWLEDGE", 0.99)]

    assert system.recall("contexto semântico", kinds=[MemoryKind.DECISION]) == []


def test_mem0_does_not_replace_conversation_json(tmp_path):
    index = FakeSemanticIndex()
    system = MemorySystem(tmp_path, semantic_index=index)
    system.conversation.add_message("user", "preservar histórico")
    before = (tmp_path / "memory" / "conversation.json").read_text(encoding="utf-8")

    system.remember(MemoryKind.KNOWLEDGE, "Fato", "registro estruturado")
    after = (tmp_path / "memory" / "conversation.json").read_text(encoding="utf-8")

    assert after == before
