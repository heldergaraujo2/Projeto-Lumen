"""Camada de provedores de IA da Lumen.

O Agent Core depende apenas de :class:`AIProvider` e dos tipos de
:mod:`app.ai.types` (:class:`AIResponse`). Provedores concretos (mock,
OpenAI, e futuros) vivem em módulos próprios e são instanciados por
:func:`create_provider` — o ÚNICO ponto do sistema que conhece o
mapeamento nome → provedor.

Taxonomia de erros (item 11 da 0.2): cada falha tem um tipo próprio, um
texto amigável ao usuário e uma política de retry (ver
``RETRYABLE_ERRORS``).
"""
from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from app.ai.types import AIResponse, ResponseType

if TYPE_CHECKING:  # evita dependência em runtime (tipagem apenas)
    from app.config.settings import Settings

ContextMessage = Mapping[str, str]
"""Item de contexto de conversa: ``{"role", "content", "timestamp"}``."""

DeltaCallback = Callable[[str], None]
"""Recebe pedaços de texto durante streaming (pode ser ``None``)."""


# --------------------------------------------------------------------- erros
class ProviderError(RuntimeError):
    """Falha em um provedor de IA."""


class MissingApiKeyError(ProviderError):
    """API Key ausente (configuração)."""


class ModelNotConfiguredError(ProviderError):
    """Nenhum modelo configurado para o provedor."""


class InvalidModelError(ProviderError):
    """Modelo rejeitado pela API."""


class ProviderAuthError(ProviderError):
    """Autenticação inválida (chave errada/revogada)."""


class ProviderRateLimitError(ProviderError):
    """Limite de requisições/uso atingido (temporário)."""


class ProviderTimeoutError(ProviderError):
    """A chamada excedeu o tempo limite configurado."""


class ProviderNetworkError(ProviderError):
    """Falha de rede/conexão com o provedor."""


class ProviderServerError(ProviderError):
    """Erro interno do servidor do provedor (5xx)."""


class ProviderDependencyError(ProviderError):
    """Dependência (SDK) não instalada."""


class UnexpectedProviderError(ProviderError):
    """Erro não classificado."""


#: Erros temporários que podem ser repetidos com retry (limitado).
RETRYABLE_ERRORS: tuple[type[ProviderError], ...] = (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderNetworkError,
    ProviderServerError,
)


def user_message_for(exc: ProviderError) -> str:
    """Mensagem amigável (pt-BR) para exibir na UI.

    As exceções desta taxonomia já carregam textos amigáveis; o fallback
    cobre provedores que levantem :class:`ProviderError` genérico.
    """
    known = (
        MissingApiKeyError, ModelNotConfiguredError, InvalidModelError,
        ProviderAuthError, ProviderRateLimitError, ProviderTimeoutError,
        ProviderNetworkError, ProviderServerError, ProviderDependencyError,
    )
    if isinstance(exc, known):
        return str(exc)
    return f"O provedor de IA falhou: {exc}"


# ------------------------------------------------------------------ contrato
class AIProvider(ABC):
    """Interface única para geração de respostas da Lumen.

    Dois níveis de API:

    - :meth:`generate` — compatível com a 0.1, devolve ``str``;
    - :meth:`chat` — API rica da 0.2: recebe system prompt e histórico,
      suporta streaming via callback ``on_delta`` e devolve uma
      :class:`~app.ai.types.AIResponse` normalizada (content, model,
      usage, finish_reason).

    A implementação padrão de :meth:`chat` embrulha :meth:`generate`,
    portanto provedores simples (como o mock) só precisam implementar
    ``generate``.
    """

    name: str = "base"

    @property
    def model_name(self) -> str:
        """Identificador do modelo em uso ("" se não fizer sentido)."""
        return ""

    @abstractmethod
    def generate(self, message: str, context: Sequence[ContextMessage] | None = None) -> str:
        """Responde a ``message`` considerando o histórico ``context``.

        Raises:
            ProviderError: em qualquer falha de comunicação/processamento.
        """
        raise ProviderError("AIProvider.generate não implementado")  # pragma: no cover

    def chat(
        self,
        message: str,
        context: Sequence[ContextMessage] | None = None,
        *,
        system_prompt: str | None = None,
        on_delta: DeltaCallback | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """API rica (0.2). Provedores reais devem sobrescrever.

        A implementação padrão delega a :meth:`generate` (ignora o system
        prompt e ``max_tokens``, apropriado para simuladores) e entrega a
        resposta inteira de uma vez ao ``on_delta``, se houver.
        """
        content = self.generate(message, context)
        if on_delta is not None:
            on_delta(content)
        return AIResponse(
            content=content,
            model=self.model_name,
            usage=None,
            finish_reason="stop",
            response_type=ResponseType.FINAL_RESPONSE,
        )


# ------------------------------------------------------------------- fábrica
#: Registro nome → "módulo.Classe". Futuros provedores entram aqui.
_PROVIDER_REGISTRY: dict[str, str] = {
    "mock": "app.ai.mock.MockProvider",
    "openai": "app.ai.openai_provider.OpenAIProvider",
    "gemini": "app.ai.gemini_provider.GeminiProvider",
    "groq": "app.ai.groq_provider.GroqProvider",
    "together": "app.ai.together_provider.TogetherProvider",
}


def available_providers() -> tuple[str, ...]:
    """Nomes de provedores registrados."""
    return tuple(sorted(_PROVIDER_REGISTRY))


def create_provider(settings: "Settings | None" = None) -> AIProvider:
    """Instancia o provedor configurado em ``LUMEN_PROVIDER``.

    Raises:
        ProviderError: se o nome não estiver registrado ou a configuração
            do provedor escolhido seja inválida (ex.: sem API key/modelo).
    """
    name = str(getattr(settings, "provider", "mock") or "mock").strip().lower()
    dotted_path = _PROVIDER_REGISTRY.get(name)
    if dotted_path is None:
        raise ProviderError(
            f"Provedor desconhecido: {name!r}. Disponíveis: {', '.join(available_providers())}."
        )

    module_path, _, class_name = dotted_path.rpartition(".")
    provider_class: Any = getattr(importlib.import_module(module_path), class_name)
    provider: AIProvider = provider_class(settings)
    return provider
