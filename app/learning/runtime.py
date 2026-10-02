"""F26 Learning Runtime: persistent learning from explicit goals and normal use."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import Enum
import json
from pathlib import Path
from threading import RLock
from typing import Callable
from uuid import uuid4
from app.memory.sanitization import redact_secrets

class KnowledgeStatus(str,Enum):
    CANDIDATE="candidate"; VERIFIED="verified"; REJECTED="rejected"
class LearningSource(str,Enum):
    USER="user"; RESEARCH="research"; INTERACTION="interaction"; PRACTICE="practice"; VERIFICATION="verification"
@dataclass(frozen=True)
class KnowledgeItem:
    knowledge_id:str; topic:str; claim:str; source:LearningSource; confidence:float=.0
    status:KnowledgeStatus=KnowledgeStatus.CANDIDATE; evidence:tuple[str,...]=()
@dataclass(frozen=True)
class Experience:
    experience_id:str; topic:str; situation:str; outcome:str; success:bool; lesson:str=""; evidence:tuple[str,...]=()
@dataclass(frozen=True)
class Strategy:
    strategy_id:str; topic:str; trigger:str; approach:str; confidence:float=.0; evidence:tuple[str,...]=()
@dataclass(frozen=True)
class LearningGoal:
    goal_id:str; objective:str; topics:tuple[str,...]; status:str="active"; knowledge_ids:tuple[str,...]=()
@dataclass(frozen=True)
class LearningExtraction:
    knowledge:tuple[str,...]=(); experiences:tuple[tuple[str,str,bool,str],...]=(); strategies:tuple[tuple[str,str],...]=()
@dataclass(frozen=True)
class LearningSession:
    goal:LearningGoal; researched:int; practiced:int; verified:int; consolidated:int

class LearningStore:
    def __init__(self,path,max_items=10000,max_text=20000):
        if max_items<1 or max_text<256: raise ValueError("invalid learning store limits")
        self.path=Path(path); self.max_items=max_items; self.max_text=max_text; self._lock=RLock()
        self.data={"knowledge":{},"experiences":{},"strategies":{},"goals":{}}; self._load()
    def _load(self):
        if self.path.exists():
            raw=json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw,dict): raise ValueError("learning store must contain an object")
            for k in self.data:
                if not isinstance(raw.get(k,{}),dict): raise ValueError(f"invalid learning section: {k}")
                self.data[k]=raw.get(k,{})
            for key, value in self.data["knowledge"].items():
                if isinstance(value, dict):
                    value["source"] = LearningSource(value.get("source", LearningSource.RESEARCH.value))
                    value["status"] = KnowledgeStatus(value.get("status", KnowledgeStatus.CANDIDATE.value))
    def _safe(self,v):
        x,_=redact_secrets(str(v))
        if len(x)>self.max_text: raise ValueError("learning text exceeds configured limit")
        return x
    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True); tmp=self.path.with_suffix(self.path.suffix+".tmp")
        tmp.write_text(json.dumps(self.data,ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8"); tmp.replace(self.path)
    def _bound(self,k):
        while len(self.data[k])>self.max_items: del self.data[k][sorted(self.data[k])[0]]
    def add_knowledge(self,x):
        if not x.knowledge_id.strip() or not x.topic.strip() or not x.claim.strip(): raise ValueError("knowledge identity/topic/claim required")
        if not 0<=x.confidence<=1: raise ValueError("confidence must be between 0 and 1")
        x=KnowledgeItem(x.knowledge_id,self._safe(x.topic),self._safe(x.claim),x.source,x.confidence,x.status,tuple(self._safe(e) for e in x.evidence))
        with self._lock: self.data["knowledge"][x.knowledge_id]=asdict(x); self._bound("knowledge"); self._save()
        return x
    def verify(self,i,evidence,confidence=1.0):
        if not 0<=confidence<=1: raise ValueError("confidence must be between 0 and 1")
        with self._lock:
            x=KnowledgeItem(**self.data["knowledge"][i]); y=KnowledgeItem(x.knowledge_id,x.topic,x.claim,LearningSource.VERIFICATION,confidence,KnowledgeStatus.VERIFIED,tuple(self._safe(e) for e in evidence))
            self.data["knowledge"][i]=asdict(y); self._save(); return y
    def reject(self,i,reason):
        with self._lock:
            x=KnowledgeItem(**self.data["knowledge"][i]); y=KnowledgeItem(x.knowledge_id,x.topic,x.claim,x.source,x.confidence,KnowledgeStatus.REJECTED,x.evidence+(self._safe(reason),))
            self.data["knowledge"][i]=asdict(y); self._save(); return y
    def add_experience(self,x):
        if not x.experience_id.strip() or not x.topic.strip() or not x.situation.strip(): raise ValueError("experience identity/topic/situation required")
        x=Experience(x.experience_id,self._safe(x.topic),self._safe(x.situation),self._safe(x.outcome),bool(x.success),self._safe(x.lesson),tuple(self._safe(e) for e in x.evidence))
        with self._lock: self.data["experiences"][x.experience_id]=asdict(x); self._bound("experiences"); self._save()
        return x
    def add_strategy(self,x):
        if not x.strategy_id.strip() or not x.topic.strip() or not x.trigger.strip() or not x.approach.strip(): raise ValueError("strategy fields required")
        if not 0<=x.confidence<=1: raise ValueError("confidence must be between 0 and 1")
        x=Strategy(x.strategy_id,self._safe(x.topic),self._safe(x.trigger),self._safe(x.approach),x.confidence,tuple(self._safe(e) for e in x.evidence))
        with self._lock: self.data["strategies"][x.strategy_id]=asdict(x); self._bound("strategies"); self._save()
        return x
    def search(self,q,verified_only=False,limit=20):
        if not q.strip() or limit<1: return ()
        terms=q.lower().split(); out=[]
        for raw in self.data["knowledge"].values():
            x=KnowledgeItem(**raw); hay=f"{x.topic} {x.claim}".lower()
            if all(t in hay for t in terms) and (not verified_only or x.status==KnowledgeStatus.VERIFIED): out.append(x)
        return tuple(out[:limit])
    def counts(self): return {k:len(v) for k,v in self.data.items()}

class LearningRuntime:
    """Orchestrates learning; research/practice/verification are explicit dependencies."""
    def __init__(self,store): self.store=store
    def _id(self,p): return f"{p}-{uuid4().hex}"
    def start_goal(self,objective,topics=()):
        objective,_=redact_secrets(objective)
        if not objective.strip(): raise ValueError("learning objective is required")
        g=LearningGoal(self._id("LEARN"),objective,tuple(dict.fromkeys(t.strip() for t in topics if t.strip())))
        self.store.data["goals"][g.goal_id]=asdict(g); self.store._bound("goals"); self.store._save(); return g
    def learn_explicit(self,goal,research:Callable|None=None,practice:Callable|None=None,verify:Callable|None=None,max_items=100):
        if max_items<1: raise ValueError("max_items must be positive")
        ids=[]; practiced=verified=0
        if research:
            for topic,claim in tuple(research(goal))[:max_items]:
                ids.append(self.store.add_knowledge(KnowledgeItem(self._id("KNOW"),topic,claim,LearningSource.RESEARCH,.25)).knowledge_id)
        for i in ids:
            x=KnowledgeItem(**self.store.data["knowledge"][i])
            if practice:
                ok,e=practice(x); practiced+=1
                if not ok: self.store.reject(i,e or "practice failed"); continue
            if verify:
                ok,e=verify(x)
                if ok: self.store.verify(i,(e,),1.0); verified+=1
                else: self.store.reject(i,e or "verification failed")
        g=LearningGoal(goal.goal_id,goal.objective,goal.topics,"completed",tuple(ids))
        self.store.data["goals"][g.goal_id]=asdict(g); self.store._save()
        return LearningSession(g,len(ids),practiced,verified,verified)
    def ingest_research(self, objective, findings, *, max_items=20):
        """Persist bounded Web research as reusable candidate knowledge.

        Research is evidence, not automatic truth: imported findings remain
        CANDIDATE until a governed verification step promotes them to VERIFIED.
        """
        if max_items < 1:
            raise ValueError("max_items must be positive")
        objective, _ = redact_secrets(str(objective))
        if not objective.strip():
            raise ValueError("learning objective is required")
        goal = self.start_goal(objective)
        saved = []
        for finding in tuple(findings)[:max_items]:
            if not isinstance(finding, dict):
                continue
            query = str(finding.get("query") or objective).strip()
            claim = str(finding.get("claim") or finding.get("text") or finding.get("snippet") or "").strip()
            if not claim:
                continue
            sources = finding.get("evidence") or finding.get("sources") or ()
            if isinstance(sources, str):
                sources = (sources,)
            evidence = tuple(str(x) for x in sources if str(x).strip())
            item = KnowledgeItem(
                self._id("KNOW"),
                query or objective,
                claim,
                LearningSource.RESEARCH,
                float(finding.get("confidence", 0.25)),
                KnowledgeStatus.CANDIDATE,
                evidence,
            )
            saved.append(self.store.add_knowledge(item))
        completed = LearningGoal(
            goal.goal_id,
            goal.objective,
            goal.topics,
            "researched",
            tuple(x.knowledge_id for x in saved),
        )
        self.store.data["goals"][completed.goal_id] = asdict(completed)
        self.store._save()
        return completed, tuple(saved)

    def recent_knowledge(self, limit=10, *, verified_only=False):
        if limit < 1:
            return ()
        items = [KnowledgeItem(**raw) for raw in self.store.data["knowledge"].values()]
        if verified_only:
            items = [x for x in items if x.status == KnowledgeStatus.VERIFIED]
        items.sort(key=lambda x: x.knowledge_id, reverse=True)
        return tuple(items[:limit])

    def learn_from_use(self,topic,situation,outcome,success,lesson="",strategy=None,evidence=()):
        e=tuple(evidence); x=self.store.add_experience(Experience(self._id("EXP"),topic,situation,outcome,success,lesson,e))
        if strategy:
            t,a=strategy; self.store.add_strategy(Strategy(self._id("STRAT"),topic,t,a,1.0 if success else .25,e))
        return x
    def learn_from_interaction(self,extraction,topic):
        saved=tuple(self.store.add_knowledge(KnowledgeItem(self._id("KNOW"),topic,c,LearningSource.INTERACTION,.25)) for c in extraction.knowledge)
        for s,o,ok,l in extraction.experiences: self.learn_from_use(topic,s,o,ok,l)
        for t,a in extraction.strategies: self.store.add_strategy(Strategy(self._id("STRAT"),topic,t,a,.25))
        return saved
    def recall(self,q,verified_only=True,limit=10): return self.store.search(q,verified_only,limit)
