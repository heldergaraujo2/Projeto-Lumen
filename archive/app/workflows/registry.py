from __future__ import annotations

from dataclasses import dataclass, field

from .models import WorkflowDefinition, WorkflowEligibility, WorkflowEvidence, WorkflowOutcome, WorkflowStats


@dataclass
class WorkflowRegistry:
    """Local workflow knowledge base; registration never executes a workflow."""

    _definitions: dict[str, WorkflowDefinition] = field(default_factory=dict)
    _evidence: dict[str, list[WorkflowEvidence]] = field(default_factory=dict)

    def register(self, workflow: WorkflowDefinition) -> None:
        workflow.validate()
        existing = self._definitions.get(workflow.workflow_id)
        if existing is not None and workflow.version < existing.version:
            raise ValueError("workflow version cannot move backwards")
        self._definitions[workflow.workflow_id] = workflow
        self._evidence.setdefault(workflow.workflow_id, [])

    def get(self, workflow_id: str) -> WorkflowDefinition | None:
        return self._definitions.get(workflow_id)

    def record(self, evidence: WorkflowEvidence) -> None:
        evidence.validate()
        if evidence.workflow_id not in self._definitions:
            raise KeyError("workflow is not registered")
        self._evidence[evidence.workflow_id].append(evidence)

    def stats(self, workflow_id: str) -> WorkflowStats:
        if workflow_id not in self._definitions:
            raise KeyError("workflow is not registered")
        records = self._evidence[workflow_id]
        return WorkflowStats(
            attempts=len(records),
            successes=sum(x.outcome is WorkflowOutcome.SUCCESS for x in records),
            failures=sum(x.outcome is WorkflowOutcome.FAILURE for x in records),
            inconclusive=sum(x.outcome is WorkflowOutcome.INCONCLUSIVE for x in records),
            last_outcome=records[-1].outcome if records else None,
        )

    def reusable(self, workflow_id: str) -> bool:
        definition = self.get(workflow_id)
        if definition is None or not definition.enabled:
            return False
        return self.stats(workflow_id).eligibility is WorkflowEligibility.REUSABLE

    def all(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(self._definitions.values())


@dataclass(frozen=True)
class WorkflowMatch:
    workflow_id: str
    score: float
    reason: str


class WorkflowMatcher:
    """Deterministic retrieval; it does not execute or approve candidates."""

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in " ".join(text.casefold().split()).split() if token}

    def match(self, goal: str, *, registry: WorkflowRegistry, limit: int = 5) -> tuple[WorkflowMatch, ...]:
        if not goal.strip():
            raise ValueError("goal is required")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        wanted = self._tokens(goal)
        matches = []
        for workflow in registry.all():
            if not workflow.enabled or not registry.reusable(workflow.workflow_id):
                continue
            tokens = self._tokens(workflow.goal)
            if not tokens:
                continue
            score = len(wanted & tokens) / len(wanted | tokens)
            if score > 0:
                matches.append(WorkflowMatch(workflow.workflow_id, score, "token_overlap"))
        matches.sort(key=lambda item: (-item.score, item.workflow_id))
        return tuple(matches[:limit])
