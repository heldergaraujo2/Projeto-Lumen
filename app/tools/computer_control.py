"""Computer Control tools (MVP).

These are thin, safe facades:
- No OS automation libraries here (guards AST).
- Execution authority remains in LUMEN (permissions + checkpoints + audit).
- Metadata-only audit: never emit screenshot bytes or typed text.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, FrozenSet, Optional
from uuid import uuid4

from app.computer_control.api import CCActionType, CCTarget, ScreenshotInfo
from app.computer_control.scopes import CCLimits, CCScope
from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult

# Operation strings for audit/UX. These are not filesystem operations.
OP_CC_SCOPE = "cc_scope"
OP_CC_SCREENSHOT = "cc_screenshot"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_actions(value: Any) -> FrozenSet[CCActionType] | None:
    if not isinstance(value, list) or not value:
        return None
    actions: set[CCActionType] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        try:
            actions.add(CCActionType(item))
        except Exception:
            return None
    # MVP hard-limit: only SCREENSHOT is supported for now.
    if actions != {CCActionType.SCREENSHOT}:
        return None
    return frozenset(actions)


def _parse_target(**kwargs: Any) -> CCTarget | None:
    app_name = kwargs.get("app_name")
    process_name = kwargs.get("process_name")
    window_title_pattern = kwargs.get("window_title_pattern")

    if app_name is not None and not isinstance(app_name, str):
        return None
    if process_name is not None and not isinstance(process_name, str):
        return None
    if window_title_pattern is not None and not isinstance(window_title_pattern, str):
        return None

    if not (app_name or process_name or window_title_pattern):
        return None

    return CCTarget(
        app_name=(app_name.strip() if isinstance(app_name, str) and app_name.strip() else None),
        process_name=(process_name.strip() if isinstance(process_name, str) and process_name.strip() else None),
        window_title_pattern=(
            window_title_pattern.strip()
            if isinstance(window_title_pattern, str) and window_title_pattern.strip()
            else None
        ),
    )


class ComputerControlTool(StructuredTool):
    """Base class for CC tools (metadata-only audit helper)."""

    _abstract_base = True
    required_permission = PermissionLevel.COMPUTER_CONTROL
    operation: str = OP_CC_SCOPE

    def __init__(self, *, scopes: dict[str, CCScope], audit=None) -> None:
        self._scopes = scopes
        self._audit = audit

    def _audit_record(
        self,
        *,
        success: bool,
        error: str | None = None,
        scope_id: str | None = None,
        action_type: str | None = None,
        artifact_ref: str | None = None,
        duration_ms: int | None = None,
        **detail: Any,
    ) -> None:
        if self._audit is None:
            return
        # requested_path/resolved_path are not applicable to CC.
        self._audit.record(
            tool=self.name,
            operation=self.operation,
            requested_path=None,
            resolved_path=None,
            success=success,
            error=error,
            scope_id=scope_id,
            action_type=action_type,
            artifact_ref=artifact_ref,
            duration_ms=duration_ms,
            **detail,
        )


class CcRequestScopeTool(ComputerControlTool):
    """Creates a CC scope (consent) in memory.

    Notes:
    - No persistence (session-only).
    - MVP supports SCREENSHOT only.
    - This tool itself does not grant permission; it requires COMPUTER_CONTROL permission.
    """

    name = "cc_request_scope"
    description = "Solicita/gera um escopo de Computer Control (MVP: SCREENSHOT)."
    operation = OP_CC_SCOPE

    def run(self, **kwargs: Any) -> ToolResult:
        target = _parse_target(**kwargs)
        actions = _parse_actions(kwargs.get("allowed_actions"))

        expires_in_s = kwargs.get("expires_in_s")
        max_actions_total = kwargs.get("max_actions_total")
        max_actions_per_minute = kwargs.get("max_actions_per_minute")

        if target is None or actions is None:
            self._audit_record(success=False, error="invalid_input")
            return ToolResult(ok=False, error="invalid_input")

        if not isinstance(expires_in_s, int) or expires_in_s <= 0:
            self._audit_record(success=False, error="invalid_input")
            return ToolResult(ok=False, error="invalid_input")

        # Conservative clamp to reduce risk.
        if expires_in_s > 3600:
            expires_in_s = 3600

        if not isinstance(max_actions_total, int) or max_actions_total <= 0:
            self._audit_record(success=False, error="invalid_input")
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(max_actions_per_minute, int) or max_actions_per_minute <= 0:
            self._audit_record(success=False, error="invalid_input")
            return ToolResult(ok=False, error="invalid_input")

        created_at = _now_utc()
        expires_at = created_at + timedelta(seconds=expires_in_s)

        scope_id = str(uuid4())
        limits = CCLimits(
            max_actions_total=max_actions_total,
            max_actions_per_minute=max_actions_per_minute,
        )
        scope = CCScope(
            scope_id=scope_id,
            created_at=created_at,
            expires_at=expires_at,
            target=target,
            allowed_actions=actions,
            limits=limits,
        )
        try:
            scope.validate()
        except Exception as exc:
            self._audit_record(success=False, error=f"invalid_scope:{type(exc).__name__}")
            return ToolResult(ok=False, error="invalid_scope")

        self._scopes[scope_id] = scope
        self._audit_record(success=True, scope_id=scope_id, allowed_actions=[a.value for a in actions])
        return ToolResult(
            ok=True,
            data={
                "scope_id": scope_id,
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "allowed_actions": [a.value for a in actions],
                "target": {
                    "app_name": target.app_name,
                    "process_name": target.process_name,
                    "window_title_pattern": target.window_title_pattern,
                },
                "limits": {
                    "max_actions_total": limits.max_actions_total,
                    "max_actions_per_minute": limits.max_actions_per_minute,
                },
            },
        )
