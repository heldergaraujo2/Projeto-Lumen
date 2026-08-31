"""Testes da persona central e do system prompt da Lumen (0.2)."""
from __future__ import annotations

from app.config.persona import DEFAULT_PERSONA, Persona, build_system_prompt


def test_persona_defaults():
    """Configuração central da identidade: nome, gênero, papel, idioma."""
    assert DEFAULT_PERSONA.name == "Lumen"
    assert DEFAULT_PERSONA.gender == "feminina"
    assert "desenvolvimento" in DEFAULT_PERSONA.role
    assert "português" in DEFAULT_PERSONA.language.lower()


def test_system_prompt_declares_identity():
    prompt = build_system_prompt()
    assert "Lumen" in prompt
    assert "feminina" in prompt
    assert "português" in prompt.lower()
    assert "desenvolvimento" in prompt


def test_system_prompt_declares_role_and_style():
    prompt = build_system_prompt()
    assert "objetiva" in prompt
    assert "colaborativa" in prompt


def test_system_prompt_declares_honesty_rules():
    """Nunca fingir ações executadas; sem acesso ao computador nesta versão."""
    prompt = build_system_prompt()
    assert "Nunca finja" in prompt
    for bloqueio in ("arquivos", "comandos", "mouse", "teclado", "tela"):
        assert bloqueio in prompt, f"limitação ausente no prompt: {bloqueio}"


def test_system_prompt_mentions_future_without_promise():
    prompt = build_system_prompt()
    assert "evoluirá" in prompt or "evoluir" in prompt
    assert "Não prometa capacidades" in prompt


def test_system_prompt_is_deterministic_and_compact():
    assert build_system_prompt() == build_system_prompt()
    assert 0 < len(build_system_prompt()) < 3000  # organizado, não um muro de texto


def test_persona_is_customizable():
    outra = Persona(name="Aurora", gender="feminina", role="assistente de testes",
                    language="inglês")
    prompt = build_system_prompt(outra)
    assert "Aurora" in prompt
    assert "assistente de testes" in prompt
    assert "inglês" in prompt
