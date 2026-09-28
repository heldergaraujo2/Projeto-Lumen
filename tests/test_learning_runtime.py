from pathlib import Path
from app.learning.runtime import LearningExtraction, LearningRuntime, KnowledgeStatus, LearningStore

def test_explicit_learning_persists_and_verifies(tmp_path: Path):
    rt=LearningRuntime(LearningStore(tmp_path/"learning.json"))
    goal=rt.start_goal("Aprender C++",("C++","templates"))
    s=rt.learn_explicit(goal,
        research=lambda _: (("C++","RAII manages resource lifetime"),("templates","templates enable generic programming")),
        practice=lambda x:(True,"compiled practice"),
        verify=lambda x:(True,"verified evidence"))
    assert (s.researched,s.practiced,s.verified,s.consolidated)==(2,2,2,2)
    assert len(rt.recall("RAII"))==1
    assert len(LearningRuntime(LearningStore(tmp_path/"learning.json")).recall("RAII"))==1

def test_unverified_knowledge_is_hidden_by_default(tmp_path):
    rt=LearningRuntime(LearningStore(tmp_path/"l.json")); g=rt.start_goal("test")
    rt.learn_explicit(g,research=lambda _: (("x","candidate fact"),))
    assert rt.recall("candidate fact")==()
    assert len(rt.recall("candidate fact",verified_only=False))==1

def test_failed_verification_rejects(tmp_path):
    rt=LearningRuntime(LearningStore(tmp_path/"l.json")); g=rt.start_goal("test")
    rt.learn_explicit(g,research=lambda _: (("x","bad fact"),),verify=lambda _: (False,"contradicted"))
    assert rt.recall("bad fact",False)[0].status==KnowledgeStatus.REJECTED

def test_use_learning_creates_experience_and_strategy(tmp_path):
    store=LearningStore(tmp_path/"l.json"); rt=LearningRuntime(store)
    x=rt.learn_from_use("C++","compile","build passed",True,"preset fixed build",("build","configure preset"),("build log",))
    assert x.success and store.counts()["experiences"]==1 and store.counts()["strategies"]==1

def test_interaction_learning_redacts_secrets(tmp_path):
    rt=LearningRuntime(LearningStore(tmp_path/"l.json"))
    x=rt.learn_from_interaction(LearningExtraction(knowledge=("api_key=SECRET123456789","RAII owns lifetime")),topic="C++")
    assert "***" in x[0].claim and "SECRET123456789" not in x[0].claim

def test_bounds_and_validation(tmp_path):
    store=LearningStore(tmp_path/"l.json",max_items=1); rt=LearningRuntime(store)
    rt.learn_from_interaction(LearningExtraction(knowledge=("one","two")),topic="x")
    assert store.counts()["knowledge"]==1
    try: LearningStore(tmp_path/"bad.json",max_items=0)
    except ValueError: pass
    else: raise AssertionError("invalid limit accepted")

def test_recall_requires_all_terms(tmp_path):
    rt=LearningRuntime(LearningStore(tmp_path/"l.json"))
    rt.learn_from_interaction(LearningExtraction(knowledge=("RAII resource lifetime","templates generic")),topic="C++")
    assert len(rt.recall("RAII lifetime",False))==1
    assert rt.recall("RAII unrelated",False)==()
