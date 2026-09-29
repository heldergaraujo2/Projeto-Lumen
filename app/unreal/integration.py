"""F30 — Unreal Engine project discovery and controlled editor integration."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from app.computer_control.api import CCTarget
from app.computer.models import ComputerObservation
from app.computer.windows_native import NativeElement, NativeWindow, WindowsNativeIntelligence
from .mcp import MCPResponse, UnrealMCPClient
from .slate import SlateGroundingAdapter

@dataclass(frozen=True)
class UnrealProject:
    root: Path
    descriptor: Path
    name: str
    engine_association: str | None
    has_content: bool
    has_source: bool
    has_config: bool
    has_plugins: bool
    has_saved: bool
    def validate(self) -> None:
        if not self.root.is_absolute(): raise ValueError("Unreal project root must be absolute")
        if self.descriptor != self.root / f"{self.name}.uproject": raise ValueError("descriptor must belong to the discovered project root")
        if not self.descriptor.is_file(): raise ValueError("uproject descriptor does not exist")
        if not self.name.strip(): raise ValueError("project name is required")

@dataclass(frozen=True)
class UnrealEditorState:
    window: NativeWindow
    project: UnrealProject
    content_browser_visible: bool = False
    blueprint_editor_visible: bool = False
    output_log_visible: bool = False
    play_in_editor: bool = False
    def validate(self) -> None:
        self.project.validate()
        if self.window.handle <= 0: raise ValueError("invalid Unreal Editor window handle")

@dataclass(frozen=True)
class UnrealWorkflowStep:
    name: str
    action: str
    target: CCTarget | None = None
    requires_approval: bool = True
    def validate(self) -> None:
        if not self.name.strip() or not self.action.strip(): raise ValueError("workflow step requires name and action")

@dataclass(frozen=True)
class UnrealWorkflowPlan:
    project: UnrealProject
    goal: str
    steps: tuple[UnrealWorkflowStep, ...]
    def validate(self) -> None:
        self.project.validate()
        if not self.goal.strip() or not self.steps: raise ValueError("workflow requires goal and steps")
        for step in self.steps: step.validate()

class UnrealDiscovery:
    def discover(self, root: str | Path) -> UnrealProject:
        base = Path(root).expanduser().resolve()
        if not base.is_dir(): raise FileNotFoundError(f"Unreal project directory not found: {base}")
        descriptors = tuple(sorted(base.glob("*.uproject")))
        if len(descriptors) != 1: raise ValueError("expected exactly one .uproject in the supplied project root")
        descriptor = descriptors[0]
        try: payload = json.loads(descriptor.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise ValueError("invalid Unreal .uproject descriptor") from exc
        project = UnrealProject(
            base, descriptor, descriptor.stem,
            str(payload["EngineAssociation"]) if payload.get("EngineAssociation") is not None else None,
            (base/"Content").is_dir(), (base/"Source").is_dir(), (base/"Config").is_dir(),
            (base/"Plugins").is_dir(), (base/"Saved").is_dir())
        project.validate()
        return project

class UnrealEditorBackend(Protocol):
    def list_windows(self) -> tuple[NativeWindow, ...]: ...

class UnrealIntegration:
    """Bridge to the existing ComputerControl security boundary; no direct execution."""
    _KNOWN_LABELS = {
        "content_browser": ("content browser",),
        "blueprint": ("blueprint",),
        "output_log": ("output log",),
        "play": ("play",),
        "stop": ("stop",),
    }
    def __init__(self, *, discovery: UnrealDiscovery | None = None, native: WindowsNativeIntelligence | None = None, mcp: UnrealMCPClient | None = None):
        self.discovery = discovery or UnrealDiscovery()
        self.native = native
        self.mcp = mcp

    def discover_project(self, root: str | Path) -> UnrealProject:
        return self.discovery.discover(root)

    def mcp_observe(self, *, ref: str, max_depth: int = 30) -> MCPResponse:
        """Register/refresh a Slate observer without performing UI input."""
        if self.mcp is None:
            raise RuntimeError("Unreal MCP client is required for Slate observation")
        if not ref.strip():
            raise ValueError("ref is required for Slate observation")
        if max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        return self.mcp.call_toolset_tool(
            "SlateInspectorToolset.SlateInspectorToolset",
            "Observe",
            {"ref": ref, "maxDepth": max_depth},
        )

    def mcp_slate_observation(
        self,
        *,
        ref: str = "",
        max_depth: int = 30,
        width: int,
        height: int,
        window: CCTarget | None = None,
        include_source_locations: bool = False,
    ) -> ComputerObservation:
        """Convert a read-only Slate snapshot into the shared perception model."""
        if width <= 0 or height <= 0:
            raise ValueError("observation dimensions must be positive")
        response = self.mcp_snapshot(
            ref=ref,
            max_depth=max_depth,
            include_source_locations=include_source_locations,
        )
        if response.is_error:
            raise RuntimeError(f"Unreal MCP snapshot failed: {response.error}")
        targets = SlateGroundingAdapter().targets_from_snapshot(response.result, window=window)
        observation = ComputerObservation(
            width=width,
            height=height,
            elements=targets,
            active_window=window,
        )
        observation.validate()
        return observation

    def mcp_snapshot(self, *, ref: str = "", max_depth: int = 30, include_source_locations: bool = False) -> MCPResponse:
        """Read the real Unreal Slate tree through MCP; never performs UI input."""
        if self.mcp is None:
            raise RuntimeError("Unreal MCP client is required for Slate snapshot")
        if max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        return self.mcp.call_toolset_tool(
            "SlateInspectorToolset.SlateInspectorToolset",
            "Snapshot",
            {
                "ref": ref,
                "maxDepth": max_depth,
                "bIncludeSourceLocations": include_source_locations,
            },
        )

    def find_editor(self, project: UnrealProject, *, native: WindowsNativeIntelligence | None = None) -> NativeWindow | None:
        backend = native or self.native
        if backend is None: raise RuntimeError("Windows native backend is required for editor discovery")
        for window in backend.list_windows():
            title = window.title.casefold()
            if project.name.casefold() in title and ("unreal editor" in title or "editor" in title): return window
        return None

    def inspect_editor(self, project: UnrealProject, window: NativeWindow, *, native: WindowsNativeIntelligence | None = None, max_depth: int = 8, max_elements: int = 256) -> UnrealEditorState:
        backend = native or self.native
        if backend is None: raise RuntimeError("Windows native backend is required for editor inspection")
        elements = backend.inspect_window(window, max_depth=max_depth, max_elements=max_elements)
        labels = tuple((e.name or "").casefold() for e in elements)
        has = lambda key: any(any(token in label for token in self._KNOWN_LABELS[key]) for label in labels)
        state = UnrealEditorState(window, project, has("content_browser"), has("blueprint"), has("output_log"), has("play") and not has("stop"))
        state.validate()
        return state

    def plan_operation(self, project: UnrealProject, operation: str, *, editor: NativeWindow | None = None) -> UnrealWorkflowPlan:
        project.validate()
        allowed = {"open_content_browser","edit_blueprint","edit_cpp","build","compile","play","stop","inspect_logs","recover"}
        if operation not in allowed: raise ValueError("unsupported Unreal operation")
        target = editor.target() if editor else CCTarget(app_name="Unreal Editor", window_title_pattern=project.name)
        destructive = operation in {"edit_blueprint","edit_cpp","build","compile","play","stop","recover"}
        steps = [
            UnrealWorkflowStep("focus_editor","focus Unreal Editor",target,False),
            UnrealWorkflowStep("observe_editor","inspect Unreal Editor state",target,False),
            UnrealWorkflowStep(operation,operation.replace("_"," "),target,destructive),
            UnrealWorkflowStep("verify","verify Unreal Editor state after operation",target,False),
        ]
        plan = UnrealWorkflowPlan(project, operation, tuple(steps)); plan.validate(); return plan

    def plan_safe_workflow(self, project: UnrealProject, *, goal: str, editor: NativeWindow | None = None) -> UnrealWorkflowPlan:
        project.validate()
        target = editor.target() if editor else CCTarget(app_name="Unreal Editor", window_title_pattern=project.name)
        plan = UnrealWorkflowPlan(project, goal, (
            UnrealWorkflowStep("focus_editor","focus Unreal Editor",target,False),
            UnrealWorkflowStep("observe_editor","capture editor state",target,False),
            UnrealWorkflowStep("perform_requested_operation",goal,target,True),
            UnrealWorkflowStep("verify_result","verify requested Unreal state",target,False)))
        plan.validate(); return plan
