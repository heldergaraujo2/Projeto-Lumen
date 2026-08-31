"""Testes de segurança de logging da 0.2.

Regras: API keys nunca aparecem em log; conteúdo das mensagens do
usuário nunca é gravado; detalhes técnicos de erros ficam no log para
diagnóstico.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.ai.provider import ProviderNetworkError
from app.config.settings import Settings, setup_logging
from app.core.agent import Agent, AgentError
from app.memory.store import MemoryStore
from app.security.permissions import PermissionManager

CHAVE = "sk-SEGREDO-LOG-123"
SENTINELA_CONVERSA = "MINHA-SENHA-SECRETA-DE-CONVERSA-42"


def _ler_log(data_dir: Path) -> str:
    return (data_dir / "logs" / "lumen.log").read_text(encoding="utf-8")


def _desmontar_logging() -> None:
    logger = logging.getLogger("lumen")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


class ProvedorQueFalha:
    name = "falho"

    def generate(self, message, context=None):
        return "não usado"

    def chat(self, message, context=None, *, system_prompt=None, on_delta=None):
        raise ProviderNetworkError("conexão recusada pelo host api.teste")


def test_api_key_never_logged_even_on_errors(tmp_path):
    settings = Settings(provider="openai", api_key=CHAVE, data_dir=tmp_path,
                        model="gpt-teste")
    setup_logging(settings)
    try:
        agent = Agent(ProvedorQueFalha(), MemoryStore(tmp_path / "c.json"),
                      PermissionManager())
        try:
            agent.send_message("mensagem qualquer")
        except AgentError:
            pass  # esperado: provedor falho; o que importa é o log
        log_text = _ler_log(tmp_path)
        assert CHAVE not in log_text
        assert "ProviderNetworkError" in log_text or "Provedor 'falho' falhou" in log_text
    finally:
        _desmontar_logging()


def test_conversation_content_never_logged(tmp_path):
    settings = Settings(provider="mock", api_key=CHAVE, data_dir=tmp_path)
    setup_logging(settings)
    try:
        from app.ai.mock import MockProvider

        agent = Agent(MockProvider(), MemoryStore(tmp_path / "c.json"),
                      PermissionManager())
        agent.send_message(SENTINELA_CONVERSA)  # eco do mock → memória, não log
        log_text = _ler_log(tmp_path)
        assert SENTINELA_CONVERSA not in log_text
        assert "caracteres" in log_text  # só metadados (tamanhos)
    finally:
        _desmontar_logging()


def test_streaming_deltas_not_logged(tmp_path):
    from app.ai.types import AIResponse

    class ProvedorStreaming:
        name = "stream"

        def generate(self, message, context=None):
            return "x"

        def chat(self, message, context=None, *, system_prompt=None, on_delta=None):
            if on_delta:
                on_delta(SENTINELA_CONVERSA)  # pedaço de streaming sensível
            return AIResponse(content=SENTINELA_CONVERSA, model="t")

    settings = Settings(data_dir=tmp_path)
    setup_logging(settings)
    try:
        agent = Agent(ProvedorStreaming(), MemoryStore(tmp_path / "c.json"),
                      PermissionManager())
        recebido: list = []
        agent.send_message("oi", on_delta=recebido.append)
        assert recebido == [SENTINELA_CONVERSA]  # chegou à UI…
        assert SENTINELA_CONVERSA not in _ler_log(tmp_path)  # …mas não ao log
    finally:
        _desmontar_logging()
