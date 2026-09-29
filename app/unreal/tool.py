"""F30 read-only Unreal MCP tool."""
from __future__ import annotations

from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult
from app.unreal.integration import UnrealIntegration


class UnrealSnapshotTool(StructuredTool):
    name = "unreal_snapshot"
    description = "Inspeciona o Unreal Editor via MCP/Slate Inspector em modo somente leitura."
    required_permission = PermissionLevel.COMPUTER_CONTROL

    def __init__(self, integration: UnrealIntegration) -> None:
        self._integration = integration

    def run(self, *, ref: str = "", max_depth: int = 30, include_source_locations: bool = False) -> ToolResult:
        response = self._integration.mcp_snapshot(ref=ref, max_depth=max_depth, include_source_locations=include_source_locations)
        if response.is_error:
            return ToolResult(ok=False, data={"mcp_error": response.error or {}}, error="Unreal MCP retornou erro")
        return ToolResult(ok=True, data={"read_only": True, "result": response.result})
