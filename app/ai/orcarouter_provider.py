"""OpenAI-compatible provider for OrcaRouter, including DeepSeek V4.1 Flash Free.

The API key is stored through Lumen's existing secret store. The endpoint is
fixed to OrcaRouter so the UI never needs to persist a custom URL or expose a
credential in a regular settings file.
"""
from __future__ import annotations

from typing import Any

from app.ai.openai_provider import OpenAIProvider
from app.ai.provider import ProviderDependencyError

DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash-free"
BASE_URL = "https://api.orcarouter.ai/v1"


class OrcaRouterProvider(OpenAIProvider):
    """OpenAI-compatible API gateway provider for OrcaRouter."""

    name = "orcarouter"

    @staticmethod
    def _default_client_factory(api_key: str, timeout: float) -> Any:
        try:
            import openai
        except ImportError as exc:
            raise ProviderDependencyError(
                "Dependência 'openai' não instalada. Execute: pip install -r requirements.txt"
            ) from exc
        return openai.OpenAI(
            api_key=api_key,
            base_url=BASE_URL,
            timeout=timeout,
            max_retries=0,
        )

    def __init__(self, settings=None, client_factory=None, retry_backoff: float = 0.5) -> None:
        super().__init__(settings, client_factory=client_factory, retry_backoff=retry_backoff)
        if not self._model:
            self._model = DEFAULT_MODEL
