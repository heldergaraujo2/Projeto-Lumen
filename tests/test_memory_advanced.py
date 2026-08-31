"""Testes do RecordStore: persistência, dedup, update, obsolescência, busca."""
from __future__ import annotations

import json

import pytest

from app.memory.record_store import (
    DuplicateRecordError,
    RecordNotFoundError,
    RecordStore,
    RecordStoreError,
)
from app.memory.records import MemoryKind, RecordStatus


def make_store(tmp_path, kind=MemoryKind.KNOWLEDGE) -> RecordStore:
    return RecordStore(tmp_path / "store.json", kind)


# ------------------------------------------------------------------ persistir
def test_add_persists_and_reloads(tmp_path):
    """Persistência: grava em JSON e recarrega com todos os campos."""
    store = make_store(tmp_path)
    record = store.add("Cache de assets", "Usar DerivedDataCache no projeto Unreal",
                       origin="user", tags=("unreal", "build"), project_id="PRJ-0001")

    assert record.id == "KN-0001"
    assert record.status is RecordStatus.ACTIVE
    assert record.created_at and record.updated_at

    disk = json.loads((tmp_path / "store.json").read_text(encoding="utf-8"))
    assert disk[0]["id"] == "KN-0001"
    assert disk[0]["tags"] == ["unreal", "build"]

    reloaded = RecordStore(tmp_path / "store.json", MemoryKind.KNOWLEDGE)
    assert reloaded.get("KN-0001") == record


def test_sequential_ids_per_domain(tmp_path):
    store = make_store(tmp_path)
    store.add("a", "conteúdo a")
    store.add("b", "conteúdo b")
    assert [r.id for r in store.all()] == ["KN-0001", "KN-0002"]


def test_prefixes_are_per_domain(tmp_path):
    store = RecordStore(tmp_path / "issues.json", MemoryKind.ISSUE)
    record = store.add("Crash no build", "Segfault ao compilar shaders")
    assert record.id == "ERR-0001"


def test_empty_title_or_content_rejected(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(ValueError):
        store.add("   ", "conteúdo")
    with pytest.raises(ValueError):
        store.add("título", "   ")


# -------------------------------------------------------------------- dedup
def test_dedup_same_content_returns_existing(tmp_path):
    """Deduplicação básica: mesma informação não gera segundo registro."""
    store = make_store(tmp_path)
    first = store.add("Cache de assets", "Usar DDC")
    second = store.add("cache de ASSETS", "usar ddc")  # normalizado

    assert second.id == first.id
    assert store.count == 1


def test_dedup_considered_again_after_obsolete(tmp_path):
    """Informação obsoleta pode ser registrada de novo (nova versão)."""
    store = make_store(tmp_path)
    first = store.add("Estrutura", "padrão singleton")
    store.mark_obsolete(first.id)
    novo = store.add("Estrutura", "padrão singleton")

    assert novo.id == "KN-0002"
    assert store.count == 2


# ------------------------------------------------------------------- update
def test_update_changes_content_and_bumps_timestamp(tmp_path):
    store = make_store(tmp_path)
    record = store.add("Fluxo de build", "build.bat antigo")
    updated = store.update(record.id, content="build.bat novo com DDC", tags=("build",))

    assert updated.id == record.id
    assert updated.content == "build.bat novo com DDC"
    assert updated.tags == ("build",)
    assert updated.updated_at >= record.updated_at
    assert RecordStore(store.path, MemoryKind.KNOWLEDGE).get(record.id).content == \
        "build.bat novo com DDC"


def test_update_to_duplicate_active_raises(tmp_path):
    store = make_store(tmp_path)
    store.add("A", "conteúdo A")
    other = store.add("B", "conteúdo B")
    with pytest.raises(DuplicateRecordError):
        store.update(other.id, title="A", content="conteúdo A")
    # nada foi gravado
    assert store.get(other.id).title == "B"


def test_update_missing_raises(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(RecordNotFoundError):
        store.update("KN-9999", content="x")


# -------------------------------------------------------------- obsolescência
def test_mark_obsolete_keeps_history(tmp_path):
    store = make_store(tmp_path)
    record = store.add("Regra", "usar LFS para binários")
    store.mark_obsolete(record.id, reason="projeto migrou para SVN")

    obsolete = store.get(record.id)
    assert obsolete.status is RecordStatus.OBSOLETE
    assert store.count == 1  # histórico preservado
    assert store.filter(status=RecordStatus.ACTIVE) == []
    assert len(store.filter(status=RecordStatus.OBSOLETE)) == 1


def test_supersede_creates_trail(tmp_path):
    """supersede: novo registro com trilha (supersedes + relação)."""
    store = make_store(tmp_path)
    old = store.add("Pipeline", "antiga versão")
    new = store.supersede(old.id, "Pipeline", "nova versão com DDC")

    assert new.id == "KN-0002"
    assert new.supersedes == "KN-0001"
    assert "KN-0001" in new.related_ids
    assert store.get(old.id).status is RecordStatus.OBSOLETE
    assert store.get(new.id).status is RecordStatus.ACTIVE


# ---------------------------------------------------------------------- busca
def test_search_relevance_title_beats_content(tmp_path):
    store = make_store(tmp_path)
    store.add("Inventory System", "componente de itens com grid")
    store.add("Notas gerais", "o inventory system foi citado de passagem")

    hits = store.search("inventory system")
    assert hits[0].record.title == "Inventory System"   # título pesa mais
    assert all(isinstance(h.score, float) and h.score > 0 for h in hits)


def test_search_tags_and_accents(tmp_path):
    store = make_store(tmp_path)
    store.add("Build", "configuração de build", tags=("configuração",))
    hits = store.search("configuracao")  # sem acento encontra com acento
    assert hits and hits[0].record.id == "KN-0001"


def test_search_multi_term_bonus_and_limit(tmp_path):
    store = make_store(tmp_path)
    store.add("Sistema de inventário", "grid de itens")
    store.add("Sistema de crafting", "receitas")
    hits = store.search("sistema inventário", limit=1)
    assert len(hits) == 1
    assert hits[0].record.title == "Sistema de inventário"


def test_search_excludes_obsolete_unless_requested(tmp_path):
    store = make_store(tmp_path)
    record = store.add("Regra antiga", "usar python 3.11")
    store.mark_obsolete(record.id)

    assert store.search("regra antiga") == []
    hits = store.search("regra antiga", include_obsolete=True)
    # título 3×2 + bônus 1 = 7 de base; obsoleto pesa 0,2 → 1,4
    assert len(hits) == 1 and hits[0].score == pytest.approx(7 * 0.2)


def test_search_empty_query_returns_nothing(tmp_path):
    store = make_store(tmp_path)
    store.add("T", "conteúdo")
    assert store.search("   ") == []


# -------------------------------------------------------------------- filtros
def test_filter_by_project_and_tag(tmp_path):
    store = make_store(tmp_path)
    store.add("A", "alpha", project_id="PRJ-0001", tags=("unreal",))
    store.add("B", "beta", project_id="PRJ-0002", tags=("tool",))

    assert [r.title for r in store.filter(project_id="PRJ-0001")] == ["A"]
    assert [r.title for r in store.filter(tag="unreal")] == ["A"]


# ------------------------------------------------------- corrupção/segurança
def test_corrupted_file_raises_clear_error(tmp_path):
    path = tmp_path / "store.json"
    path.write_text("{corrompido", encoding="utf-8")
    with pytest.raises(RecordStoreError) as exc:
        RecordStore(path, MemoryKind.KNOWLEDGE)
    assert "corrompido" in str(exc.value)


def test_invalid_shape_raises(tmp_path):
    path = tmp_path / "store.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(RecordStoreError):
        RecordStore(path, MemoryKind.KNOWLEDGE)


def test_wrong_kind_file_raises(tmp_path):
    path = tmp_path / "store.json"
    path.write_text(json.dumps([{
        "id": "KN-0001", "kind": "PROJECT", "title": "t", "content": "c",
    }]), encoding="utf-8")
    with pytest.raises(RecordStoreError) as exc:
        RecordStore(path, MemoryKind.KNOWLEDGE)
    assert "domínio" in str(exc.value)


def test_secrets_never_persisted(tmp_path):
    """Segurança: segredos são redigidos antes de gravar no disco."""
    store = make_store(tmp_path)
    record = store.add("Config da API", "usar api_key=sk-supersegredo123456 no build")

    assert "sk-supersegredo123456" not in record.content
    assert "***" in record.content
    disk = (tmp_path / "store.json").read_text(encoding="utf-8")
    assert "sk-supersegredo123456" not in disk
