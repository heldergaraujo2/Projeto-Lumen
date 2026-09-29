"""F30 — read-only Unreal Editor inspection tool exposed to the Planner."""
from __future__ import annotations

from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult
from app.unreal.integration import UnrealIntegration


class UnrealSnapshotTool(StructuredTool):
    """Capture the Unreal Slate tree through the controlled MCP integration.

    This tool is deliberately read-only. It cannot click, type, save, build,
    compile, play, or otherwise mutate Unreal. Physical interaction remains
    the responsibility of ComputerControlService.
    """

    name = "unreal_snapshot"
    description = (
        "Inspeciona o Unreal Editor por MCP/Slate Inspector e retorna um "
        "snapshot somente leitura da árvore Slate."
    )
    required_permission = PermissionLevel.COMPUTER_CONTROL

    def __init__(self, integration: UnrealIntegration) -> None:
        if not isinstance(integration, UnrealIntegration):
            raise TypeError("UnrealSnapshotTool exige UnrealIntegration")
        self._integration = integration

    def run(
        self,
        *,
        ref: str = "",
        max_depth: int = 30,
        include_source_locations: bool = False,
    ) -> ToolResult:
        if not isinstance(ref, str):
            return ToolResult(ok=False, error="ref deve ser texto")
        if isinstance(max_depth, bool) or not isinstance(max_depth, int):
            return ToolResult(ok=False, error="max_depth deve ser inteiro")
        if max_depth < 0 or max_depth > 100:
            return ToolResult(ok=False, error="max_depth deve estar entre 0 e 100")
        if not isinstance(include_source_locations, bool):
            return ToolResult(ok=False, error="include_source_locations deve ser booleano")
        try:
            response = self._integration.mcp_snapshot(
                ref=ref,
                max_depth=max_depth,
                include_source_locations=include_source_locations,
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Unreal MCP indisponível: {exc}")
        if response.is_error:
            return ToolResult(
                ok=False,
                data={"mcp_error": response.error or {}},
                error="Unreal MCP retornou erro de protocolo",
            )
        return ToolResult(
            ok=True,
            data={
                "read_only": True,
                "protocol": "MCP",
                "toolset": "SlateInspectorToolset.SlateInspectorToolset",
                "tool": "Snapshot",
                "result": response.result,
            },
        )
