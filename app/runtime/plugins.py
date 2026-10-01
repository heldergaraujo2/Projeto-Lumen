"""Descoberta segura dos componentes da instalação da Lumen."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import importlib
import socket
from typing import Callable

class PluginStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"

@dataclass(frozen=True)
class PluginDescriptor:
    id: str
    name: str
    module: str
    description: str
    required: bool = False
    check: Callable[[], bool] | None = None

@dataclass(frozen=True)
class PluginReport:
    descriptor: PluginDescriptor
    status: PluginStatus
    detail: str
    def to_dict(self) -> dict[str, object]:
        return {"id": self.descriptor.id, "name": self.descriptor.name,
                "status": self.status.value, "detail": self.detail,
                "required": self.descriptor.required}

def _module_available(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False

def _ollama_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.35):
            return True
    except OSError:
        return False

def _mcp_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8000), timeout=0.35):
            return True
    except OSError:
        return False

class PluginManager:
    """Registro fechado dos componentes built-in e diagnóstico read-only."""
    def __init__(self) -> None:
        self._descriptors = (
            PluginDescriptor("computer_control", "Computer Control",
                "app.computer_control.service",
                "Controle físico protegido por permissão, scope, checkpoint e auditoria.", True),
            PluginDescriptor("web_research", "Web Research", "app.web.tools",
                "Pesquisa web com política de segurança.", True),
            PluginDescriptor("unreal", "Unreal Integration", "app.unreal.integration",
                "Integração Unreal com MCP/Slate e Computer Control protegido."),
            PluginDescriptor("ollama", "Ollama", "app.ai.ollama_provider",
                "Provider local; serviço externo à Lumen.", False, _ollama_available),
            PluginDescriptor("mcp", "Unreal MCP", "app.unreal.mcp",
                "Canal MCP local da integração Unreal.", False, _mcp_available),
        )

    @property
    def descriptors(self) -> tuple[PluginDescriptor, ...]:
        return self._descriptors

    def discover(self) -> tuple[PluginReport, ...]:
        reports = []
        for descriptor in self._descriptors:
            if not _module_available(descriptor.module):
                reports.append(PluginReport(descriptor, PluginStatus.UNAVAILABLE, "módulo indisponível"))
                continue
            if descriptor.check is None:
                reports.append(PluginReport(descriptor, PluginStatus.AVAILABLE, "componente carregável"))
                continue
            try:
                online = descriptor.check()
            except Exception as exc:
                reports.append(PluginReport(descriptor, PluginStatus.DEGRADED, f"diagnóstico falhou: {exc}"))
                continue
            reports.append(PluginReport(
                descriptor,
                PluginStatus.AVAILABLE if online else PluginStatus.DEGRADED,
                "serviço local acessível" if online else "componente instalado, serviço local não acessível",
            ))
        return tuple(reports)

    def summary(self) -> tuple[dict[str, object], ...]:
        return tuple(report.to_dict() for report in self.discover())
