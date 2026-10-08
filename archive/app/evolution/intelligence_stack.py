from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StackLayer(str, Enum):
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    VISION = "vision"
    CODING = "coding"
    RESEARCH = "research"
    PLANNING = "planning"


class AdapterKind(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"
    MOCK = "mock"


@dataclass(frozen=True)
class ModelProfile:
    model_id: str
    provider_id: str
    capabilities: frozenset[StackLayer]
    context_window: int = 0
    cost_per_unit: float = 0.0
    reliability: float = 1.0
    enabled: bool = True

    def validate(self) -> None:
        if not self.model_id.strip() or not self.provider_id.strip():
            raise ValueError("model and provider identity are required")
        if self.context_window < 0 or self.cost_per_unit < 0:
            raise ValueError("model limits and cost must be non-negative")
        if not 0.0 <= self.reliability <= 1.0:
            raise ValueError("reliability must be between 0 and 1")
        if not self.capabilities:
            raise ValueError("model must declare at least one capability")


@dataclass(frozen=True)
class ProviderProfile:
    provider_id: str
    adapter: AdapterKind
    models: tuple[ModelProfile, ...] = ()
    enabled: bool = True

    def validate(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider identity is required")
        for model in self.models:
            model.validate()
            if model.provider_id != self.provider_id:
                raise ValueError("model belongs to another provider")


@dataclass(frozen=True)
class StackRequest:
    request_id: str
    layer: StackLayer
    required_capabilities: frozenset[StackLayer] = frozenset()
    min_reliability: float = 0.0
    max_cost_per_unit: float | None = None
    min_context_window: int = 0

    def validate(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request identity is required")
        if not 0.0 <= self.min_reliability <= 1.0:
            raise ValueError("minimum reliability must be between 0 and 1")
        if self.max_cost_per_unit is not None and self.max_cost_per_unit < 0:
            raise ValueError("maximum cost must be non-negative")
        if self.min_context_window < 0:
            raise ValueError("minimum context must be non-negative")


@dataclass(frozen=True)
class RoutingDecision:
    request_id: str
    provider_id: str
    model_id: str
    reasons: tuple[str, ...] = ()


class IntelligenceStack:
    """Provider-neutral registry and deterministic router; never invokes providers."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderProfile] = {}

    def register(self, provider: ProviderProfile) -> None:
        provider.validate()
        if provider.provider_id in self._providers:
            raise ValueError("provider already registered")
        self._providers[provider.provider_id] = provider

    def provider(self, provider_id: str) -> ProviderProfile:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"unknown provider: {provider_id}") from exc

    def providers(self) -> tuple[ProviderProfile, ...]:
        return tuple(self._providers.values())

    def route(self, request: StackRequest) -> RoutingDecision:
        request.validate()
        candidates: list[ModelProfile] = []
        for provider in self._providers.values():
            if not provider.enabled:
                continue
            for model in provider.models:
                if not model.enabled:
                    continue
                if request.required_capabilities - model.capabilities:
                    continue
                if request.layer not in model.capabilities:
                    continue
                if model.reliability < request.min_reliability:
                    continue
                if request.max_cost_per_unit is not None and model.cost_per_unit > request.max_cost_per_unit:
                    continue
                if model.context_window < request.min_context_window:
                    continue
                candidates.append(model)
        if not candidates:
            raise LookupError("no declared model satisfies the intelligence-stack request")
        chosen = sorted(
            candidates,
            key=lambda m: (-m.reliability, m.cost_per_unit, -m.context_window, m.provider_id, m.model_id),
        )[0]
        return RoutingDecision(
            request.request_id, chosen.provider_id, chosen.model_id,
            ("declared capabilities", "reliability", "cost", "context"),
        )

    def describe(self) -> dict[str, object]:
        return {
            "providers": len(self._providers),
            "models": sum(len(p.models) for p in self._providers.values()),
            "enabled_providers": sum(p.enabled for p in self._providers.values()),
        }


@dataclass(frozen=True)
class StackEvidence:
    request_id: str
    provider_id: str
    model_id: str
    metric: str
    score: float
    sample_size: int = 1
    source: str = ""

    def validate(self) -> None:
        if not self.request_id.strip() or not self.provider_id.strip() or not self.model_id.strip():
            raise ValueError("stack evidence identity is required")
        if not self.metric.strip() or not 0.0 <= self.score <= 1.0:
            raise ValueError("invalid stack evidence")
        if self.sample_size < 1:
            raise ValueError("sample_size must be >= 1")


class StackEvaluator:
    """Compares caller-supplied evidence; never benchmarks or invokes models."""

    def compare(self, left: StackEvidence, right: StackEvidence) -> int:
        left.validate()
        right.validate()
        if left.request_id != right.request_id or left.metric != right.metric:
            raise ValueError("evidence must use the same request and metric")
        return (left.score > right.score) - (left.score < right.score)


@dataclass(frozen=True)
class StackAdaptation:
    adaptation_id: str
    target_provider: str
    target_model: str
    changed_layers: frozenset[StackLayer]
    rationale: str
    isolated: bool = True

    def validate(self) -> None:
        if not self.adaptation_id.strip() or not self.target_provider.strip() or not self.target_model.strip():
            raise ValueError("adaptation identity is required")
        if not self.changed_layers or not self.rationale.strip():
            raise ValueError("adaptation requires changed layers and rationale")
        if not self.isolated:
            raise ValueError("intelligence-stack adaptation must be isolated")


class IntelligenceStackEvolution:
    """F17 proposal/evidence boundary; no live stack mutation."""

    def propose(self, adaptation: StackAdaptation, evidence: tuple[StackEvidence, ...]) -> None:
        adaptation.validate()
        if not evidence:
            raise ValueError("adaptation requires evidence")
        for item in evidence:
            item.validate()
        if any(item.provider_id != adaptation.target_provider or item.model_id != adaptation.target_model for item in evidence):
            raise ValueError("evidence does not match adaptation target")
