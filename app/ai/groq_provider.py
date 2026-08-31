"""GroqProvider — integração com a API da Groq (GroqCloud, SDK oficial ``groq``).

Características (Lumen 0.3.x — expansão de providers):

- SDK oficial ``groq`` (interface OpenAI-compatível, verificada por
  introspecção da versão 1.7.0: ``Groq(api_key, timeout, max_retries)`` e
  ``chat.completions.create(model, messages, stream, max_tokens, timeout)``),
  importado **lazy**: modo mock e testes funcionam sem o pacote instalado.
- Como o SDK segue a mesma interface do ``openai``, este provider herda o
  núcleo testado do :class:`~app.ai.openai_provider.OpenAIProvider`
  (montagem do payload, timeout, retry limitado, streaming, normalização
  e mapeamento de erros — as exceções do SDK ``groq`` têm os mesmos
  nomes/status: ``AuthenticationError`` 401, ``RateLimitError`` 429,
  ``NotFoundError`` 404, ``APITimeoutError``, ``APIConnectionError``,
  ``InternalServerError`` 5xx). A implementação própria fica na fábrica
  de client, no modelo padrão e na validação de configuração.
- Modelo padrão ``openai/gpt-oss-120b`` quando ``LUMEN_MODEL`` vazio:
  modelo de produção em destaque na documentação oficial (131k de
  contexto, raciocínio e tool calling — adequado a conversa, programação
  e uso futuro como agente; US$0.15/1M in · US$0.60/1M out, ~500 t/s).
  Alternativas de produção: ``openai/gpt-oss-20b``,
  ``llama-3.3-70b-versatile`` e ``llama-3.1-8b-instant`` (modelos Llama
  hospedados pela Groq — ver README para o catálogo).
- API Key: mesma variável ``LUMEN_API_KEY``/cofre das demais integrações;
  chave gerada em console.groq.com/keys. Nunca em logs, código ou
  arquivos comuns.
- TESTAR CONEXÃO: a sonda do ConfigService não limita ``max_tokens``
  para provedores não-openai — modelos com raciocínio (gpt-oss) podem
  consumir o orçamento mínimo pensando e devolver texto vazio, gerando
  falso negativo.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.ai.openai_provider import OpenAIProvider
from app.ai.provider import MissingApiKeyError, ProviderDependencyError

if TYPE_CHECKING:
    from app.config.settings import Settings

logger = logging.getLogger("lumen.ai.groq")

#: Modelo padrão usado quando LUMEN_MODEL estiver vazio. Escolha baseada
#: no catálogo de produção da documentação oficial da GroqCloud (2026-08):
#: "openai/gpt-oss-120b" é o modelo em destaque — 131k de contexto,
#: raciocínio configurável e tool calling, disponível no plano Developer.
DEFAULT_MODEL = "openai/gpt-oss-120b"

ClientFactory = Callable[[str, float], Any]
"""Recebe (api_key, timeout) e devolve um client com ``chat.completions``."""


class GroqProvider(OpenAIProvider):
    """Provedor concreto para a API da Groq (chat/completions)."""

    name = "groq"

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
                "LUMEN_API_KEY não configurada para o provedor groq. Gere uma chave em "
                "console.groq.com/keys e salve pela tela ⚙ Configurações (cofre do sistema) "
                "ou defina no .env (veja .env.example). Para voltar ao modo offline: "
                "LUMEN_PROVIDER=mock."
            )

    @staticmethod
    def _default_client_factory(api_key: str, timeout: float) -> Any:
        try:
            import groq  # import lazy: só quando o provedor é realmente usado
        except ImportError as exc:
            raise ProviderDependencyError(
                "Dependência 'groq' não instalada. Execute: pip install -r requirements.txt"
            ) from exc
        # max_retries=0: retry é controlado por nós (política visível e testável).
        return groq.Groq(api_key=api_key, timeout=timeout, max_retries=0)
