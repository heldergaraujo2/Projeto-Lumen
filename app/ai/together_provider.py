"""TogetherProvider — Llama 4 real via Together AI (SDK oficial ``together``).

Características (Lumen 0.3.x — expansão de providers):

- **Por que Together AI**: o pedido original era "Meta Llama API", mas a
  Meta encerrou o Llama API Public Preview em **06/07/2026** (fonte:
  llama.developer.meta.com/docs/llama-api-deprecation — a API hoje só
  devolve uma resposta de encerramento). Modelos Llama permanecem em
  hosts de terceiros; a Together AI é a que serve o **Llama 4** real em
  API pública (a Cerebras removeu todos os Llama do catálogo público
  entre 10/2025 e 05/2026). Decisão registrada em LUMEN_STATE.md.
- SDK oficial ``together`` (interface OpenAI-compatível, verificada por
  introspecção da versão 2.32.0: ``Together(api_key, timeout,
  max_retries)`` e ``chat.completions.create(model, messages, stream,
  max_tokens, timeout)``), importado **lazy**.
- Como o SDK segue a mesma interface do ``openai``, este provider herda
  o núcleo testado do :class:`~app.ai.openai_provider.OpenAIProvider`
  (payload, timeout, retry limitado, streaming, normalização e
  mapeamento de erros — exceções com os mesmos nomes/status:
  ``AuthenticationError`` 401, ``RateLimitError`` 429,
  ``NotFoundError`` 404, ``APITimeoutError``, ``APIConnectionError``,
  ``InternalServerError`` 5xx). Implementação própria: fábrica de
  client, modelo padrão e validação de configuração.
- Modelo padrão ``meta-llama/Llama-4-Scout-17B-16E-Instruct`` quando
  ``LUMEN_MODEL`` vazio: Llama 4 Scout (109B total/17B ativos, MoE)
  indicado pela própria Together para análise multi-documento e
  **raciocínio sobre codebase** — adequado a conversa, programação,
  contexto amplo e uso futuro como agente (function calling; US$0.18/1M
  in · US$0.59/1M out). Alternativa: ``meta-llama/Llama-4-Maverick-17B-
  128E-Instruct-FP8`` (flagship 400B/17B ativos) e o Llama 3.3 ainda
  listado no catálogo (ver README).
- API Key: mesma variável ``LUMEN_API_KEY``/cofre das demais integrações;
  chave gerada em api.together.ai. Nunca em logs, código ou arquivos.
- TESTAR CONEXÃO: a sonda do ConfigService não limita ``max_tokens``
  para provedores não-openai (padrão já usado com o Gemini).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.ai.openai_provider import OpenAIProvider
from app.ai.provider import MissingApiKeyError, ProviderDependencyError

if TYPE_CHECKING:
    from app.config.settings import Settings

logger = logging.getLogger("lumen.ai.together")

#: Modelo padrão usado quando LUMEN_MODEL estiver vazio. Escolha baseada
#: no catálogo oficial da Together AI (2026-08): Llama 4 Scout — contexto
#: amplo, function calling, foco em raciocínio sobre codebase, custo
#: menor que o Maverick.
DEFAULT_MODEL = "meta-llama/Llama-4-Scout-17B-16E-Instruct"

ClientFactory = Callable[[str, float], Any]
"""Recebe (api_key, timeout) e devolve um client com ``chat.completions``."""


class TogetherProvider(OpenAIProvider):
    """Provedor concreto para a API da Together AI (chat/completions)."""

    name = "together"

    def __init__(
        self,
        settings: "Settings | None" = None,
        client_factory: ClientFactory | None = None,
        retry_backoff: float = 0.5,
    ) -> None:
        # Init próprio (espelha o do OpenAIProvider) porque o modelo é
        # OPCIONAL aqui: vazio usa DEFAULT_MODEL.
        self._model = str(getattr(settings, "model", "") or "").strip() or DEFAULT_MODEL
        self._api_key = str(getattr(settings, "api_key", "") or "").strip()
        self._timeout = float(getattr(settings, "request_timeout", 60.0) or 60.0)
        self._max_retries = int(getattr(settings, "max_retries", 2) or 0)
        self._retry_backoff = float(retry_backoff)
        self._client_factory = client_factory or self._default_client_factory
        self._client: Any = None

        self._validate_config()

    # ----------------------------------------------------------- configuração
    def _validate_config(self) -> None:
        """Falha rápido, com instrução clara de como configurar."""
        if not self._api_key:
            raise MissingApiKeyError(
                "LUMEN_API_KEY não configurada para o provedor together. Gere uma chave em "
                "api.together.ai/settings/api-keys e salve pela tela ⚙ Configurações (cofre "
                "do sistema) ou defina no .env (veja .env.example). Para voltar ao modo "
                "offline: LUMEN_PROVIDER=mock."
            )

    @staticmethod
    def _default_client_factory(api_key: str, timeout: float) -> Any:
        try:
            import together  # import lazy: só quando o provedor é realmente usado
        except ImportError as exc:
            raise ProviderDependencyError(
                "Dependência 'together' não instalada. Execute: pip install -r requirements.txt"
            ) from exc
        # max_retries=0: retry é controlado por nós (política visível e testável).
        return together.Together(api_key=api_key, timeout=timeout, max_retries=0)
