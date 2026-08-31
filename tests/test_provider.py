"""Testes dos provedores de IA (interface + MockProvider + fábrica)."""
from __future__ import annotations

import pytest

from app.ai.mock import MockProvider
from app.ai.provider import AIProvider, ProviderError, create_provider
from app.config.settings import Settings


def test_mock_implements_ai_provider():
    assert isinstance(MockProvider(), AIProvider)


def test_mock_answers_greeting():
    """4. MockProvider responde à saudação da fase 0."""
    reply = MockProvider().generate("Olá Lumen", [])
    assert reply.strip()
    assert "Olá" in reply
    assert "Lumen" in reply


def test_mock_answers_any_message():
    provider = MockProvider()
    reply = provider.generate("Quero criar um inventário")
    assert isinstance(reply, str) and reply.strip()


def test_mock_echoes_message_by_default():
    reply = MockProvider().generate("organizar meus arquivos", [])
    assert "organizar meus arquivos" in reply


def test_mock_uses_context_count():
    provider = MockProvider()
    context = [
        {"role": "user", "content": "oi", "timestamp": "2026-01-01T10:00:00-03:00"},
        {"role": "assistant", "content": "olá", "timestamp": "2026-01-01T10:00:01-03:00"},
    ]
    reply = provider.generate("meu teclado quebrou", context)
    assert "2 mensagens anteriores" in reply


def test_factory_returns_mock(tmp_path):
    settings = Settings(provider="mock", data_dir=tmp_path)
    provider = create_provider(settings)
    assert isinstance(provider, MockProvider)
    assert provider.name == "mock"


def test_factory_rejects_unknown_provider(tmp_path):
    settings = Settings(provider="gpt-inexistente", data_dir=tmp_path)
    with pytest.raises(ProviderError):
        create_provider(settings)
