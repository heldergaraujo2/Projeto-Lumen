"""Teste real opt-in para validar Ollama + Mem0 + Qdrant local.

Ative explicitamente com LUMEN_MEM0_INTEGRATION_TESTS=1 após instalar o
extra opcional e baixar os modelos locais. Por padrão, nenhum serviço é chamado.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from app.memory.mem0_index import Mem0SemanticIndex


pytestmark = pytest.mark.skipif(
    os.getenv("LUMEN_MEM0_INTEGRATION_TESTS") != "1",
    reason="teste real local opt-in; requer Ollama, Mem0 e modelo de embeddings",
)


def test_local_mem0_add_and_semantic_search(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_MEM0_ENABLED", "1")
    monkeypatch.setenv("LUMEN_MEM0_EMBED_MODEL", "nomic-embed-text:latest")
    index = Mem0SemanticIndex(tmp_path / "mem0")
    record = SimpleNamespace(
        id="KN-LOCAL-INTEGRATION-001",
        title="Direção artística de Age of Aether",
        content=(
            "O jogo usa um diorama isométrico painterly 2.5D, "
            "com materiais pintados à mão e cidades de gelo e lava."
        ),
        kind=SimpleNamespace(value="KNOWLEDGE"),
        project_id="age-of-aether",
    )

    assert index.add_record(record) is True
    hits = index.search("qual é a estética visual e quais são os biomas das cidades?", limit=5)

    assert any(record_id == record.id and kind == "KNOWLEDGE"
               for record_id, kind, _score in hits)
