"""F31 Experience & Workflow Intelligence.

Observe -> understand -> record -> generalize -> store -> reuse -> adapt -> verify.
This module stores knowledge and evidence only. It never executes actions or grants
permissions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from pathlib import Path
from threading import RLock
from typing import Any

from app.memory.sanitization import redact_secrets
from app.workflows import WorkflowDefinition, WorkflowEvidence, WorkflowLearner, WorkflowMatcher, WorkflowOutcome, WorkflowRegistry, WorkflowRisk, WorkflowStep


class ExperienceOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ExperienceEvent:
    sequence: int
    action: str
    parameters: tuple[tuple[str, Any], ...] = ()
    observation_fingerprint: str = ""
    verified: bool = False
    outcome: ExperienceOutcome = ExperienceOutcome.INCONCLUSIVE

    def validate(self) -> None:
        if self.sequence < 0:
            raise ValueError("experience sequence must be >= 0")
        if not self.action.strip():
            raise ValueError("experience action is required")
        if not self.observation_fingerprint.strip():
            raise ValueError("experience observation fingerprint is required")
        for key, _ in self.parameters:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("experience parameter names must be non-empty")
        if self.outcome is ExperienceOutcome.SUCCESS and not self.verified:
            raise ValueError("successful experience event must be verified")


@dataclass(frozen=True)
class ExperienceTrace:
    experience_id: str
    goal: str
    events: tuple[ExperienceEvent, ...]
    outcome: ExperienceOutcome
    context: tuple[tuple[str, Any], ...] = ()
    source: str = "runtime"

    def validate(self) -> None:
        if not self.experience_id.strip() or not self.goal.strip():
            raise ValueError("experience identity and goal are required")
        if not self.events:
            raise ValueError("experience must contain at least one event")
        sequences = [event.sequence for event in self.events]
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise ValueError("experience event sequence must be unique and ordered")
        for event in self.events:
            event.validate()


class ExperienceStore:
    """Bounded persistent experience metadata store; no execution authority."""

    def __init__(self, path: str | Path, max_items: int = 5000, max_text: int = 20000):
        if max_items < 1 or max_text < 256:
            raise ValueError("invalid experience store limits")
        self.path = Path(path)
        self.max_items = max_items
        self.max_text = max_text
        self._lock = RLock()
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): self._safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._safe(v) for v in value]
        value, _ = redact_secrets(str(value))
        if len(value) > self.max_text:
            raise ValueError("experience text exceeds configured limit")
        return value

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("experience store must contain an object")
        self._data = raw

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def record(self, trace: ExperienceTrace) -> ExperienceTrace:
        trace.validate()
        payload = asdict(trace)
        payload = self._safe(payload)
        with self._lock:
            self._data[trace.experience_id] = payload
            while len(self._data) > self.max_items:
                del self._data[sorted(self._data)[0]]
            self._save()
        return trace

    def get(self, experience_id: str) -> ExperienceTrace | None:
        raw = self._data.get(experience_id)
        if raw is None:
            return None
        events = tuple(
            ExperienceEvent(
                sequence=int(e["sequence"]),
                action=e["action"],
                parameters=tuple((str(k), v) for k, v in e.get("parameters", [])),
                observation_fingerprint=e["observation_fingerprint"],
                verified=bool(e["verified"]),
                outcome=ExperienceOutcome(e["outcome"]),
            )
            for e in raw["events"]
        )
        return ExperienceTrace(
            experience_id=raw["experience_id"],
            goal=raw["goal"],
            events=events,
            outcome=ExperienceOutcome(raw["outcome"]),
            context=tuple((str(k), v) for k, v in raw.get("context", [])),
            source=raw.get("source", "runtime"),
        )

    def all(self) -> tuple[ExperienceTrace, ...]:
        return tuple(self.get(k) for k in sorted(self._data) if self.get(k) is not None)

class PersistentWorkflowRegistry(WorkflowRegistry):
    """Durable workflow/evidence registry built on the F10 contract."""

    def __init__(self, path: str | Path, max_items: int = 5000):
        if max_items < 1:
            raise ValueError("max_items must be >= 1")
        self.path = Path(path)
        self.max_items = max_items
        super().__init__()
        self._load_persistent()

    @staticmethod
    def _definition_payload(workflow: WorkflowDefinition) -> dict[str, Any]:
        return {
            "workflow_id": workflow.workflow_id, "name": workflow.name, "goal": workflow.goal,
            "steps": [{"action": s.action, "parameters": list(s.parameters),
                       "expectation_kind": s.expectation_kind, "expectation_value": s.expectation_value,
                       "risk": s.risk.value, "rationale": s.rationale} for s in workflow.steps],
            "variables": list(workflow.variables), "source": workflow.source,
            "version": workflow.version, "enabled": workflow.enabled,
        }

    @staticmethod
    def _definition_from_payload(raw: dict[str, Any]) -> WorkflowDefinition:
        return WorkflowDefinition(
            workflow_id=raw["workflow_id"], name=raw["name"], goal=raw["goal"],
            steps=tuple(WorkflowStep(action=s["action"], parameters=tuple((str(k), v) for k, v in s.get("parameters", [])),
                expectation_kind=s.get("expectation_kind"), expectation_value=s.get("expectation_value"),
                risk=WorkflowRisk(s.get("risk", WorkflowRisk.LOW.value)), rationale=s.get("rationale", "")) for s in raw["steps"]),
            variables=tuple(raw.get("variables", [])), source=raw.get("source", "learned"),
            version=int(raw.get("version", 1)), enabled=bool(raw.get("enabled", True)))

    def _save_persistent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"definitions": {k: self._definition_payload(v) for k, v in self._definitions.items()},
                   "evidence": {k: [{"workflow_id": e.workflow_id, "outcome": e.outcome.value,
                       "verification_status": e.verification_status, "observation_fingerprint": e.observation_fingerprint,
                       "reason": e.reason, "source": e.source, "attempt": e.attempt} for e in values]
                       for k, values in self._evidence.items()}}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _load_persistent(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("workflow registry must contain an object")
        for key, definition in raw.get("definitions", {}).items():
            workflow = self._definition_from_payload(definition)
            if workflow.workflow_id != key:
                raise ValueError("workflow registry key mismatch")
            super().register(workflow)
        for values in raw.get("evidence", {}).values():
            for value in values:
                super().record(WorkflowEvidence(workflow_id=value["workflow_id"], outcome=WorkflowOutcome(value["outcome"]),
                    verification_status=value["verification_status"], observation_fingerprint=value["observation_fingerprint"],
                    reason=value.get("reason", ""), source=value.get("source", "runtime"), attempt=int(value.get("attempt", 1))))

    def register(self, workflow: WorkflowDefinition) -> None:
        super().register(workflow)
        self._save_persistent()

    def record(self, evidence: WorkflowEvidence) -> None:
        super().record(evidence)
        self._save_persistent()


@dataclass(frozen=True)
class GeneralizationResult:
    workflow: WorkflowDefinition
    source_experiences: tuple[str, ...]
    generalized_variables: tuple[str, ...]


class WorkflowIntelligence:
    """Turns verified experience into reusable workflow knowledge."""

    def __init__(
        self,
        *,
        experience_store: ExperienceStore,
        workflow_registry: WorkflowRegistry | None = None,
    ):
        self.experiences = experience_store
        self.registry = workflow_registry or WorkflowRegistry()
        self.learner = WorkflowLearner(self.registry)
        self.matcher = WorkflowMatcher()

    def observe(self, trace: ExperienceTrace) -> ExperienceTrace:
        trace.validate()
        return trace

    def understand(self, trace: ExperienceTrace) -> dict[str, Any]:
        trace.validate()
        actions = tuple(event.action for event in trace.events)
        return {
            "goal": trace.goal,
            "action_sequence": actions,
            "step_count": len(actions),
            "outcome": trace.outcome.value,
            "verified": all(event.verified for event in trace.events),
        }

    def record(self, trace: ExperienceTrace) -> ExperienceTrace:
        self.observe(trace)
        return self.experiences.record(trace)

    @staticmethod
    def _normalized_parameters(event: ExperienceEvent) -> dict[str, Any]:
        return {key: value for key, value in event.parameters}

    def generalize(
        self,
        *,
        workflow_id: str,
        name: str,
        traces: tuple[ExperienceTrace, ...],
    ) -> GeneralizationResult:
        if not traces:
            raise ValueError("at least one experience is required")
        for trace in traces:
            trace.validate()
            if trace.outcome is not ExperienceOutcome.SUCCESS or not all(e.verified for e in trace.events):
                raise ValueError("only successful verified experiences can be generalized")
        lengths = {len(t.events) for t in traces}
        if len(lengths) != 1:
            raise ValueError("experiences must have the same step count")
        variables: list[str] = []
        raw_steps: list[dict[str, Any]] = []
        for index in range(len(traces[0].events)):
            base = traces[0].events[index]
            parameter_keys = set(self._normalized_parameters(base))
            if any(set(self._normalized_parameters(t.events[index])) != parameter_keys for t in traces[1:]):
                raise ValueError("experiences must expose the same parameter keys")
            params: dict[str, Any] = {}
            for key in sorted(parameter_keys):
                values = [self._normalized_parameters(t.events[index])[key] for t in traces]
                if all(value == values[0] for value in values):
                    params[key] = values[0]
                else:
                    variable = f"step{index}_{key}"
                    variables.append(variable)
                    params[key] = "$" + variable
            raw_steps.append({
                "action": base.action,
                "parameters": params,
                "observation_fingerprint": base.observation_fingerprint,
                "expectation_kind": "state_changed",
                "risk": WorkflowRisk.LOW.value,
            })
        if any(t.events[i].action != traces[0].events[i].action for t in traces for i in range(len(t.events))):
            raise ValueError("experiences must have the same action sequence")
        proposal = self.learner.learn(
            workflow_id=workflow_id,
            name=name,
            goal=traces[0].goal,
            steps=tuple(raw_steps),
            source="experience_generalization",
        )
        workflow = WorkflowDefinition(
            workflow_id=proposal.workflow.workflow_id,
            name=proposal.workflow.name,
            goal=proposal.workflow.goal,
            steps=proposal.workflow.steps,
            variables=tuple(variables),
            source=proposal.workflow.source,
            version=proposal.workflow.version,
            enabled=True,
        )
        self.registry.register(workflow)
        return GeneralizationResult(workflow, tuple(t.experience_id for t in traces), tuple(variables))

    def reuse(self, goal: str, limit: int = 5):
        return self.matcher.match(goal, registry=self.registry, limit=limit)

    def adapt(self, workflow_id: str, bindings: dict[str, Any]) -> WorkflowDefinition:
        return self.learner.adapt(workflow_id, bindings=bindings)

    def verify(self, evidence: WorkflowEvidence) -> None:
        evidence.validate()
        self.registry.record(evidence)

    def record_verification(
        self,
        *,
        workflow_id: str,
        success: bool,
        observation_fingerprint: str,
        reason: str = "",
    ) -> None:
        outcome = WorkflowOutcome.SUCCESS if success else WorkflowOutcome.FAILURE
        self.verify(WorkflowEvidence(
            workflow_id=workflow_id,
            outcome=outcome,
            verification_status="verified" if success else "failed",
            observation_fingerprint=observation_fingerprint,
            reason=reason,
        ))
