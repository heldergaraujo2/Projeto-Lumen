from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import WorkflowDefinition, WorkflowEvidence, WorkflowOutcome, WorkflowRisk, WorkflowStep
from .registry import WorkflowRegistry
from app.unreal.models import UnrealPlan


@dataclass(frozen=True)
class WorkflowProposal:
    workflow: WorkflowDefinition
    evidence_count: int
    confidence: float
    requires_human_approval: bool


class WorkflowLearner:
    """Converts successful observed plans into reusable, non-executing workflow knowledge."""

    def __init__(self, registry: WorkflowRegistry | None = None):
        self.registry = registry or WorkflowRegistry()

    def learn(self, *, workflow_id: str, name: str, goal: str, steps: tuple[dict[str, Any], ...], source: str = "observed") -> WorkflowProposal:
        if not steps:
            raise ValueError("at least one observed step is required")
        learned_steps = []
        for raw in steps:
            if "action" not in raw:
                raise ValueError("observed step requires action")
            learned_steps.append(
                WorkflowStep(
                    action=str(raw["action"]),
                    parameters=tuple(sorted((str(k), v) for k, v in raw.get("parameters", {}).items())),
                    expectation_kind=raw.get("expectation_kind"),
                    expectation_value=raw.get("expectation_value"),
                    risk=WorkflowRisk(raw.get("risk", WorkflowRisk.LOW.value)),
                    rationale=str(raw.get("rationale", "")),
                )
            )
        workflow = WorkflowDefinition(
            workflow_id=workflow_id, name=name, goal=goal,
            steps=tuple(learned_steps), source=source,
        )
        self.registry.register(workflow)
        stats = self.registry.stats(workflow_id)
        return WorkflowProposal(
            workflow=workflow,
            evidence_count=stats.attempts,
            confidence=stats.success_rate if stats.attempts else 0.0,
            requires_human_approval=workflow.requires_human_approval,
        )

    def learn_unreal_plan(self, *, plan: UnrealPlan, workflow_id: str, name: str | None = None) -> WorkflowProposal:
        plan.validate()
        steps = tuple(
            {
                "action": action.operation.value,
                "parameters": ({"value": action.value} if action.value is not None else {})
                | ({"keys": action.keys} if action.keys else {}),
                "expectation_kind": action.expected.kind if action.expected else None,
                "expectation_value": action.expected.value if action.expected else None,
                "risk": action.risk.value,
                "rationale": action.rationale,
            }
            for action in plan.actions
        )
        return self.learn(
            workflow_id=workflow_id,
            name=name or plan.goal,
            goal=plan.goal,
            steps=steps,
            source="unreal_agent",
        )

    def record_outcome(self, *, workflow_id: str, outcome: WorkflowOutcome, verification_status: str, observation_fingerprint: str, reason: str = "") -> None:
        self.registry.record(
            WorkflowEvidence(
                workflow_id=workflow_id, outcome=outcome,
                verification_status=verification_status,
                observation_fingerprint=observation_fingerprint,
                reason=reason,
            )
        )

    def adapt(self, workflow_id: str, *, bindings: dict[str, Any]) -> WorkflowDefinition:
        workflow = self.registry.get(workflow_id)
        if workflow is None:
            raise KeyError("workflow is not registered")
        if set(bindings) != set(workflow.variables):
            raise ValueError("workflow bindings must match declared variables exactly")

        def substitute(value: Any) -> Any:
            if isinstance(value, str) and value.startswith("$") and value[1:] in bindings:
                return bindings[value[1:]]
            return value

        steps = tuple(
            WorkflowStep(
                action=step.action,
                parameters=tuple(sorted((key, substitute(value)) for key, value in step.parameters)),
                expectation_kind=step.expectation_kind,
                expectation_value=substitute(step.expectation_value),
                risk=step.risk,
                rationale=step.rationale,
            )
            for step in workflow.steps
        )
        return WorkflowDefinition(
            workflow_id=workflow.workflow_id, name=workflow.name, goal=workflow.goal,
            steps=steps, variables=workflow.variables, source=workflow.source,
            version=workflow.version + 1, enabled=workflow.enabled,
        )
