"""Runtime de providers da Lumen (F25).

Executa providers reais já registrados, com seleção determinística, retries
limitados, fallback por compatibilidade/custo/localidade e evidência de cada
tentativa. Não concede permissões nem altera Policy/Sandbox/Checkpoint/Audit:
a chamada deve chegar aqui já autorizada pelo runtime superior.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from app.ai.provider import (
    AIProvider, ProviderAuthError, ProviderError, RETRYABLE_ERRORS,
)
from app.ai.types import AIResponse
from app.evolution.intelligence_stack import StackLayer


@dataclass(frozen=True)
class RuntimeProviderSpec:
    provider_id: str
    provider: AIProvider
    capabilities: frozenset[StackLayer]
    reliability: float = 1.0
    cost_per_unit: float = 0.0
    context_window: int = 0
    local: bool = False
    enabled: bool = True

    def validate(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider identity is required")
        if not self.capabilities:
            raise ValueError("provider must declare capabilities")
        if not 0.0 <= self.reliability <= 1.0:
            raise ValueError("reliability must be between 0 and 1")
        if self.cost_per_unit < 0 or self.context_window < 0:
            raise ValueError("provider limits must be non-negative")


@dataclass(frozen=True)
class RuntimeRequest:
    request_id: str
    required_capabilities: frozenset[StackLayer] = frozenset()
    min_reliability: float = 0.0
    max_cost_per_unit: float | None = None
    min_context_window: int = 0
    preferred_provider_ids: tuple[str, ...] = ()

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
class RuntimeAttempt:
    provider_id: str
    model_id: str
    success: bool
    error_type: str = ""


@dataclass(frozen=True)
class RuntimeResult:
    request_id: str
    response: AIResponse
    provider_id: str
    attempts: tuple[RuntimeAttempt, ...]
    verified: bool


class ProviderRuntime:
    """Executa e faz fallback entre providers já autorizados."""

    def __init__(
        self,
        providers: Sequence[RuntimeProviderSpec],
        *,
        max_retries_per_provider: int = 0,
        authorization: Callable[[RuntimeRequest, str], bool] | None = None,
        verification: Callable[[AIResponse], bool] | None = None,
        audit: Callable[[RuntimeAttempt], None] | None = None,
    ) -> None:
        if max_retries_per_provider < 0:
            raise ValueError("max_retries_per_provider must be >= 0")
        self._providers: dict[str, RuntimeProviderSpec] = {}
        for spec in providers:
            spec.validate()
            if spec.provider_id in self._providers:
                raise ValueError("provider already registered")
            self._providers[spec.provider_id] = spec
        self._max_retries = max_retries_per_provider
        self._authorization = authorization
        self._verification = verification
        self._audit = audit

    def providers(self) -> tuple[RuntimeProviderSpec, ...]:
        return tuple(self._providers.values())

    def compatible(self, request: RuntimeRequest) -> tuple[RuntimeProviderSpec, ...]:
        request.validate()
        candidates = [
            p for p in self._providers.values()
            if p.enabled
            and p.reliability >= request.min_reliability
            and (request.max_cost_per_unit is None or p.cost_per_unit <= request.max_cost_per_unit)
            and p.context_window >= request.min_context_window
            and not (request.required_capabilities - p.capabilities)
        ]
        preferred = {p: i for i, p in enumerate(request.preferred_provider_ids)}
        return tuple(sorted(
            candidates,
            key=lambda p: (
                preferred.get(p.provider_id, len(preferred)),
                p.cost_per_unit,
                -p.reliability,
                -p.context_window,
                p.provider_id,
            ),
        ))


    @staticmethod
    def _normalize_context(
        context: Sequence[Mapping[str, str]] | None,
    ) -> tuple[dict[str, str], ...]:
        normalized: list[dict[str, str]] = []
        for item in context or ():
            if not isinstance(item, Mapping):
                raise ValueError("context item must be a mapping")
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", ""))
            if role not in {"system", "user", "assistant"}:
                raise ValueError("context role is invalid")
            if not content.strip():
                continue
            normalized.append({"role": role, "content": content})
        return tuple(normalized)

    def execute_chat(
        self,
        request: RuntimeRequest,
        message: str,
        context: Sequence[Mapping[str, str]] | None = None,
        *,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        on_delta=None,
        authorized: bool = False,
    ) -> RuntimeResult:
        request.validate()
        if not authorized:
            raise PermissionError("provider runtime requires explicit authorization")
        normalized_context = self._normalize_context(context)
        candidates = self.compatible(request)
        if not candidates:
            raise LookupError("no enabled provider satisfies the runtime request")
        attempts: list[RuntimeAttempt] = []
        last_error: Exception | None = None

        for spec in candidates:
            if self._authorization is not None and not self._authorization(request, spec.provider_id):
                attempt = RuntimeAttempt(spec.provider_id, spec.provider.model_name, False, "authorization_denied")
                attempts.append(attempt)
                if self._audit is not None:
                    self._audit(attempt)
                continue

            total_attempts = self._max_retries + 1
            for attempt_no in range(total_attempts):
                try:
                    response = spec.provider.chat(
                        message, normalized_context,
                        system_prompt=system_prompt,
                        on_delta=on_delta,
                        max_tokens=max_tokens,
                    )
                    if not isinstance(response, AIResponse) or not response.content.strip():
                        raise ProviderError("provider returned an invalid empty response")
                    verified = True if self._verification is None else bool(self._verification(response))
                    if not verified:
                        raise ProviderError("provider response failed verification")
                    success_attempt = RuntimeAttempt(spec.provider_id, response.model or spec.provider.model_name, True)
                    attempts.append(success_attempt)
                    if self._audit is not None:
                        self._audit(success_attempt)
                    return RuntimeResult(request.request_id, response, spec.provider_id, tuple(attempts), True)
                except ProviderAuthError:
                    attempt = RuntimeAttempt(spec.provider_id, spec.provider.model_name, False, "ProviderAuthError")
                    attempts.append(attempt)
                    if self._audit is not None:
                        self._audit(attempt)
                    last_error = ProviderAuthError("provider authentication failed")
                    break
                except RETRYABLE_ERRORS as exc:
                    attempt = RuntimeAttempt(spec.provider_id, spec.provider.model_name, False, type(exc).__name__)
                    attempts.append(attempt)
                    if self._audit is not None:
                        self._audit(attempt)
                    last_error = exc
                    if attempt_no + 1 < total_attempts:
                        continue
                    break
                except ProviderError as exc:
                    attempt = RuntimeAttempt(spec.provider_id, spec.provider.model_name, False, type(exc).__name__)
                    attempts.append(attempt)
                    if self._audit is not None:
                        self._audit(attempt)
                    last_error = exc
                    break

        if last_error is not None:
            raise ProviderError(
                f"all compatible providers failed for request {request.request_id}: {type(last_error).__name__}"
            ) from last_error
        raise ProviderError(f"all compatible providers were denied for request {request.request_id}")
