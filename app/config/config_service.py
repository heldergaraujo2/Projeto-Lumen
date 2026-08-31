"""ConfigService — ponte entre a tela de configurações e o Agent.

Responsabilidades (Lumen 0.2 — complemento de configuração gráfica):

- expor a configuração de IA vigente (provider/modelo/origem da chave);
- salvar configuração do usuário (não secreta em ``settings.json``,
  API Key no cofre) e **aplicar ao Agent sem reiniciar** (troca do
  provider de forma thread-safe);
- remover a API Key do cofre;
- testar a conexão com uma requisição mínima (barata), convertendo
  erros para mensagens amigáveis e mantendo detalhes técnicos no log.

A UI conversa **apenas** com este serviço — nunca com stores, factory ou
Agent diretamente.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from app.ai.mock import MockProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.provider import (
    AIProvider,
    ProviderError,
    available_providers,
    create_provider,
    user_message_for,
)
from app.config.secrets import API_KEY_NAME, SecretStore
from app.config.user_config import UserConfigStore, apply_user_overrides

if TYPE_CHECKING:
    from app.config.settings import Settings
    from app.core.agent import Agent

logger = logging.getLogger("lumen.config.service")

ClientFactory = Any


class InvalidAIConfig(ValueError):
    """Configuração de IA inválida (mensagem amigável ao usuário)."""


@dataclass(frozen=True)
class ConnectionTestResult:
    """Resultado do teste de conexão (mensagem pronta para a UI)."""

    ok: bool
    message: str


class ConfigService:
    """Gerencia a configuração de IA da Lumen e a aplica ao Agent."""

    def __init__(
        self,
        base_settings: "Settings",
        user_store: UserConfigStore,
        secrets: SecretStore,
        agent: "Agent",
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._base = base_settings
        self._user_store = user_store
        self._secrets = secrets
        self._agent = agent
        self._client_factory = client_factory  # testes injetam client fake
        self._lock = threading.RLock()

    # ------------------------------------------------------------- leitura
    def effective_settings(self) -> "Settings":
        """Configuração vigente: GUI salva > ambiente > .env > padrões."""
        return apply_user_overrides(self._base, self._user_store.load(), self._secrets)

    def current_config(self) -> dict[str, Any]:
        """Resumo da configuração vigente para exibir na UI (sem segredos)."""
        effective = self.effective_settings()
        try:
            stored = bool(self._secrets.get_secret(API_KEY_NAME))
        except Exception:
            logger.exception("Falha ao consultar o cofre de credenciais.")
            stored = False
        key_source = "cofre" if stored else (".env" if self._base.api_key else "nenhuma")
        return {
            "provider": effective.provider,
            "model": effective.model,
            "has_stored_key": stored,
            "key_source": key_source,
        }

    # ------------------------------------------------------------- escrita
    def save(
        self, provider: str, model: str, api_key: str | None = None
    ) -> "Settings":
        """Valida, persiste e **aplica ao Agent** a nova configuração.

        Args:
            provider: ``mock`` ou ``openai`` (validado contra o registro).
            model: identificador do modelo (obrigatório p/ provedores reais).
            api_key: ``None``/vazio mantém a chave já salva; texto não
                vazio salva no cofre. Remoção é método apartado.

        Raises:
            InvalidAIConfig: configuração inválida (mensagem amigável).
                Nada é persistido nem aplicado nesse caso.
        """
        provider = (provider or "").strip().lower()
        model = (model or "").strip()

        if provider not in available_providers():
            raise InvalidAIConfig(
                f"Provedor inválido: {provider!r}. Disponíveis: "
                f"{', '.join(available_providers())}."
            )

        with self._lock:
            # Valida ANTES de persistir: cria o provider candidato.
            candidate = replace(
                apply_user_overrides(self._base, {"provider": provider, "model": model}, self._secrets),
                provider=provider,
                model=model,
            )
            if api_key is not None and api_key.strip():
                candidate = replace(candidate, api_key=api_key.strip())

            try:
                new_provider = self._build_provider(candidate)
            except ProviderError as exc:
                raise InvalidAIConfig(str(exc)) from exc

            # Persiste apenas depois de validar.
            self._user_store.save({"provider": provider, "model": model})
            if api_key is not None and api_key.strip():
                self._secrets.set_secret(API_KEY_NAME, api_key.strip())

            self._agent.set_provider(new_provider)  # aplica sem reiniciar
            logger.info(
                "Configuração de IA salva e aplicada: provedor=%s, modelo=%s, chave=%s.",
                provider, model or "-", "atualizada no cofre" if api_key and api_key.strip() else "inalterada",
            )
            return candidate

    def remove_api_key(self) -> str:
        """Remove a API Key do cofre (mantém fallback para a do ``.env``).

        Returns:
            Mensagem amigável descrevendo o resultado.
        """
        with self._lock:
            self._secrets.delete_secret(API_KEY_NAME)
            logger.info("API Key removida do cofre pelo usuário.")
            effective = self.effective_settings()
            if effective.provider != "mock" and not effective.api_key:
                message = (
                    "Chave removida. Atenção: o provedor atual "
                    f"({effective.provider}) ficou sem chave — ajuste as "
                    "configurações antes de conversar."
                )
            else:
                message = "Chave removida do cofre."
            # Reaplica o provider vigente com a chave agora efetiva.
            try:
                self._agent.set_provider(self._build_provider(effective))
            except ProviderError as exc:
                logger.warning("Provider não reconfigurado após remoção: %s", exc)
            return message

    # ------------------------------------------------------------- teste
    def test_connection(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> ConnectionTestResult:
        """Teste mínimo de conexão (barato) com os valores indicados.

        Usa os valores passados (formulário da UI) ou, se omitidos, a
        configuração vigente. Com ``mock`` funciona offline, sem chave.

        Sonda: OpenAI usa ``max_tokens=1``; Gemini não limita tokens —
        modelos com "thinking" podem consumir o orçamento mínimo em
        raciocínio e devolver texto vazio, gerando falso negativo. O
        custo continua ínfimo (prompt "ping", sem retries).
        """
        provider = (provider or "").strip().lower() or None
        model = (model or "").strip() or None
        # Ponto de partida: configuração vigente (GUI salva > ambiente > .env).
        candidate = self.effective_settings()
        if provider:
            candidate = replace(candidate, provider=provider)
        if model:
            candidate = replace(candidate, model=model)
        if api_key is not None and api_key.strip():
            candidate = replace(candidate, api_key=api_key.strip())
        # Teste deve ser rápido: sem retries.
        candidate = replace(candidate, max_retries=0)

        resolved_provider = candidate.provider
        if resolved_provider not in available_providers():
            return ConnectionTestResult(
                False,
                f"Provedor inválido: {resolved_provider!r}. Disponíveis: "
                f"{', '.join(available_providers())}.",
            )

        if resolved_provider == "mock":
            # Offline por natureza: exercita o simulador.
            try:
                answer = MockProvider(candidate).generate("ping")
                ok = bool(answer.strip())
            except Exception:  # pragma: no cover - simulador não falha
                ok = False
            if ok:
                logger.info("Teste de conexão: MockProvider OK (offline).")
                return ConnectionTestResult(
                    True, "🟢 MockProvider funcionando (modo offline, sem rede)."
                )
            return ConnectionTestResult(False, "🔴 MockProvider não respondeu.")  # pragma: no cover

        logger.info(
            "Teste de conexão: provedor=%s, modelo=%s (requisição mínima).",
            resolved_provider, candidate.model or "-",
        )
        probe_max_tokens = 1 if resolved_provider == "openai" else None
        try:
            probe = self._build_provider(candidate)
            response = probe.chat(
                "ping", [], system_prompt=None, max_tokens=probe_max_tokens
            )
            if response.content and response.content.strip():
                logger.info("Teste de conexão OK (modelo=%s).", response.model or candidate.model)
                return ConnectionTestResult(
                    True,
                    f"🟢 Conexão estabelecida — o modelo "
                    f"'{response.model or candidate.model}' respondeu.",
                )
            return ConnectionTestResult(
                False, "🔴 O provedor respondeu vazio. Verifique o modelo configurado."
            )
        except ProviderError as exc:
            logger.error(
                "Teste de conexão falhou (%s): %s", type(exc).__name__, exc,
            )
            return ConnectionTestResult(False, f"🔴 {user_message_for(exc)}")
        except Exception as exc:  # nunca traceback ao usuário
            logger.exception("Erro inesperado no teste de conexão.")
            return ConnectionTestResult(
                False, f"🔴 Erro inesperado ao testar a conexão: {exc}"
            )

    # ------------------------------------------------------------- interno
    def _build_provider(self, settings: "Settings") -> AIProvider:
        """Constrói o provider (com client fake injetado em testes)."""
        if self._client_factory is not None and settings.provider in (
            "openai", "gemini", "groq", "together",
        ):
            if settings.provider == "openai":
                return OpenAIProvider(settings, client_factory=self._client_factory)
            if settings.provider == "gemini":
                from app.ai.gemini_provider import GeminiProvider

                return GeminiProvider(settings, client_factory=self._client_factory)
            if settings.provider == "groq":
                from app.ai.groq_provider import GroqProvider

                return GroqProvider(settings, client_factory=self._client_factory)
            from app.ai.together_provider import TogetherProvider

            return TogetherProvider(settings, client_factory=self._client_factory)
        return create_provider(settings)
