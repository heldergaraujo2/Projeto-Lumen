"""Testes da abstração de ferramentas (tools) e do registro."""
from __future__ import annotations

import pytest

from app.security.permissions import PermissionDeniedError, PermissionLevel, PermissionManager
from app.tools.base import Tool, ToolError, ToolNotFoundError, ToolRegistry


class EchoTool(Tool):
    """Ferramenta de exemplo (inofensiva) usada apenas nos testes."""

    name = "echo"
    description = "Repete o texto recebido (ferramenta de exemplo/teste)."
    required_permission = PermissionLevel.CHAT

    def execute(self, **kwargs) -> str:
        return str(kwargs.get("text", ""))


class NotebookTool(Tool):
    """Ferramenta de exemplo que exige permissão WRITE."""

    name = "notebook"
    description = "Exemplo que exige permissão WRITE."
    required_permission = PermissionLevel.WRITE

    def execute(self, **kwargs) -> str:
        return "anotado"


def test_tool_is_abstract():
    with pytest.raises(TypeError):
        Tool()  # type: ignore[abstract]


def test_subclass_must_declare_metadata():
    with pytest.raises(ToolError):

        class IncompleteTool(Tool):
            name = "incomplete"
            # sem 'description'
            def execute(self, **kwargs) -> str:
                return ""


def test_registry_executes_tool_with_permission():
    registry = ToolRegistry(PermissionManager())  # CHAT concedido por padrão
    registry.register(EchoTool())
    assert registry.execute("echo", text="olá") == "olá"


def test_registry_blocks_tool_without_permission():
    registry = ToolRegistry(PermissionManager())  # WRITE não concedido
    registry.register(NotebookTool())
    with pytest.raises(PermissionDeniedError):
        registry.execute("notebook", text="segredo")


def test_registry_allows_after_explicit_grant():
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.WRITE)
    registry = ToolRegistry(permissions)
    registry.register(NotebookTool())
    assert registry.execute("notebook") == "anotado"


def test_registry_rejects_duplicate_and_missing():
    registry = ToolRegistry()
    registry.register(EchoTool())

    with pytest.raises(ToolError):
        registry.register(EchoTool())
    with pytest.raises(ToolNotFoundError):
        registry.execute("ferramenta-inexistente")


def test_registry_lists_metadata():
    registry = ToolRegistry()
    registry.register(EchoTool())
    listing = registry.list_tools()
    assert listing == [
        {
            "name": "echo",
            "description": EchoTool.description,
            "required_permission": "CHAT",
        }
    ]
