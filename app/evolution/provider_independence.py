from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from .intelligence_stack import AdapterKind, ModelProfile, ProviderProfile, StackLayer, StackRequest


class IndependenceRequirement(str, Enum):
    CAPABILITY = "capability"
    RELIABILITY = "reliability"
    CONTEXT = "context"
    COST = "cost"
    LOCAL_AVAILABILITY = "local_availability"
    FAILOVER = "failover"


@dataclass(frozen=True)
class ProviderCapabilityContract:
    capability_id: str
    required_layers: frozenset[StackLayer]
    min_reliability: float = 0.0
    min_context_window: int = 0
    max_cost_per_unit: float | None = None
    requirements: frozenset[IndependenceRequirement] = frozenset()

    def validate(self) -> None:
        if not self.capability_id.strip() or not self.required_layers:
            raise ValueError("provider contract requires identity and layers")
        if not 0.0 <= self.min_reliability <= 1.0:
            raise ValueError("minimum reliability must be between 0 and 1")
        if self.min_context_window < 0:
            raise ValueError("minimum context must be non-negative")
        if self.max_cost_per_unit is not None and self.max_cost_per_unit < 0:
            raise ValueError("maximum cost must be non-negative")


@dataclass(frozen=True)
class ProviderCompatibility:
    provider_id: str
    model_id: str
    contract_id: str
    compatible: bool
    reasons: tuple[str, ...]

    def validate(self) -> None:
        if not self.provider_id.strip() or not self.model_id.strip() or not self.contract_id.strip():
            raise ValueError("compatibility identity is required")


@dataclass(frozen=True)
class ProviderFallbackPolicy:
    policy_id: str
    ordered_provider_ids: tuple[str, ...]
    minimum_alternatives: int = 1

    def validate(self) -> None:
        if not self.policy_id.startswith("PROV-POL-"):
            raise ValueError("invalid provider policy identifier")
        if not self.ordered_provider_ids:
            raise ValueError("provider fallback policy requires providers")
        if len(set(self.ordered_provider_ids)) != len(self.ordered_provider_ids):
            raise ValueError("provider fallback order must be unique")
        if self.minimum_alternatives < 1:
            raise ValueError("minimum alternatives must be positive")


@dataclass(frozen=True)
class ProviderIndependenceAssessment:
    contract_id: str
    compatible: tuple[ProviderCompatibility, ...]
    incompatible: tuple[ProviderCompatibility, ...]
    independent: bool
    alternative_count: int
    reasons: tuple[str, ...]

    def validate(self) -> None:
        if not self.contract_id.strip():
            raise ValueError("contract identity is required")
        for item in (*self.compatible, *self.incompatible):
            item.validate()


@dataclass(frozen=True)
class ProviderMigrationPlan:
    plan_id: str
    contract_id: str
    source_provider_id: str
    target_provider_id: str
    source_model_id: str
    target_model_id: str
    steps: tuple[str, ...]
    reversible: bool = True

    def validate(self) -> None:
        if not self.plan_id.startswith("PROV-MIG-"):
            raise ValueError("invalid migration plan identifier")
        if not self.contract_id.strip() or not self.source_provider_id.strip() or not self.target_provider_id.strip():
            raise ValueError("migration identity is required")
        if self.source_provider_id == self.target_provider_id and self.source_model_id == self.target_model_id:
            raise ValueError("migration must change provider or model")
        if not self.steps:
            raise ValueError("migration requires steps")
        if not self.reversible:
            raise ValueError("provider migration must remain reversible")


class ProviderIndependenceLab:
    """F21 provider-neutral compatibility and migration planning.

    This layer evaluates declared profiles only. It never invokes providers,
    routes live requests, downloads models, changes the live stack, or deploys.
    """

    def __init__(self, *, providers: tuple[ProviderProfile, ...] = ()) -> None:
        self._providers: dict[str, ProviderProfile] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: ProviderProfile) -> None:
        provider.validate()
        if provider.provider_id in self._providers:
            raise ValueError("provider already registered")
        self._providers[provider.provider_id] = provider

    def provider(self, provider_id: str) -> ProviderProfile:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError("unknown provider") from exc

    def providers(self) -> tuple[ProviderProfile, ...]:
        return tuple(self._providers.values())

    @staticmethod
    def _compatible(provider: ProviderProfile, model: ModelProfile, contract: ProviderCapabilityContract) -> tuple[bool, tuple[str, ...]]:
        reasons: list[str] = []
        if not provider.enabled:
            reasons.append("provider disabled")
        if not model.enabled:
            reasons.append("model disabled")
        if contract.required_layers - model.capabilities:
            reasons.append("missing required layers")
        if model.reliability < contract.min_reliability:
            reasons.append("reliability below minimum")
        if model.context_window < contract.min_context_window:
            reasons.append("context below minimum")
        if contract.max_cost_per_unit is not None and model.cost_per_unit > contract.max_cost_per_unit:
            reasons.append("cost above maximum")
        return not reasons, tuple(reasons)

    def assess(self, contract: ProviderCapabilityContract) -> ProviderIndependenceAssessment:
        contract.validate()
        compatible: list[ProviderCompatibility] = []
        incompatible: list[ProviderCompatibility] = []
        for provider in self._providers.values():
            for model in provider.models:
                ok, reasons = self._compatible(provider, model, contract)
                item = ProviderCompatibility(provider.provider_id, model.model_id, contract.capability_id, ok, reasons)
                (compatible if ok else incompatible).append(item)
        compatible.sort(key=lambda x: (x.provider_id, x.model_id))
        incompatible.sort(key=lambda x: (x.provider_id, x.model_id))
        providers = {x.provider_id for x in compatible}
        return ProviderIndependenceAssessment(
            contract.capability_id,
            tuple(compatible),
            tuple(incompatible),
            len(providers) >= 2,
            len(providers),
            ("provider-neutral contract", "declared profile compatibility"),
        )

    def validate_fallback(self, policy: ProviderFallbackPolicy, contract: ProviderCapabilityContract) -> ProviderIndependenceAssessment:
        policy.validate()
        assessment = self.assess(contract)
        available = set(x.provider_id for x in assessment.compatible)
        ordered = [p for p in policy.ordered_provider_ids if p in available]
        if len(ordered) < policy.minimum_alternatives:
            raise ValueError("fallback policy lacks required compatible alternatives")
        return assessment

    def plan_migration(
        self,
        plan: ProviderMigrationPlan,
        contract: ProviderCapabilityContract,
    ) -> ProviderMigrationPlan:
        plan.validate()
        assessment = self.assess(contract)
        targets = {(x.provider_id, x.model_id) for x in assessment.compatible}
        if (plan.target_provider_id, plan.target_model_id) not in targets:
            raise ValueError("migration target is incompatible with contract")
        self.provider(plan.source_provider_id)
        self.provider(plan.target_provider_id)
        return plan

    def digest(self, contract: ProviderCapabilityContract) -> str:
        assessment = self.assess(contract)
        payload = {
            "contract": contract.capability_id,
            "compatible": [(x.provider_id, x.model_id) for x in assessment.compatible],
            "incompatible": [(x.provider_id, x.model_id, x.reasons) for x in assessment.incompatible],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def to_stack_request(self, contract: ProviderCapabilityContract, request_id: str) -> StackRequest:
        contract.validate()
        return StackRequest(
            request_id=request_id,
            layer=next(iter(sorted(contract.required_layers, key=lambda x: x.value))),
            required_capabilities=contract.required_layers,
            min_reliability=contract.min_reliability,
            max_cost_per_unit=contract.max_cost_per_unit,
            min_context_window=contract.min_context_window,
        )


def ensure_f21_no_execution_surface() -> frozenset[str]:
    return frozenset({
        "execute", "invoke_provider", "run_model", "download_model", "train",
        "infer", "deploy", "grant_permission", "change_policy", "disable_audit",
        "widen_scope", "execute_driver", "run_browser", "run_tool",
    })
