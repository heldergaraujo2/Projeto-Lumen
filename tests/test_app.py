"""Testes de inicialização da aplicação (composição + configuração)."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app import __version__
from app.ai.mock import MockProvider
from app.config.settings import ConfigError, Settings, setup_logging
from app.core.agent import Agent
from app.memory.store import MemoryStore
from main import build_agent

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_agent_wires_all_components(tmp_path):
    """6. A aplicação consegue inicializar seus componentes de ponta a ponta."""
    settings = Settings(provider="mock", data_dir=tmp_path / "data")
    settings.ensure_dirs()
    agent = build_agent(settings)

    assert isinstance(agent, Agent)
    assert isinstance(agent.provider, MockProvider)
    assert isinstance(agent.memory, MemoryStore)
    assert agent.task_manager is not None

    # Conversa completa funciona logo após a montagem.
    reply = agent.send_message("Olá Lumen")
    assert reply.strip()
    assert agent.memory.count == 2


def test_version_matches_phase():
    assert __version__ == "0.6.8"


def test_settings_loads_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# exemplo\nLUMEN_PROVIDER=mock\nLUMEN_LOG_LEVEL=DEBUG\nLUMEN_DATA_DIR=dados\n",
        encoding="utf-8",
    )
    settings = Settings.load(env_file=env_file, environ={})

    assert settings.provider == "mock"
    assert settings.log_level == "DEBUG"
    assert settings.data_dir == PROJECT_ROOT / "dados"


def test_settings_environment_overrides_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LUMEN_LOG_LEVEL=DEBUG\n", encoding="utf-8")
    settings = Settings.load(
        env_file=env_file, environ={"LUMEN_PROVIDER": "mock", "LUMEN_LOG_LEVEL": "ERROR"}
    )
    assert settings.log_level == "ERROR"


def test_settings_rejects_invalid_log_level(tmp_path):
    with pytest.raises(ConfigError):
        Settings(log_level="CHATTY", data_dir=tmp_path)


def test_settings_creates_directories(tmp_path):
    settings = Settings(data_dir=tmp_path / "dados")
    settings.ensure_dirs()
    assert (tmp_path / "dados" / "memory").is_dir()
    assert (tmp_path / "dados" / "logs").is_dir()


def test_logging_redacts_secrets(tmp_path):
    settings = Settings(provider="mock", data_dir=tmp_path, api_key="sk-supersecret123")
    setup_logging(settings)
    logger = logging.getLogger("lumen")
    try:
        logger.error("configurado com a chave sk-supersecret123")
        log_text = (tmp_path / "logs" / "lumen.log").read_text(encoding="utf-8")
        assert "sk-supersecret123" not in log_text
        assert "***" in log_text
    finally:  # não vazar handlers para outros testes
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


def test_env_example_documents_expected_keys():
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    for key in (
        "LUMEN_PROVIDER",
        "LUMEN_MODEL",
        "LUMEN_API_KEY",
        "LUMEN_DATA_DIR",
        "LUMEN_LOG_LEVEL",
        "LUMEN_MAX_CONTEXT_MESSAGES",
        "LUMEN_REQUEST_TIMEOUT",
        "LUMEN_MAX_RETRIES",
    ):
        assert key in content, f"chave ausente no .env.example: {key}"


def test_expected_project_layout_exists():
    expected = [
        "main.py",
        "README.md",
        "requirements.txt",
        ".env.example",
        "LUMEN_STATE.md",
        "docs/ARCHITECTURE.md",
        "docs/ROADMAP.md",
        "data/memory",
        "data/logs",
        "app/ai/provider.py",
        "app/ai/mock.py",
        "app/ai/openai_provider.py",
        "app/ai/gemini_provider.py",
        "app/ai/groq_provider.py",
        "app/ai/together_provider.py",
        "app/ai/types.py",
        "app/config/settings.py",
        "app/config/persona.py",
        "app/config/secrets.py",
        "app/config/user_config.py",
        "app/config/config_service.py",
        "app/core/agent.py",
        "app/planner/__init__.py",
        "app/planner/models.py",
        "app/planner/planner.py",
        "app/executor/__init__.py",
        "app/executor/handlers.py",
        "app/executor/executor.py",
        "app/executor/checkpoints.py",
        "app/executor/retry.py",
        "app/executor/verification.py",
        "app/executor/correction.py",
        "app/memory/store.py",
        "app/memory/sanitization.py",
        "app/memory/records.py",
        "app/memory/record_store.py",
        "app/memory/system.py",
        "app/tasks/manager.py",
        "app/tools/base.py",
        "app/tools/filesystem.py",
        "app/tools/handler.py",
        "app/tools/workspaces.py",
        "app/tools/audit_log.py",
        "app/tools/control.py",
        "app/tools/terminal.py",
        "app/security/permissions.py",
        "app/ui/main_window.py",
        "app/ui/settings_dialog.py",
        "app/ui/tools_dialog.py",
    ]
    for relative in expected:
        assert (PROJECT_ROOT / relative).exists(), f"arquivo ausente: {relative}"
