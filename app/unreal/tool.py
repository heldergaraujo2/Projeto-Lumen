"""Unreal Editor tools exposed to the Planner.

Physical execution remains outside these planning/inspection tools and is
still owned by the ComputerControl security boundary.
"""
from __future__ import annotations

from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult
from app.unreal.integration import UnrealIntegration
from app.unreal.agent import UnrealAgent
from app.unreal.models import UnrealProject


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


class UnrealPlanTool(StructuredTool):
    """Create a validated Unreal workflow plan without executing it.

    This is intentionally non-executing: it gives the planner a structured
    Unreal workflow while physical interaction remains behind the separate
    ComputerControl permission/scope/checkpoint pipeline.
    """

    name = "unreal_plan"
    description = (
        "Planeja uma operação explícita do Unreal Editor sem executá-la. "
        "Suporta salvar, salvar tudo, iniciar/parar PIE e abrir asset/nível."
    )
    required_permission = PermissionLevel.UNREAL

    def __init__(self, agent: UnrealAgent | None = None) -> None:
        self._agent = agent or UnrealAgent()

    def run(
        self,
        *,
        goal: str,
        project_name: str,
        project_root: str,
        engine_version: str | None = None,
    ) -> ToolResult:
        if not isinstance(goal, str) or not goal.strip():
            return ToolResult(ok=False, error="goal deve ser texto não vazio")
        if not isinstance(project_name, str) or not project_name.strip():
            return ToolResult(ok=False, error="project_name deve ser texto não vazio")
        if not isinstance(project_root, str) or not project_root.strip():
            return ToolResult(ok=False, error="project_root deve ser texto não vazio")
        if engine_version is not None and not isinstance(engine_version, str):
            return ToolResult(ok=False, error="engine_version deve ser texto ou nulo")
        try:
            plan = self._agent.plan(
                project=UnrealProject(
                    name=project_name,
                    root=project_root,
                    engine_version=engine_version,
                ),
                goal=goal,
            )
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(
            ok=True,
            data={
                "executed": False,
                "requires_computer_control": plan.requires_computer_control,
                "goal": plan.goal,
                "actions": [
                    {
                        "operation": action.operation.value,
                        "value": action.value,
                        "keys": list(action.keys),
                        "expected": (
                            {
                                "kind": action.expected.kind,
                                "value": action.expected.value,
                            }
                            if action.expected is not None else None
                        ),
                    }
                    for action in plan.actions
                ],
            },
        )
