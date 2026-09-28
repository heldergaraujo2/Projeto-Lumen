"""F30 — Unreal Engine project discovery and controlled editor integration.

The module discovers an existing Unreal project and produces bounded workflow
plans. It does not create a second project, silently launch processes, or bypass
ComputerControl permissions/checkpoints.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.computer.api import CCTarget
from app.computer.windows_native import NativeWindow, WindowsNativeIntelligence


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
        if not self.root.is_absolute():
            raise ValueError("Unreal project root must be absolute")
        if self.descriptor != self.root / f"{self.name}.uproject":
            raise ValueError("descriptor must belong to the discovered project root")
        if not self.descriptor.is_file():
            raise ValueError("uproject descriptor does not exist")
        if not self.name.strip():
            raise ValueError("project name is required")


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
        if self.window.handle <= 0:
            raise ValueError("invalid Unreal Editor window handle")


@dataclass(frozen=True)
class UnrealWorkflowStep:
    name: str
    action: str
    target: CCTarget | None = None
    requires_approval: bool = True

    def validate(self) -> None:
        if not self.name.strip() or not self.action.strip():
            raise ValueError("workflow step requires name and action")


@dataclass(frozen=True)
class UnrealWorkflowPlan:
    project: UnrealProject
    goal: str
    steps: tuple[UnrealWorkflowStep, ...]

    def validate(self) -> None:
        self.project.validate()
        if not self.goal.strip() or not self.steps:
            raise ValueError("workflow requires goal and steps")
        for step in self.steps:
            step.validate()


class UnrealDiscovery:
    """Read-only discovery of one explicitly supplied directory."""

    def discover(self, root: str | Path) -> UnrealProject:
        base = Path(root).expanduser().resolve()
        if not base.is_dir():
            raise FileNotFoundError(f"Unreal project directory not found: {base}")
        descriptors = tuple(sorted(base.glob("*.uproject")))
        if len(descriptors) != 1:
            raise ValueError(
                "expected exactly one .uproject in the supplied project root"
            )
        descriptor = descriptors[0]
        try:
            payload = json.loads(descriptor.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("invalid Unreal .uproject descriptor") from exc
        name = descriptor.stem
        engine = payload.get("EngineAssociation")
        project = UnrealProject(
            root=base,
            descriptor=descriptor,
            name=name,
            engine_association=str(engine) if engine is not None else None,
            has_content=(base / "Content").is_dir(),
            has_source=(base / "Source").is_dir(),
            has_config=(base / "Config").is_dir(),
            has_plugins=(base / "Plugins").is_dir(),
            has_saved=(base / "Saved").is_dir(),
        )
        project.validate()
        return project


class UnrealEditorBackend(Protocol):
    def list_windows(self) -> tuple[NativeWindow, ...]: ...


class UnrealIntegration:
    """Bridge between a discovered project and the existing computer-control core."""

    def __init__(
        self,
        *,
        discovery: UnrealDiscovery | None = None,
        native: WindowsNativeIntelligence | None = None,
    ) -> None:
        self.discovery = discovery or UnrealDiscovery()
        self.native = native

    def discover_project(self, root: str | Path) -> UnrealProject:
        return self.discovery.discover(root)

    def find_editor(
        self,
        project: UnrealProject,
        *,
        native: WindowsNativeIntelligence | None = None,
    ) -> NativeWindow | None:
        backend = native or self.native
        if backend is None:
            raise RuntimeError("Windows native backend is required for editor discovery")
        windows = backend.list_windows()
        project_name = project.name.casefold()
        for window in windows:
            title = window.title.casefold()
            if project_name in title and (
                "unreal editor" in title or "editor" in title
            ):
                return window
        return None

    def plan_safe_workflow(
        self,
        project: UnrealProject,
        *,
        goal: str,
        editor: NativeWindow | None = None,
    ) -> UnrealWorkflowPlan:
        project.validate()
        target = editor.target() if editor is not None else CCTarget(
            app_name="Unreal Editor",
            window_title_pattern=project.name,
        )
        plan = UnrealWorkflowPlan(
            project=project,
            goal=goal,
            steps=(
                UnrealWorkflowStep("focus_editor", "focus Unreal Editor", target, False),
                UnrealWorkflowStep("observe_editor", "capture editor state", target, False),
                UnrealWorkflowStep("perform_requested_operation", goal, target, True),
                UnrealWorkflowStep("verify_result", "verify requested Unreal state", target, False),
            ),
        )
        plan.validate()
        return plan
