"""Configuração da ponte com o Unreal Editor (Fase 4).

Tudo vem de variáveis de ambiente, com defaults que funcionam numa
instalação padrão do Unreal (Remote Control API na porta 30010, local).

Nenhuma configuração aqui abre porta nem altera o projeto Unreal: o
editor é quem precisa ter o plugin habilitado (ver ``TESTE_LOCAL.md``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

#: Porta padrão do servidor HTTP da Remote Control API.
DEFAULT_RC_PORT = 30010

#: Host padrão. Só local: a RC API **não tem autenticação** — expor isso
#: na rede entrega controle total do editor para qualquer um que alcance
#: a porta. Ver "Security" em TESTE_LOCAL.md.
DEFAULT_RC_HOST = "127.0.0.1"

DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 300.0

#: Modos de transporte:
#: - ``rc``     : só a Remote Control API (o que a doc oficial cobre);
#: - ``python`` : exige o Python Editor Script Plugin (necessário para
#:                criar Blueprints — a RC API não tem rota para isso);
#: - ``auto``   : RC API sempre; Python só quando a rota existir.
TRANSPORTS = ("rc", "python", "auto")


class UnrealBridgeError(RuntimeError):
    """Falha de configuração ou de comunicação com o Unreal Editor."""


class UnrealUnavailableError(UnrealBridgeError):
    """O editor não respondeu — provavelmente fechado ou sem o plugin."""


@dataclass(frozen=True)
class UnrealBridgeConfig:
    """Parâmetros de conexão com o editor.

    Args:
        host: host do servidor HTTP da RC API.
        port: porta (30010 é o default da Epic).
        timeout: segundos por requisição.
        transport: ``rc`` | ``python`` | ``auto`` (ver :data:`TRANSPORTS`).
        python_class_path: caminho do objeto que expõe a execução de Python
            no editor. É o ``UObject`` da biblioteca do Python Editor Script
            Plugin; o valor abaixo é o caminho canônico do plugin.
        verify_on_start: faz ``GET /remote/info`` na primeira operação para
            falhar cedo e com mensagem clara em vez de estourar timeout.
    """

    host: str = DEFAULT_RC_HOST
    port: int = DEFAULT_RC_PORT
    timeout: float = DEFAULT_TIMEOUT
    transport: str = "auto"
    python_class_path: str = "/Script/PythonScriptPlugin.Default__PythonScriptLibrary"
    verify_on_start: bool = True

    def __post_init__(self) -> None:
        if self.transport not in TRANSPORTS:
            raise UnrealBridgeError(
                f"transporte inválido: {self.transport!r} (use um de {TRANSPORTS})"
            )
        if not 1 <= int(self.port) <= 65535:
            raise UnrealBridgeError(f"porta inválida: {self.port!r}")
        if not 0 < float(self.timeout) <= MAX_TIMEOUT:
            raise UnrealBridgeError(
                f"timeout deve estar entre 0 e {MAX_TIMEOUT}s (recebido {self.timeout!r})"
            )
        if not str(self.host).strip():
            raise UnrealBridgeError("host não pode ser vazio")

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{int(self.port)}"

    @property
    def python_enabled(self) -> bool:
        """Se o transporte pode usar o Python Editor Script Plugin."""
        return self.transport in ("python", "auto")

    @property
    def python_required(self) -> bool:
        return self.transport == "python"

    def endpoint(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @classmethod
    def from_env(cls, environ: dict | None = None) -> "UnrealBridgeConfig":
        """Lê ``LUMEN_UNREAL_*`` do ambiente, com defaults seguros."""
        env = os.environ if environ is None else environ

        def raw(name: str, default: str) -> str:
            value = env.get(name)
            return default if value is None or not str(value).strip() else str(value).strip()

        def number(name: str, default: float) -> float:
            value = raw(name, str(default))
            try:
                return float(value)
            except ValueError as exc:
                raise UnrealBridgeError(
                    f"{name} deve ser numérico (recebido {value!r})"
                ) from exc

        port = number("LUMEN_UNREAL_RC_PORT", DEFAULT_RC_PORT)
        return cls(
            host=raw("LUMEN_UNREAL_RC_HOST", DEFAULT_RC_HOST),
            port=int(port),
            timeout=number("LUMEN_UNREAL_TIMEOUT", DEFAULT_TIMEOUT),
            transport=raw("LUMEN_UNREAL_TRANSPORT", "auto").lower(),
        )


__all__ = [
    "DEFAULT_RC_HOST",
    "DEFAULT_RC_PORT",
    "DEFAULT_TIMEOUT",
    "MAX_TIMEOUT",
    "TRANSPORTS",
    "UnrealBridgeConfig",
    "UnrealBridgeError",
    "UnrealUnavailableError",
]
