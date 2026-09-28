from __future__ import annotations
import json
from pathlib import Path
import pytest
from app.computer.api import ScreenRegion
from app.computer.windows_native import NativeWindow, FakeWindowsNativeBackend, WindowsNativeIntelligence
from app.unreal import UnrealDiscovery, UnrealIntegration

def make_project(tmp_path: Path, name: str = "MyGame") -> Path:
    root = tmp_path / name; root.mkdir()
    (root / f"{name}.uproject").write_text(json.dumps({"FileVersion": 3, "EngineAssociation": "5.6"}), encoding="utf-8")
    for d in ("Content", "Source", "Config", "Plugins"): (root / d).mkdir()
    return root

def test_discovery_is_read_only_and_requires_one_uproject(tmp_path):
    project = UnrealDiscovery().discover(make_project(tmp_path))
    assert project.name == "MyGame" and project.engine_association == "5.6"
    assert project.has_content and project.has_source and project.has_config and project.has_plugins

def test_discovery_rejects_multiple_projects(tmp_path):
    root = make_project(tmp_path); (root / "Other.uproject").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"): UnrealDiscovery().discover(root)

def test_discovery_rejects_invalid_descriptor(tmp_path):
    root = tmp_path / "Bad"; root.mkdir(); (root / "Bad.uproject").write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"): UnrealDiscovery().discover(root)

def test_editor_discovery_is_window_scoped(tmp_path):
    project = UnrealDiscovery().discover(make_project(tmp_path))
    editor = NativeWindow(42, "MyGame - Unreal Editor", ScreenRegion(0,0,1280,720), 99, "UnrealEditor.exe", True)
    other = NativeWindow(43, "Browser", ScreenRegion(0,0,1280,720), 100, "browser.exe", True)
    native = WindowsNativeIntelligence(FakeWindowsNativeBackend((other, editor), {42:()}))
    found = UnrealIntegration(native=native).find_editor(project)
    assert found is not None and found.handle == 42

def test_workflow_never_creates_project_and_marks_mutation_for_approval(tmp_path):
    root = make_project(tmp_path); project = UnrealDiscovery().discover(root)
    plan = UnrealIntegration().plan_safe_workflow(project, goal="compile Blueprint")
    assert plan.steps[0].requires_approval is False and plan.steps[2].requires_approval is True
    assert not (root / "LumenCreatedProject.uproject").exists()

def test_windows_editor_discovery_fails_without_backend(tmp_path):
    project = UnrealDiscovery().discover(make_project(tmp_path))
    with pytest.raises(RuntimeError, match="native backend"): UnrealIntegration().find_editor(project)

from app.computer.windows_native import NativeElement

def test_editor_inspection_maps_unreal_surfaces(tmp_path):
    project = UnrealDiscovery().discover(make_project(tmp_path))
    window = NativeWindow(50, "MyGame - Unreal Editor", ScreenRegion(0,0,1600,900), 1, "UnrealEditor.exe", True)
    elements = (
        NativeElement("Content Browser", "Pane", ScreenRegion(0,0,300,300), window=window.target()),
        NativeElement("Blueprint Editor", "Window", ScreenRegion(300,0,600,600), window=window.target()),
        NativeElement("Output Log", "Pane", ScreenRegion(0,600,600,300), window=window.target()),
        NativeElement("Play", "Button", ScreenRegion(900,0,100,40), window=window.target()),
    )
    native = WindowsNativeIntelligence(FakeWindowsNativeBackend((window,), {50: elements}))
    state = UnrealIntegration(native=native).inspect_editor(project, window)
    assert state.content_browser_visible
    assert state.blueprint_editor_visible
    assert state.output_log_visible
    assert state.play_in_editor

def test_operation_allowlist_and_approval(tmp_path):
    project = UnrealDiscovery().discover(make_project(tmp_path))
    integration = UnrealIntegration()
    plan = integration.plan_operation(project, "edit_blueprint")
    assert plan.steps[2].requires_approval
    with pytest.raises(ValueError):
        integration.plan_operation(project, "delete_everything")
