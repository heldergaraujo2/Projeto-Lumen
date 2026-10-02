from __future__ import annotations
import json, os, re, shutil, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from app.tools.run_pytest import PytestCommandTimeout, run_pytest_command
from app.tools.terminal import run_git_command

class EvolutionLoopError(RuntimeError):
    pass

@dataclass(frozen=True)
class EvolutionConfig:
    repo: Path
    goal: str
    model: str = "qwen2.5-coder:7b-instruct-q8_0"
    ollama_url: str = "http://127.0.0.1:11434"
    branch: str = "feature/web-research-agent"
    max_attempts_per_cycle: int = 3
    max_cycles: int = 0
    fast_test: tuple[str, ...] = ("python", "-m", "pytest", "tests/test_autonomous_evolution.py", "-q")
    full_test: tuple[str, ...] = ("python", "-m", "pytest", "-q")
    test_timeout: int = 900
    def validate(self):
        if not self.repo.is_dir() or not self.goal.strip():
            raise EvolutionLoopError("repo and goal are required")
        if self.max_attempts_per_cycle < 1 or self.max_cycles < 0:
            raise EvolutionLoopError("invalid limits")

class GitGuard:
    def __init__(self, repo): self.repo=repo
    def run(self,*args,timeout=120):
        return run_git_command(self.repo, args, timeout=timeout)
    def branch(self):
        r=self.run("branch","--show-current")
        if r.returncode: raise EvolutionLoopError(r.stderr.strip())
        return r.stdout.strip()
    def head(self):
        r=self.run("rev-parse","HEAD")
        if r.returncode: raise EvolutionLoopError(r.stderr.strip())
        return r.stdout.strip()
    def status(self):
        r=self.run("status","--porcelain")
        if r.returncode: raise EvolutionLoopError(r.stderr.strip())
        return [x for x in r.stdout.splitlines() if x]
    def tracked_dirty(self):
        return any(not x.startswith("?? ") for x in self.status())
    def changed_since(self,sha):
        r=self.run("diff","--name-only",sha,"--")
        if r.returncode: raise EvolutionLoopError(r.stderr.strip())
        return [x for x in r.stdout.splitlines() if x]
    def commit(self,paths,message):
        if not paths: raise EvolutionLoopError("no changes")
        r=self.run("add","--",*paths)
        if r.returncode: raise EvolutionLoopError(r.stderr.strip())
        r=self.run("commit","-m",message[:120])
        if r.returncode: raise EvolutionLoopError(r.stderr.strip())
        return self.head()
    def rollback(self,sha,paths):
        if paths:
            r=self.run("restore","--source",sha,"--",*paths)
            if r.returncode: raise EvolutionLoopError(r.stderr.strip())

class LocalOllama:
    def __init__(self,url,model): self.url=url.rstrip("/"); self.model=model
    def health(self):
        try:
            with urlopen(Request(self.url+"/api/tags"),timeout=10) as r: return 200 <= r.status < 300
        except OSError: return False
    def chat(self,system,prompt,*,think=False,json_format=False):
        payload={"model":self.model,"stream":False,"messages":[{"role":"system","content":system},{"role":"user","content":prompt}],"think":think}
        if json_format: payload["format"]="json"
        body=json.dumps(payload).encode()
        req=Request(self.url+"/api/chat",data=body,headers={"Content-Type":"application/json"},method="POST")
        with urlopen(req,timeout=300) as r: data=json.loads(r.read().decode())
        text=(data.get("message") or {}).get("content","")
        if not isinstance(text,str) or not text.strip(): raise EvolutionLoopError("empty Ollama response")
        return text

def extract_json(text:str)->dict[str,Any]:
    fence=chr(96)*3
    text=text.strip().replace(fence+"json","").replace(fence,"").strip()
    try: value=json.loads(text)
    except json.JSONDecodeError as exc: raise EvolutionLoopError("model response is not JSON") from exc
    if not isinstance(value,dict): raise EvolutionLoopError("model response must be object")
    return value

class AutonomousEvolutionLoop:
    SYSTEM=("You are Lumen's autonomous software evolution engineer. "
            "Return ONLY JSON with summary, changes and commit_message. "
            "Each change has path and complete file content. "
            "Never return shell commands. Prefer generic reusable capabilities. "
            "Add regression tests for every new capability.")
    PROTECTED={".git",".env",".env.example","secrets.py","permissions.py","policy.py","audit.py","checkpoint.py"}
    CONTEXT=("app/unreal/agent.py","app/unreal/models.py","app/unreal/integration.py","app/unreal/mcp.py","tests/test_unreal_agent.py","tests/test_unreal_execution.py","tests/test_unreal_mcp.py")
    def __init__(self,config):
        config.validate(); self.config=config; self.git=GitGuard(config.repo); self.model=LocalOllama(config.ollama_url,config.model)
        self.log=config.repo/"data"/"evolution"/"overnight.jsonl"; self.log.parent.mkdir(parents=True,exist_ok=True)
    def context(self):
        out=[]
        for rel in self.CONTEXT:
            p=self.config.repo/rel
            if p.is_file(): out.append("\n===== "+rel+" =====\n"+p.read_text(encoding="utf-8",errors="replace")[:12000])
        return "".join(out)
    def prompt(self,cycle,failure=""):
        return ("Goal:\n"+self.config.goal+"\nCycle: "+str(cycle)+"\nBranch: "+self.git.branch()+
                "\nHEAD: "+self.git.head()+"\nPrevious failure:\n"+(failure or "none")+
                "\nRepository context:\n"+self.context())
    def apply(self,changes,baseline):
        created=[]; protected={".git",".env",".env.example","secrets.py","permissions.py","policy.py","audit.py","checkpoint.py"}
        preexisting={x[3:] for x in baseline if x.startswith("?? ")}
        for item in changes:
            if not isinstance(item,dict): raise EvolutionLoopError("invalid change")
            raw=str(item.get("path","")).replace("\\","/"); content=item.get("content"); p=Path(raw)
            if not raw or p.is_absolute() or ".." in p.parts or not isinstance(content,str): raise EvolutionLoopError("invalid path/content")
            if any(part.lower() in protected for part in p.parts): raise EvolutionLoopError("protected path")
            if raw in preexisting: raise EvolutionLoopError("pre-existing untracked file")
            target=(self.config.repo/p).resolve()
            if self.config.repo.resolve() not in target.parents: raise EvolutionLoopError("path escapes repo")
            if len(content.encode())>250000: raise EvolutionLoopError("file too large")
            if not target.exists(): created.append(target)
            target.parent.mkdir(parents=True,exist_ok=True); target.write_text(content,encoding="utf-8")
        return created
    def run_tests(self,command):
        try:
            r=run_pytest_command(self.config.repo, tuple(command), timeout=self.config.test_timeout)
        except PytestCommandTimeout as exc:
            return False,str(exc)
        return r.returncode==0,(r.stdout+"\n"+r.stderr)[-16000:]
    def cycle(self,number):
        if self.git.branch()!=self.config.branch: raise EvolutionLoopError("wrong branch")
        if self.git.tracked_dirty(): raise EvolutionLoopError("tracked changes exist")
        checkpoint=self.git.head(); baseline=self.git.status(); failure=""
        for attempt in range(1,self.config.max_attempts_per_cycle+1):
            created=[]
            try:
                doc=extract_json(self.model.chat(self.SYSTEM,self.prompt(number,failure)))
                changes=doc.get("changes",[])
                if not changes: return "blocked"
                created=self.apply(changes,baseline)
                ok,out=self.run_tests(self.config.fast_test)
                if not ok:
                    failure="FAST TEST FAILURE:\n"+out; self.git.rollback(checkpoint,self.git.changed_since(checkpoint))
                    for p in created:
                        if p.exists(): p.unlink()
                    continue
                ok,out=self.run_tests(self.config.full_test)
                if not ok:
                    failure="FULL TEST FAILURE:\n"+out; self.git.rollback(checkpoint,self.git.changed_since(checkpoint))
                    for p in created:
                        if p.exists(): p.unlink()
                    continue
                return self.git.commit(self.git.changed_since(checkpoint),str(doc.get("commit_message") or "evolution cycle"))
            except Exception as exc:
                failure=type(exc).__name__+": "+str(exc)
                self.git.rollback(checkpoint,self.git.changed_since(checkpoint))
        return "rolled_back"
    def run_forever(self):
        cycle=1
        while self.config.max_cycles==0 or cycle<=self.config.max_cycles:
            result=self.cycle(cycle); print("[LUMEN EVOLUTION] cycle",cycle,result,flush=True)
            if result in {"blocked","rolled_back"}: return
            cycle+=1
