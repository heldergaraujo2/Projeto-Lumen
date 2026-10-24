"""Testes isolados do índice semântico Mem0; não exigem Ollama nem Mem0 instalado."""
from __future__ import annotations

from types import SimpleNamespace

from app.memory.mem0_index import Mem0SemanticIndex


def make_record():
    return SimpleNamespace(
        id="KN-0001",
        title="Inventário do jogo",
        content="O inventário usa um widget UMG com grade.",
        kind=SimpleNamespace(value="KNOWLEDGE"),
        project_id="age-of-aether",
    )


def test_mem0_is_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LUMEN_MEM0_ENABLED", raising=False)
    called = []
    index = Mem0SemanticIndex(tmp_path, client_factory=lambda config: called.append(config))

    assert index.enabled is False
    assert index.add_record(make_record()) is False
    assert index.search("como funciona o inventário") == []
    assert called == []


def test_mem0_config_is_local_and_stored_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_MEM0_ENABLED", "1")
    monkeypatch.setenv("LUMEN_MEM0_LLM_MODEL", "qwen-local")
    captured = []
    index = Mem0SemanticIndex(tmp_path / "mem0", client_factory=lambda config: captured.append(config) or object())

    index._get_client()
    config = captured[0]

    assert config["llm"]["provider"] == "ollama"
    assert config["llm"]["config"]["model"] == "qwen-local"
    assert config["embedder"]["provider"] == "ollama"
    assert config["vector_store"]["provider"] == "qdrant"
    assert config["vector_store"]["config"]["path"].startswith(str(tmp_path))
    assert config["history_db_path"].startswith(str(tmp_path))
    assert "api_key" not in str(config).lower()


def test_mem0_adds_structured_record_with_stable_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_MEM0_ENABLED", "true")

    class FakeClient:
        def __init__(self):
            self.add_calls = []

        def add(self, text, **kwargs):
            self.add_calls.append((text, kwargs))
            return {"results": []}

    client = FakeClient()
    index = Mem0SemanticIndex(tmp_path, client_factory=lambda _config: client)

    assert index.add_record(make_record()) is True
    text, kwargs = client.add_calls[0]
    assert "Inventário do jogo" in text
    assert kwargs["user_id"] == "lumen-local"
    assert kwargs["metadata"]["lumen_record_id"] == "KN-0001"
    assert kwargs["metadata"]["lumen_kind"] == "KNOWLEDGE"


def test_mem0_search_returns_only_grounded_record_references(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_MEM0_ENABLED", "1")

    class FakeClient:
        def search(self, query, **kwargs):
            assert query == "como funciona a grade do inventário"
            assert kwargs["user_id"] == "lumen-local"
            return {"results": [
                {"memory": "inventário usa UMG", "score": 0.91,
                 "metadata": {"lumen_record_id": "KN-0001", "lumen_kind": "KNOWLEDGE"}},
                {"memory": "memória inventada", "score": 0.99, "metadata": {}},
                {"memory": "duplicado", "score": 0.8,
                 "metadata": {"lumen_record_id": "KN-0001", "lumen_kind": "KNOWLEDGE"}},
            ]}

    index = Mem0SemanticIndex(tmp_path, client_factory=lambda _config: FakeClient())
    assert index.search("como funciona a grade do inventário") == [
        ("KN-0001", "KNOWLEDGE", 0.91)
    ]


def test_mem0_failure_fails_open_without_crashing(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_MEM0_ENABLED", "1")

    def fail(_config):
        raise RuntimeError("local model is offline")

    index = Mem0SemanticIndex(tmp_path, client_factory=fail)
    assert index.add_record(make_record()) is False
    assert index.enabled is False
    assert index.search("inventário") == []
