"""F23 — detecção determinística de capacidade do ambiente.

Este módulo NÃO executa mouse, teclado, UI Automation, processos ou Unreal.
Ele somente descreve capacidades observáveis do processo atual. A ausência
de uma capacidade nunca é convertida em um falso PASS.
"""
from __future__ import annotations

import os
import platform
import sys
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EnvironmentCapabilities:
    os_name: str
    platform: str
    python: str
    interactive_session: bool
    display_available: bool
    windows_native: bool
    physical_validation_allowed: bool
    unreal_validation_allowed: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_environment() -> EnvironmentCapabilities:
    """Observa somente o ambiente; não cria efeitos colaterais."""
    windows = sys.platform == "win32"
    # DISPLAY/WAYLAND_DISPLAY indicam uma sessão gráfica em Unix. No Windows,
    # a presença de um processo interativo é suficiente para este gate básico;
    # isso NÃO prova que UIA, mouse, teclado ou Unreal estejam disponíveis.
    display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    interactive = bool(getattr(sys, "stdin", None) and getattr(sys.stdin, "isatty", lambda: False)())
    if windows:
        display = True
    return EnvironmentCapabilities(
        os_name=os.name,
        platform=platform.system(),
        python=platform.python_version(),
        interactive_session=interactive,
        display_available=display,
        windows_native=windows,
        physical_validation_allowed=False,
        unreal_validation_allowed=False,
    )


def physical_validation_status(capabilities: EnvironmentCapabilities) -> str:
    """Retorna o estado do gate físico sem inferência otimista."""
    if not capabilities.physical_validation_allowed:
        return "NOT_EXECUTED"
    return "EXECUTED"


def unreal_validation_status(capabilities: EnvironmentCapabilities) -> str:
    """Retorna o estado do gate Unreal sem confundir Windows com Unreal."""
    if not capabilities.unreal_validation_allowed:
        return "NOT_EXECUTED"
    return "EXECUTED"
