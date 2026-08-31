"""Configuração da Lumen (settings + logging + persona + cofre + serviço)."""

from app.config.config_service import (
    ConfigService,
    ConnectionTestResult,
    InvalidAIConfig,
)
from app.config.persona import DEFAULT_PERSONA, Persona, build_system_prompt
from app.config.secrets import (
    API_KEY_NAME,
    FileSecretStore,
    KeyringSecretStore,
    SecretStore,
    SecretStoreError,
    create_secret_store,
)
from app.config.settings import ConfigError, Settings, setup_logging
from app.config.user_config import (
    UserConfigError,
    UserConfigStore,
    apply_user_overrides,
    resolve_api_key,
)

__all__ = [
    "API_KEY_NAME",
    "ConfigError",
    "ConfigService",
    "ConnectionTestResult",
    "DEFAULT_PERSONA",
    "FileSecretStore",
    "InvalidAIConfig",
    "KeyringSecretStore",
    "Persona",
    "SecretStore",
    "SecretStoreError",
    "Settings",
    "UserConfigError",
    "UserConfigStore",
    "apply_user_overrides",
    "build_system_prompt",
    "create_secret_store",
    "resolve_api_key",
    "setup_logging",
]
