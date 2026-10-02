"""Autonomous mission supervisor for the Lumen Evolution System.

A mission is a durable high-level goal. Once created, Lumen resumes it on
startup and waits for the real Unreal MCP endpoint to become available. The
planner may research, evolve the Lumen codebase, run bounded tests, inspect
Unreal, or invoke an advertised Unreal MCP tool.

The mission layer does not bypass the existing security model: Unreal MCP is
loopback-only, calls are bounded and audited, and the existing
ComputerControl/permission/checkpoint stack remains the authority for
physical mouse/keyboard actions.
"""
from __future__ import annotations

import argparse
import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from app.evolution.autonomous_loop import AutonomousEvolutionLoop, EvolutionConfig, LocalOllama
from app.unreal.mcp import UnrealMCPClient, UnrealMCPError
from app.learning.runtime import LearningRuntime, LearningStore
from app.evolution.autonomous_progress import AutonomousProgressController

LOGGER = logging.getLogger("lumen.autonomous_mission")


@dataclass
class MissionRecord:
    mission_id: str
    goal: str
    project_root: str
    status: str = "WAITING_UNREAL"
    cycle: int = 0
    last_action: str = ""
    last_error: str = ""
    phase: str = "WAITING_UNREAL"
    last_result: str = ""
    last_started_at: float = 0.0
    last_duration_seconds: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0

    def validate(self) -> None:
        if not self.mission_id.strip() or not self.goal.strip():
            raise ValueError("mission_id and goal are required")
        if not self.project_root.strip():
            raise ValueError("project_root is required")
        if self.cycle < 0:
            raise ValueError("cycle must be >= 0")


class MissionStore:
    """Atomic, single-file persistence for the one active mission."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.event_path = self.path.with_name("evolution_log.jsonl")
        self._save_lock = threading.RLock()

    def event(self, event: str, record: MissionRecord, **details: Any) -> None:
        payload = {
            "timestamp": time.time(),
            "event": event,
            "mission_id": record.mission_id,
            "cycle": record.cycle,
            "status": record.status,
            "phase": record.phase,
            **details,
        }
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        with self.event_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def load(self) -> MissionRecord | None:
        if not self.path.exists():
            return None
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("mission store must contain an object")
        record = MissionRecord(**raw)
        record.validate()
        return record

    def save(self, record: MissionRecord) -> None:
        record.validate()
        with self._save_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(asdict(record), ensure_ascii=False, sort_keys=True, indent=2)
            tmp = self.path.with_name(f"{self.path.name}.{threading.get_ident()}.tmp")
            for attempt in range(6):
                try:
                    tmp.write_text(payload, encoding="utf-8")
                    tmp.replace(self.path)
                    return
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(0.05 * (attempt + 1))
            raise RuntimeError("mission store save failed unexpectedly")


class UnrealReadiness:
    """Read-only readiness probe for the real local Unreal MCP server."""

    def __init__(self, client: UnrealMCPClient | None = None) -> None:
        self.client = client or UnrealMCPClient(timeout=2.0)

    def probe(self) -> tuple[bool, dict[str, Any]]:
        try:
            tools = self.client.list_tools()
            if tools.is_error:
                return False, {"error": tools.error}
            return True, {"mcp": "ready", "tools": tools.result}
        except Exception as exc:
            # Unreal Editor restarts invalidate the old MCP session. Forget it
            # so the next poll performs a fresh initialize/handshake.
            reset = getattr(self.client, "reset_session", None)
            if callable(reset):
                reset()
            return False, {"error": str(exc)}


class AutonomousUnrealBroker:
    """Bounded broker for advertised Unreal MCP tools.

    The broker deliberately accepts only tools returned by the connected
    server. It never accepts a raw HTTP URL, shell command, or non-MCP target.
    """

    def __init__(self, client: UnrealMCPClient | None = None, *, max_calls: int = 20) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be >= 1")
        self.client = client or UnrealMCPClient(timeout=15.0)
        self.max_calls = max_calls
        self.calls = 0

    def list_toolsets(self) -> Any:
        response = self.client.list_toolsets()
        if response.is_error:
            raise UnrealMCPError(str(response.error))
        return response.result

    def describe_toolset(self, toolset_name: str) -> Any:
        response = self.client.describe_toolset(toolset_name)
        if response.is_error:
            raise UnrealMCPError(str(response.error))
        return response.result

    def call(self, toolset_name: str, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        if self.calls >= self.max_calls:
            raise RuntimeError("autonomous Unreal call budget exhausted")
        if not toolset_name.strip() or not tool_name.strip():
            raise ValueError("toolset_name and tool_name are required")
        if arguments is not None and not isinstance(arguments, dict):
            raise TypeError("arguments must be an object")
        toolsets = self.list_toolsets()
        serialized = json.dumps(toolsets, ensure_ascii=False)
        if toolset_name not in serialized:
            raise PermissionError("toolset is not advertised by the connected Unreal server")
        response = self.client.call_toolset_tool(toolset_name, tool_name, arguments or {})
        self.calls += 1
        if response.is_error:
            raise UnrealMCPError(str(response.error))
        return response.result


class AutonomousMissionEngine:
    """Closed-loop mission executor driven by the local Ollama provider."""

    SYSTEM = """You are the Lumen autonomous mission planner.
Return ONLY JSON:
{"action":"research|list_toolsets|describe_toolset|evolve_code|observe_unreal|unreal_call|done",
 "reason":"...",
 "query":"...",
 "toolset_name":"...",
 "tool_name":"...",
 "arguments":{}}
Choose exactly one next action. Prefer reusable capabilities over one-off hacks.
Never request shell commands through unreal_call. Use evolve_code for Lumen source
changes and its bounded test/rollback pipeline. Use observe_unreal before an
unreal_call when the current UI state is unknown. Mark done only when the goal is
actually verified."""

    def __init__(
        self,
        *,
        record: MissionRecord,
        store: MissionStore,
        repo: Path,
        model: str,
        ollama_url: str,
        broker: AutonomousUnrealBroker,
        decision_provider: Callable[[str, str], dict[str, Any]] | None = None,
        learning_store_path: str | Path | None = None,
    ) -> None:
        self.record = record
        self.store = store
        self.repo = repo
        self.ollama = LocalOllama(ollama_url, model)
        self.broker = broker
        self.decision_provider = decision_provider
        learning_path = Path(learning_store_path) if learning_store_path else repo / "data" / "learning" / "knowledge.json"
        self.learning = LearningRuntime(LearningStore(learning_path))
        self.progress = AutonomousProgressController(
            self.store.path.parent / "autonomous_progress.json",
            record.mission_id,
            repeat_limit=2,
            max_recovery_attempts=3,
            stagnation_limit=3,
        )
        self._evolution = AutonomousEvolutionLoop(
            EvolutionConfig(
                repo=repo,
                goal=record.goal,
                model=model,
                ollama_url=ollama_url,
                branch=self._current_branch(),
                max_cycles=1,
            )
        )

    def _current_branch(self) -> str:
        from app.tools.terminal import run_git_command
        result = run_git_command(self.repo, ("branch", "--show-current"))
        branch = result.stdout.strip()
        if not branch:
            raise RuntimeError("cannot determine current git branch")
        return branch

    @staticmethod
    def _toolset_names(toolsets: Any) -> tuple[str, ...]:
        """Extract advertised toolset names from Unreal MCP text/envelopes."""
        names: list[str] = []

        def add(value: Any) -> None:
            if isinstance(value, str) and value.strip() and value.strip() not in names:
                names.append(value.strip())

        def visit(value: Any) -> None:
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    return
                if text.startswith(("{", "[", "```")):
                    cleaned = text
                    if cleaned.startswith("```"):
                        lines = cleaned.splitlines()
                        if lines and lines[0].strip().startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].strip() == "```":
                            lines = lines[:-1]
                        cleaned = "\n".join(lines).strip()
                    try:
                        decoded = json.loads(cleaned)
                    except json.JSONDecodeError:
                        decoded = None
                    if decoded is not None:
                        visit(decoded)
                        return
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("- ") and ":" in line:
                        candidate = line[2:].split(":", 1)[0].strip()
                        if "." in candidate:
                            add(candidate)
                return
            if isinstance(value, dict):
                for key in ("toolset_name", "toolsetName", "toolset", "toolset_id"):
                    add(value.get(key))
                for key in ("toolsets", "toolset_list", "toolsetList"):
                    if key in value:
                        visit(value[key])
                if isinstance(value.get("name"), str):
                    add(value["name"])
                for key in ("content", "text", "data", "result", "structuredContent",
                            "structured_content", "output", "payload", "response", "items", "value"):
                    if key in value:
                        visit(value[key])
                return
            if isinstance(value, (list, tuple)):
                for item in value:
                    visit(item)

        visit(toolsets)
        return tuple(names)

    def _progress_context(self) -> dict[str, Any]:
        return {
            **self.progress.planner_context(),
            "can_observe": True,
            "can_research": True,
            "can_evolve_code": True,
            "can_unreal_call": True,
            "capability_gap": bool(self.progress.state.current_gap),
        }

    def decide(self, context: str) -> dict[str, Any]:
        self.record.phase = "PLANNING"
        self.record.last_started_at = time.time()
        self.record.updated_at = self.record.last_started_at
        self.store.save(self.record)
        model_name = getattr(getattr(self, "ollama", None), "model", "unknown")
        self.store.event("decision_started", self.record, model=model_name)

        if self.decision_provider is not None:
            decision = self.decision_provider(self.record.goal, context)
        else:
            response = self.ollama.chat(self.SYSTEM, context, think=False, json_format=True)
            try:
                decision = json.loads(response)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Ollama returned invalid autonomous mission JSON") from exc

        if not isinstance(decision, dict):
            raise RuntimeError("autonomous mission decision must be an object")

        action = decision.get("action")
        allowed = {"research", "list_toolsets", "describe_toolset", "evolve_code", "observe_unreal", "unreal_call", "done"}

        # Planner output is untrusted model data. If Ollama returns a missing
        # or unsupported action, let the deterministic progress controller
        # recover instead of crashing the autonomous loop.
        proposed = action if isinstance(action, str) and action in allowed else ""
        progress = self.progress.recommend(tuple(allowed), context=self._progress_context())
        proposed_payload = {
            "toolset_name": decision.get("toolset_name"),
            "tool_name": decision.get("tool_name"),
            "query": decision.get("query"),
            "arguments": decision.get("arguments"),
        }
        proposed_allowed = bool(proposed) and self.progress.admit(
            proposed,
            self.progress.fingerprint(proposed, proposed_payload),
        )
        guarded = dict(decision)
        if progress.action != proposed or not proposed_allowed:
            guarded["action"] = progress.action
            guarded["reason"] = f"Progress guard: {progress.reason}; planner proposed {action!r}."
            self.store.event(
                "decision_guarded",
                self.record,
                proposed_action=proposed,
                selected_action=progress.action,
                reason=progress.reason,
            )

        # A describe step is only executable when it carries the concrete
        # toolset selected by the progress controller. This must also be
        # repaired when the planner independently proposed describe_toolset
        # and the guard therefore did not override the action.
        if guarded.get("action") == "describe_toolset" and not str(guarded.get("toolset_name") or "").strip():
            candidates = [
                name for name in self.progress.state.known_toolsets
                if name not in self.progress.state.described_toolsets
            ]
            if candidates:
                guarded["toolset_name"] = candidates[0]
            elif self.progress.state.known_toolsets:
                guarded["action"] = "observe_unreal"
                guarded["reason"] = "Progress guard rejected describe_toolset because every known toolset is already described."
            else:
                guarded["action"] = "list_toolsets"
                guarded["reason"] = "Progress guard rejected describe_toolset because no toolset inventory is available."
        return guarded

    def context(self, readiness: dict[str, Any]) -> str:
        toolsets = ""
        try:
            toolsets = json.dumps(self.broker.list_toolsets(), ensure_ascii=False)[:24000]
        except Exception as exc:
            toolsets = json.dumps({"error": str(exc)})
        return json.dumps(
            {
                "mission": asdict(self.record),
                "unreal_readiness": readiness,
                "unreal_toolsets": toolsets,
                "learned_knowledge": [
                    {
                        "knowledge_id": item.knowledge_id,
                        "topic": item.topic,
                        "claim": item.claim,
                        "status": item.status.value,
                        "evidence": item.evidence,
                    }
                    for item in self.learning.recent_knowledge(limit=12)
                ],
                "learning_counts": self.learning.store.counts(),
                "autonomous_progress": self.progress.planner_context(),
                "instruction": "Continue the mission; reuse persisted research knowledge when relevant. Do not treat candidate knowledge as verified truth. Do not stop merely because a capability is missing: research it, persist the evidence, then build the missing capability in Lumen and retry.",
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def step(self, readiness: dict[str, Any]) -> str:
        decision = self.decide(self.context(readiness))
        action = str(decision["action"])
        self.record.last_action = action
        self.record.phase = action.upper()
        self.record.updated_at = time.time()
        self.record.last_duration_seconds = max(0.0, self.record.updated_at - self.record.last_started_at)
        self.store.event("decision", self.record, action=action, reason=str(decision.get("reason") or ""), query=str(decision.get("query") or ""))

        if action == "done":
            self.record.status = "COMPLETED"
            self.record.phase = "COMPLETED"
            self.record.last_result = "verified_done"
            self.store.save(self.record)
            self.store.event("mission_completed", self.record)
            return "done"

        if action == "list_toolsets":
            result = self.broker.list_toolsets()
            names = self._toolset_names(result)
            previous = set(self.progress.state.known_toolsets)
            self.progress.record(
                action="list_toolsets",
                result="toolsets_listed",
                success=True,
                new_information=bool(set(names) - previous),
                details={"toolsets": names},
            )
            self.record.status = "EVOLVING"
            self.record.phase = "LIST_TOOLSETS"
            self.record.last_result = "toolsets_listed"
            self.store.save(self.record)
            self.store.event(
                "action_completed",
                self.record,
                action="list_toolsets",
                result="ok",
                toolset_count=len(names),
                toolsets=names,
            )
            return "list_toolsets"

        if action == "describe_toolset":
            toolset_name = str(decision.get("toolset_name") or "").strip()

            if not toolset_name:
                raise ValueError(
                    "describe_toolset requires toolset_name"
                )

            result = self.broker.describe_toolset(toolset_name)

            if toolset_name not in self.progress.state.described_toolsets:
                self.progress.state.described_toolsets.append(toolset_name)
            self.progress.record(
                action="describe_toolset",
                result="toolset_described",
                success=True,
                new_information=True,
                details={"toolset": toolset_name},
            )
            self.record.status = "EVOLVING"
            self.record.phase = "DESCRIBE_TOOLSET"
            self.record.last_result = "toolset_described"
            self.store.save(self.record)
            self.store.event(
                "action_completed",
                self.record,
                action="describe_toolset",
                result="ok",
                toolset=toolset_name,
            )
            return "describe_toolset"

        if action == "research":
            from app.web.tools import WebResearchTool
            query = str(decision.get("query") or self.record.goal)
            result = WebResearchTool().run(
                query=query,
                max_results=5,
                max_sources=3,
            )
            if not result.ok:
                raise RuntimeError(result.error or "web research failed")
            payload = result.data if isinstance(result.data, dict) else {}
            findings = []
            for source in payload.get("sources", []):
                if not isinstance(source, dict):
                    continue
                claim = source.get("text") or source.get("snippet") or ""
                if not str(claim).strip():
                    continue
                findings.append(
                    {
                        "query": query,
                        "claim": str(claim),
                        "evidence": tuple(
                            x
                            for x in (source.get("url"), source.get("final_url"))
                            if isinstance(x, str) and x.strip()
                        ),
                        "confidence": 0.25,
                    }
                )
            _, learned = self.learning.ingest_research(
                query,
                findings,
                max_items=5,
            )
            research_text = f"{query} {decision.get('reason') or ''}".lower()
            gap = ""
            if learned and any(token in research_text for token in ("missing", "capability", "tool", "cannot", "need", "required")):
                gap = "Required Unreal/Lumen capability identified by research: " + query
            self.progress.record(
                action="research",
                result=f"knowledge={len(learned)}",
                success=True,
                new_information=bool(learned),
                research_finding=query,
                gap=gap or None,
                details={"knowledge_items": len(learned)},
            )
            self.record.status = "EVOLVING"
            self.record.phase = "RESEARCH"
            self.record.last_result = f"research_ok:knowledge={len(learned)}"
            self.store.save(self.record)
            self.store.event("action_completed", self.record, action="research", result="ok")
            return "research"

        if action == "evolve_code":
            result = self._evolution.cycle(self.record.cycle + 1)
            if result in {"blocked", "rolled_back"}:
                raise RuntimeError(f"code evolution did not produce a verified change: {result}")
            self.record.cycle += 1
            self.progress.record(
                action="evolve_code",
                result=str(result),
                success=True,
                new_information=True,
                capability=self.progress.state.current_gap or "lumen_autonomous_evolution",
                details={"evolution_result": str(result)},
            )
            self.record.status = "EVOLVING"
            self.record.phase = "EVOLVE_CODE"
            self.record.last_result = str(result)
            self.store.save(self.record)
            self.store.event("action_completed", self.record, action="evolve_code", result=str(result))
            return "evolve_code"

        if action == "observe_unreal":
            response = self.broker.client.call_toolset_tool(
                "SlateInspectorToolset.SlateInspectorToolset",
                "Snapshot",
                {"ref": "", "maxDepth": 30, "bIncludeSourceLocations": False},
            )
            if response.is_error:
                raise UnrealMCPError(str(response.error))
            self.progress.record(
                action="observe_unreal",
                result="snapshot_ok",
                success=True,
                new_information=True,
                observation="Unreal Slate snapshot acquired",
            )
            self.record.status = "EVOLVING"
            self.record.phase = "OBSERVE_UNREAL"
            self.record.last_result = "snapshot_ok"
            self.store.save(self.record)
            self.store.event("action_completed", self.record, action="observe_unreal", result="ok")
            return "observe_unreal"

        toolset_name = str(decision.get("toolset_name") or "").strip()
        tool_name = str(decision.get("tool_name") or "").strip()
        arguments = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}

        self.store.event(
            "action_started",
            self.record,
            action="unreal_call",
            toolset=toolset_name,
            tool=tool_name,
            argument_keys=sorted(str(key) for key in arguments),
        )

        try:
            self.broker.call(toolset_name, tool_name, arguments)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.progress.record(
                action="unreal_call",
                result="unreal_call_failed",
                success=False,
                new_information=False,
                error=error,
                gap=(
                    f"Unreal capability failed: {toolset_name}.{tool_name}. "
                    "Research the failure and evolve or replace the capability before retrying."
                ),
                details={"toolset": toolset_name, "tool": tool_name},
            )
            self.record.status = "EVOLVING"
            self.record.phase = "UNREAL_CALL"
            self.record.last_result = "unreal_call_failed"
            self.record.last_error = error
            self.record.updated_at = time.time()
            self.record.last_duration_seconds = max(0.0, self.record.updated_at - self.record.last_started_at)
            self.store.save(self.record)
            self.store.event(
                "action_failed",
                self.record,
                action="unreal_call",
                error=error,
                toolset=toolset_name,
                tool=tool_name,
            )
            return "unreal_call_failed"

        self.progress.record(
            action="unreal_call",
            result="unreal_call_ok",
            success=True,
            new_information=True,
            details={"toolset": toolset_name, "tool": tool_name},
        )
        self.record.status = "EVOLVING"
        self.record.phase = "UNREAL_CALL"
        self.record.last_result = "unreal_call_ok"
        self.record.last_error = ""
        self.record.updated_at = time.time()
        self.record.last_duration_seconds = max(0.0, self.record.updated_at - self.record.last_started_at)
        self.store.save(self.record)
        self.store.event(
            "action_completed",
            self.record,
            action="unreal_call",
            result="ok",
            toolset=toolset_name,
            tool=tool_name,
        )
        return "unreal_call"


class AutonomousMissionSupervisor:
    """Background watcher: resume the saved mission when Unreal becomes ready."""

    def __init__(
        self,
        *,
        repo: Path,
        data_dir: Path,
        model: str,
        ollama_url: str,
        poll_seconds: float = 5.0,
        broker: AutonomousUnrealBroker | None = None,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be > 0")
        self.store = MissionStore(data_dir / "evolution" / "mission.json")
        self.repo = repo
        self.model = model
        self.ollama_url = ollama_url
        self.poll_seconds = poll_seconds
        self.probe = UnrealReadiness(broker.client if broker else None)
        self.broker = broker or AutonomousUnrealBroker()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if self.store.load() is None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="lumen-autonomous-mission",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=min(2.0, self.poll_seconds + 0.5))

    def _run(self) -> None:
        while not self._stop.is_set():
            record = self.store.load()
            if record is None or record.status == "COMPLETED":
                return
            ready, details = self.probe.probe()
            if not ready:
                record.status = "WAITING_UNREAL"
                record.last_error = str(details.get("error") or "")
                record.updated_at = time.time()
                self.store.save(record)
                self._stop.wait(self.poll_seconds)
                continue
            try:
                record.status = "EVOLVING"
                record.last_error = ""
                self.store.save(record)
                engine = AutonomousMissionEngine(
                    record=record,
                    store=self.store,
                    repo=self.repo,
                    model=self.model,
                    ollama_url=self.ollama_url,
                    broker=self.broker,
                    learning_store_path=self.store.path.parent.parent / "learning" / "knowledge.json",
                )
                engine.step(details)
            except Exception as exc:
                record.status = "BLOCKED"
                record.last_error = f"{type(exc).__name__}: {exc}"
                record.updated_at = time.time()
                self.store.save(record)
                LOGGER.exception("Autonomous mission paused: %s", exc)
                self._stop.wait(self.poll_seconds)
                continue
            self._stop.wait(0.25)

    @property
    def mission_path(self) -> Path:
        return self.store.path


def create_mission(path: str | Path, *, goal: str, project_root: str | Path) -> MissionRecord:
    now = time.time()
    record = MissionRecord(
        mission_id=f"LUMEN-MISSION-{uuid.uuid4().hex[:12]}",
        goal=goal.strip(),
        project_root=str(Path(project_root).expanduser().resolve()),
        created_at=now,
        updated_at=now,
    )
    record.validate()
    MissionStore(path).save(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Create/resume the Lumen autonomous mission.")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--goal", required=True)
    init.add_argument("--project-root", required=True)
    init.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    if args.command == "init":
        record = create_mission(
            Path(args.data_dir) / "evolution" / "mission.json",
            goal=args.goal,
            project_root=args.project_root,
        )
        print(json.dumps(asdict(record), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
