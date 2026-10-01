from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.computer_control.api import CCTarget
from app.computer_control.verification import VerificationExpectation
from app.computer.models import ActionPlan


class UnrealOperation(str, Enum):
    FOCUS_EDITOR = "focus_editor"
    OPEN_ASSET = "open_asset"
    OPEN_LEVEL = "open_level"
    SAVE = "save"
    SAVE_ALL = "save_all"
    PLAY = "play_in_editor"
    STOP_PLAY = "stop_play"


class UnrealRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"


@dataclass(frozen=True)
class UnrealProject:
    name: str
    root: str
    engine_version: str | None = None
    # The default target remains explicit and resolvable by both the native
    # perception layer and the Windows driver: app identity plus title pattern.
    # Callers may still provide a narrower process/title/handle target.
    editor_window: CCTarget = field(
        default_factory=lambda: CCTarget(
            app_name="UnrealEditor",
            window_title_pattern=r"Unreal Editor",
        )
    )

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Unreal project name is required")
        if not self.root.strip():
            raise ValueError("Unreal project root is required")
        if self.engine_version is not None and not self.engine_version.strip():
            raise ValueError("engine_version cannot be blank")


@dataclass(frozen=True)
class UnrealAction:
    operation: UnrealOperation
    value: str | None = None
    keys: tuple[str, ...] = ()
    expected: VerificationExpectation | None = None
    risk: UnrealRisk = UnrealRisk.LOW
    rationale: str = ""

    def validate(self) -> None:
        if self.operation in {UnrealOperation.OPEN_ASSET, UnrealOperation.OPEN_LEVEL} and not (self.value or "").strip():
            raise ValueError("asset/level operation requires a value")
        if self.operation in {UnrealOperation.FOCUS_EDITOR, UnrealOperation.SAVE, UnrealOperation.SAVE_ALL, UnrealOperation.PLAY, UnrealOperation.STOP_PLAY} and self.value:
            raise ValueError("operation does not accept a value")
        if self.expected is not None:
            self.expected.validate()


@dataclass(frozen=True)
class UnrealPlan:
    project: UnrealProject
    goal: str
    actions: tuple[UnrealAction, ...]
    action_plan: ActionPlan | None = None

    def validate(self) -> None:
        self.project.validate()
        if not self.goal.strip():
            raise ValueError("goal is required")
        if not self.actions:
            raise ValueError("plan must contain at least one action")
        for action in self.actions:
            action.validate()

    @property
    def requires_computer_control(self) -> bool:
        return bool(self.actions)
