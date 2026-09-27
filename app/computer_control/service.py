from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic

from app.security.permissions import PermissionLevel, PermissionManager
from .actions import CCActionRequest, action_point
from .api import CCActionType, ComputerControlDriver
from .audit import CCAuditEvent, make_cc_audit_event
from .policy import CCDecision, evaluate_cc_action
from .scopes import CCScope


@dataclass(frozen=True)
class CCCheckpoint:
    id: str
    scope_id: str
    request_fingerprint: str
    action: CCActionType
    created_at: datetime
    status: str = "PENDING_APPROVAL"
    decided_at: datetime | None = None
    note: str = ""

    def validate(self) -> None:
        if not self.id.strip() or not self.scope_id.strip() or not self.request_fingerprint.strip():
            raise ValueError("invalid computer-control checkpoint")
        if self.status not in {"PENDING_APPROVAL", "APPROVED", "REFUSED", "CONSUMED"}:
            raise ValueError("invalid computer-control checkpoint status")
        if self.created_at.tzinfo is None:
            raise ValueError("checkpoint timestamp must be timezone-aware")

    @property
    def pending(self) -> bool:
        return self.status == "PENDING_APPROVAL"


@dataclass(frozen=True)
class CCExecutionResult:
    success: bool
    decision: CCDecision
    audit: CCAuditEvent
    error: str | None = None
    checkpoint: CCCheckpoint | None = None


def _request_fingerprint(scope: CCScope, request: CCActionRequest) -> str:
    request.validate()
    target = request.target
    payload = {
        "scope_id": scope.scope_id,
        "action": request.action.value,
        "x": request.x,
        "y": request.y,
        "target": (
            {
                "label": target.label,
                "source": target.source.value,
                "confidence": target.confidence,
                "x": target.x,
                "y": target.y,
                "width": target.width,
                "height": target.height,
            }
            if target is not None
            else None
        ),
        "text_present": request.text is not None,
        "text_length": len(request.text or ""),
        "keys": request.keys,
        "delta": request.delta,
        "region": (
            [request.region.x, request.region.y, request.region.width, request.region.height]
            if request.region
            else None
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class ComputerControlService:
    """Secure physical-execution boundary.

    Every action requires:
    PermissionManager(COMPUTER_CONTROL)
    -> policy
    -> scope
    -> one-shot checkpoint approval
    -> driver
    -> metadata-only audit.
    """

    def __init__(
        self,
        *,
        permissions: PermissionManager,
        driver: ComputerControlDriver,
        require_checkpoint: bool = True,
    ):
        self.permissions = permissions
        self.driver = driver
        self.require_checkpoint = require_checkpoint
        self._counter = 0
        self._checkpoints: dict[str, CCCheckpoint] = {}

    def prepare(self, *, scope: CCScope, request: CCActionRequest) -> CCExecutionResult:
        request.validate()
        decision = self._policy(scope, request)
        if not decision.allowed:
            return self._denied(scope, request, decision)
        self._counter += 1
        checkpoint = CCCheckpoint(
            id=f"CC-CP-{self._counter:06d}",
            scope_id=scope.scope_id,
            request_fingerprint=_request_fingerprint(scope, request),
            action=request.action,
            created_at=datetime.now(timezone.utc),
        )
        checkpoint.validate()
        self._checkpoints[checkpoint.id] = checkpoint
        audit = make_cc_audit_event(
            operation="computer_control",
            scope_id=scope.scope_id,
            action_type=request.action,
            decision="denied",
            denied_reason="checkpoint_required",
        )
        return CCExecutionResult(False, decision, audit, "checkpoint_required", checkpoint)

    def approve(
        self,
        checkpoint_id: str,
        *,
        scope: CCScope,
        request: CCActionRequest,
        note: str = "",
    ) -> CCExecutionResult:
        request.validate()
        checkpoint = self._checkpoints.get(checkpoint_id)
        if checkpoint is None:
            return self._checkpoint_failure(scope, request, "checkpoint_not_found")
        if checkpoint.scope_id != scope.scope_id:
            return self._checkpoint_failure(scope, request, "checkpoint_scope_mismatch")
        if checkpoint.request_fingerprint != _request_fingerprint(scope, request):
            return self._checkpoint_failure(scope, request, "checkpoint_request_mismatch")
        if not checkpoint.pending:
            return self._checkpoint_failure(scope, request, "checkpoint_not_pending")
        decision = self._policy(scope, request)
        if not decision.allowed:
            self._checkpoints.pop(checkpoint_id, None)
            return self._denied(scope, request, decision)
        approved = CCCheckpoint(
            checkpoint.id, checkpoint.scope_id, checkpoint.request_fingerprint,
            checkpoint.action, checkpoint.created_at, "APPROVED",
            datetime.now(timezone.utc), note,
        )
        self._checkpoints[checkpoint_id] = approved
        result = self._execute(scope=scope, request=request, decision=decision, checkpoint=approved)
        consumed = CCCheckpoint(
            approved.id, approved.scope_id, approved.request_fingerprint,
            approved.action, approved.created_at, "CONSUMED",
            approved.decided_at, approved.note,
        )
        self._checkpoints[checkpoint_id] = consumed
        return CCExecutionResult(
            result.success, result.decision, result.audit, result.error, consumed
        )

    def refuse(self, checkpoint_id: str, *, note: str = "") -> CCCheckpoint:
        checkpoint = self._checkpoints.get(checkpoint_id)
        if checkpoint is None:
            raise KeyError(checkpoint_id)
        if not checkpoint.pending:
            raise ValueError("checkpoint is not pending")
        refused = CCCheckpoint(
            checkpoint.id, checkpoint.scope_id, checkpoint.request_fingerprint,
            checkpoint.action, checkpoint.created_at, "REFUSED",
            datetime.now(timezone.utc), note,
        )
        self._checkpoints[checkpoint_id] = refused
        return refused

    def get_checkpoint(self, checkpoint_id: str) -> CCCheckpoint | None:
        return self._checkpoints.get(checkpoint_id)

    def execute(
        self,
        *,
        scope: CCScope,
        request: CCActionRequest,
        approved_checkpoint_id: str | None = None,
    ) -> CCExecutionResult:
        request.validate()
        decision = self._policy(scope, request)
        if not decision.allowed:
            return self._denied(scope, request, decision)
        if self.require_checkpoint:
            if approved_checkpoint_id is None:
                return self.prepare(scope=scope, request=request)
            return self.approve(
                approved_checkpoint_id, scope=scope, request=request
            )
        return self._execute(scope=scope, request=request, decision=decision, checkpoint=None)

    def _policy(self, scope: CCScope, request: CCActionRequest) -> CCDecision:
        return evaluate_cc_action(
            has_computer_control_permission=self.permissions.is_granted(
                PermissionLevel.COMPUTER_CONTROL
            ),
            scope=scope,
            action=request.action,
            now=datetime.now(timezone.utc),
        )

    def _denied(self, scope, request, decision):
        audit = make_cc_audit_event(
            operation="computer_control",
            scope_id=scope.scope_id,
            action_type=request.action,
            decision="denied",
            denied_reason=decision.reason,
        )
        return CCExecutionResult(False, decision, audit, decision.reason)

    def _checkpoint_failure(self, scope, request, reason):
        decision = CCDecision(False, reason, scope.scope_id)
        return self._denied(scope, request, decision)

    def _execute(self, *, scope, request, decision, checkpoint):
        start = monotonic()
        try:
            self._execute_driver(scope, request)
            scope.consume_action(now=datetime.now(timezone.utc))
            audit = make_cc_audit_event(
                operation="computer_control",
                scope_id=scope.scope_id,
                action_type=request.action,
                decision="allowed",
                duration_ms=int((monotonic() - start) * 1000),
            )
            return CCExecutionResult(True, decision, audit, checkpoint=checkpoint)
        except Exception as exc:
            audit = make_cc_audit_event(
                operation="computer_control",
                scope_id=scope.scope_id,
                action_type=request.action,
                decision="allowed",
                denied_reason="execution_failed",
                duration_ms=int((monotonic() - start) * 1000),
            )
            return CCExecutionResult(False, decision, audit, str(exc), checkpoint)

    def _execute_driver(self, scope, request):
        if request.action == CCActionType.SCREENSHOT:
            self.driver.screenshot(
                target=scope.target,
                region=request.region or scope.allowed_region,
            )
            return
        if request.action == CCActionType.WINDOW_FOCUS:
            self.driver.focus_window(scope.target)
            return
        if request.action in {
            CCActionType.MOUSE_MOVE,
            CCActionType.MOUSE_CLICK,
            CCActionType.MOUSE_DOUBLE_CLICK,
            CCActionType.MOUSE_RIGHT_CLICK,
        }:
            x, y = action_point(request)
            if not scope.allows_point(x, y):
                raise PermissionError("point outside authorized region")
            if request.action == CCActionType.MOUSE_MOVE:
                self.driver.mouse_move(x, y)
            elif request.action == CCActionType.MOUSE_CLICK:
                self.driver.mouse_click(x, y)
            elif request.action == CCActionType.MOUSE_DOUBLE_CLICK:
                self.driver.mouse_double_click(x, y)
            else:
                self.driver.mouse_click(x, y, button="right")
            return
        if request.action == CCActionType.SCROLL:
            self.driver.scroll(request.delta or 0)
            return
        if request.action == CCActionType.KEY_PRESS:
            self.driver.key_press(request.keys[0])
            return
        if request.action == CCActionType.KEY_COMBO:
            self.driver.key_combo(request.keys)
            return
        if request.action == CCActionType.KEY_TYPE:
            self.driver.type_text(request.text or "")
            return
        raise NotImplementedError(request.action.value)
