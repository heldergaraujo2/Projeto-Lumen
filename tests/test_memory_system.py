"""Testes da MemorySystem: domínios, busca unificada, contexto e relações."""
from __future__ import annotations

import pytest

from app.memory.records import MemoryKind, RecordStatus
from app.memory.system import MemorySystem
from app.memory.store import MemoryStore


def make_system(tmp_path, max_records=3) -> MemorySystem:
    return MemorySystem(tmp_path, max_context_records=max_records)


# ------------------------------------------------------------------ domínios
def test_six_domains_with_separate_files(tmp_path):
    """Separação clara: cada domínio estruturado tem seu arquivo."""
    system = make_system(tmp_path)
    system.remember(MemoryKind.PROJECT, "Jogo de terror", "Unreal 5, C++, horror")
    system.remember(MemoryKind.TASK, "Criar inventário", "widget de grid concluído")
    system.remember(MemoryKind.KNOWLEDGE, "DDC", "cache acelera builds")
    system.remember(MemoryKind.DECISION, "Usar LFS", "binários fora do Git")
    system.remember(MemoryKind.ISSUE, "Crash no shader", "segfault ao compilar")
    system.remember(MemoryKind.SOLUTION, "Fix do shader", "atualizar driver de vídeo")

    memory_dir = tmp_path / "memory"
    for filename in ("projects.json", "task_records.json", "knowledge.json",
                     "decisions.json", "issues.json", "solutions.json"):
        assert (memory_dir / filename).exists(), f"arquivo do domínio ausente: {filename}"

    stats = system.stats()
    assert stats["PROJECT"] == 1 and stats["ISSUE"] == 1
    assert set(stats) == {"CONVERSATION", "PROJECT", "TASK", "KNOWLEDGE",
                          "DECISION", "ISSUE", "SOLUTION"}


def test_records_carry_origin_and_relations(tmp_path):
    system = make_system(tmp_path)
    issue = system.remember(MemoryKind.ISSUE, "Crash no shader", "segfault",
                            origin="agent")
    solution = system.remember(MemoryKind.SOLUTION, "Fix do shader", "driver novo",
                               origin="agent", related_ids=(issue.id,))
    assert issue.origin == "agent"
    assert issue.id in system.get(MemoryKind.SOLUTION, solution.id).related_ids


def test_bidirectional_relate(tmp_path):
    system = make_system(tmp_path)
    issue = system.remember(MemoryKind.ISSUE, "Erro X", "descrição")
    solution = system.remember(MemoryKind.SOLUTION, "Solução X", "descrição")
    updated = system.relate(issue.id, solution.id)

    ids = {r.id for r in updated}
    assert ids == {issue.id, solution.id}
    assert solution.id in system.get(MemoryKind.ISSUE, issue.id).related_ids
    assert issue.id in system.get(MemoryKind.SOLUTION, solution.id).related_ids


def test_relate_unknown_ids_raises(tmp_path):
    system = make_system(tmp_path)
    with pytest.raises(Exception):
        system.relate("ERR-9999", "SOL-9999")


# -------------------------------------------------------- persistência/reload
def test_system_persists_across_instances(tmp_path):
    system = make_system(tmp_path)
    system.remember(MemoryKind.DECISION, "Usar SQLite", "migração futura")
    system.conversation.add_message("user", "decidimos usar sqlite")

    reloaded = MemorySystem(tmp_path)
    assert reloaded.get(MemoryKind.DECISION, "DEC-0001").title == "Usar SQLite"
    assert reloaded.conversation.count == 1


# ------------------------------------------------------------- busca unificada
def test_recall_across_domains_sorted_by_relevance(tmp_path):
    system = make_system(tmp_path)
    system.remember(MemoryKind.KNOWLEDGE, "Sistema de inventário", "grid de itens")
    system.remember(MemoryKind.DECISION, "Padrão de UI", "decisão: usar UMG no inventário")
    system.remember(MemoryKind.PROJECT, "Jogo de fazenda", "colheita e plantio")

    hits = system.recall("inventário")
    kinds = [h.record.kind.value for h in hits]
    assert kinds[:2] == ["KNOWLEDGE", "DECISION"]  # título (3) > conteúdo (1)
    assert "PROJECT" not in kinds


def test_recall_respects_limit_and_kinds_filter(tmp_path):
    system = make_system(tmp_path, max_records=2)
    system.remember(MemoryKind.KNOWLEDGE, "inventário A", "conteúdo")
    system.remember(MemoryKind.DECISION, "inventário B", "conteúdo")
    system.remember(MemoryKind.ISSUE, "inventário C", "conteúdo")

    assert len(system.recall("inventário")) == 2  # budget
    hits = system.recall("inventário", kinds=[MemoryKind.ISSUE])
    assert [h.record.kind for h in hits] == [MemoryKind.ISSUE]


# ------------------------------------------------------------ contexto limitado
def test_build_context_structured_first_then_conversation(tmp_path):
    """Contexto: registros estruturados primeiro; conversa completa a cota."""
    system = make_system(tmp_path, max_records=3)
    system.remember(MemoryKind.KNOWLEDGE, "Sistema de inventário", "grid de itens")
    system.conversation.add_message("user", "como fizemos o inventário?")
    system.conversation.add_message("assistant", "usamos um widget de grid")

    context = system.build_context("inventário")
    kinds = [entry.kind for entry in context]

    assert len(context) <= 3                       # limite respeitado
    assert kinds[0] == "KNOWLEDGE"                  # estruturado primeiro
    assert "CONVERSATION" in kinds                  # conversa completa a cota
    assert all(entry.content for entry in context)
    assert context[0].record_id == "KN-0001"


def test_build_context_respects_budget_zero_left(tmp_path):
    system = make_system(tmp_path, max_records=1)
    system.remember(MemoryKind.KNOWLEDGE, "inventário", "grid")
    system.conversation.add_message("user", "inventário")

    context = system.build_context("inventário")
    assert len(context) == 1
    assert context[0].kind == "KNOWLEDGE"


def test_build_context_excerpts_long_content(tmp_path):
    system = make_system(tmp_path)
    system.remember(MemoryKind.KNOWLEDGE, "grande", "x" * 2000)
    entry = system.build_context("grande")[0]
    assert len(entry.content) <= 400 + 1  # excerto + elipse


def test_conversation_search_matches_accents_and_order(tmp_path):
    store = MemoryStore(tmp_path / "c.json")
    store.add_message("user", "Configuração do inventário")
    store.add_message("assistant", "feito")
    store.add_message("user", "outra configuração")

    found = store.search("configuracao")
    assert [m.content for m in found] == [
        "Configuração do inventário", "outra configuração"
    ]
    assert store.search("zzz") == []
    assert store.search("configuracao", limit=1)[0].content == "outra configuração"


# --------------------------------------------------------------------- obsolescência via fachada
def test_mark_obsolete_and_supersede_via_facade(tmp_path):
    system = make_system(tmp_path)
    first = system.remember(MemoryKind.KNOWLEDGE, "versão", "v1")
    system.mark_obsolete(MemoryKind.KNOWLEDGE, first.id, reason="desatualizada")

    second = system.supersede(MemoryKind.KNOWLEDGE, first.id, "versão", "v2")
    assert second.supersedes == first.id
    assert system.get(MemoryKind.KNOWLEDGE, first.id).status is RecordStatus.OBSOLETE
    assert "v2" in system.get(MemoryKind.KNOWLEDGE, second.id).content


# ---------------------------------------------------------------------- segurança
def test_no_secrets_in_any_memory_file(tmp_path):
    """Nenhum arquivo de memória contém segredos após operações diversas."""
    system = make_system(tmp_path)
    system.remember(MemoryKind.KNOWLEDGE, "config", "api_key=sk-memoria-secreta-99")
    system.remember(MemoryKind.PROJECT, "projeto", "chave AIzaProjetoChave1234567890ab")
    system.remember(MemoryKind.DECISION, "decisão", "password=super-secreto")
    system.conversation.add_message("user", "olá")  # conversa sem segredos

    for path in (tmp_path / "memory").glob("*.json"):
        content = path.read_text(encoding="utf-8")
        for segredo in ("sk-memoria-secreta-99", "AIzaProjetoChave1234567890ab",
                        "super-secreto"):
            assert segredo not in content, f"segredo em {path}"


def test_system_rejects_invalid_budget(tmp_path):
    with pytest.raises(ValueError):
        MemorySystem(tmp_path, max_context_records=0)
