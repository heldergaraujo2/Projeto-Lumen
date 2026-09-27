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


OP_CC_MOUSE_MOVE = "cc_mouse_move"

OP_CC_MOUSE_CLICK = "cc_mouse_click"
OP_CC_MOUSE_CLICK_AT = "cc_mouse_click_at"
OP_CC_MOUSE_MOVE_TO = "cc_mouse_move_to"
OP_CC_CLICK_TEMPLATE = "cc_click_template"
OP_CC_CLICK_TEMPLATE_LIVE = "cc_click_template_live"
OP_CC_CLICK_TARGET_LIVE = "cc_click_target_live"
OP_CC_KEY_TYPE = "cc_key_type"
OP_CC_DOUBLE_CLICK_AND_TYPE = "cc_double_click_and_type"
OP_CC_WINDOW_FOCUS = "cc_window_focus"
OP_CC_WINDOW_WAIT = "cc_window_wait"
OP_CC_LOCATE_TEMPLATE = "cc_locate_template"
OP_CC_LIST_SCOPES = "cc_list_scopes"
OP_CC_REVOKE_SCOPE = "cc_revoke_scope"

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
    # MVP hard-limit: only a small allowlist of actions is supported.
    allowed = {CCActionType.SCREENSHOT, CCActionType.MOUSE_MOVE, CCActionType.MOUSE_CLICK, CCActionType.KEY_TYPE, CCActionType.WINDOW_FOCUS, CCActionType.WINDOW_WAIT}
    if not actions.issubset(allowed):
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


class CcScreenshotTool(ComputerControlTool):
    """Captura um screenshot (metadata-only) dentro de um scope já concedido.

    Segurança:
    - Fail-closed: nega se não houver scope/expirado/ação não permitida/limite excedido.
    - Auditoria metadata-only (sem bytes).
    - Consome orçamento do scope via scope.consume_action().
    """

    name = "cc_screenshot"
    description = (
        "Captura um screenshot (somente metadados; sem bytes) usando um scope de "
        "Computer Control previamente concedido."
    )
    operation = OP_CC_SCREENSHOT

    def __init__(self, *, scopes: dict[str, CCScope], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(
                success=False,
                error="invalid_input",
                scope_id=str(scope_id) if isinstance(scope_id, str) else None,
                action_type=CCActionType.SCREENSHOT.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)

        # Local import para evitar mexer na seção de imports do módulo.
        from app.computer_control.policy import evaluate_cc_action

        decision = evaluate_cc_action(
            has_computer_control_permission=True,  # se chegou aqui, o registry já exigiu a permissão
            scope=scope,
            action=CCActionType.SCREENSHOT,
        )
        if not decision.allowed:
            self._audit_record(
                success=False,
                error=decision.reason,
                scope_id=scope_id,
                action_type=CCActionType.SCREENSHOT.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error=decision.reason)

        # Reserva/consome orçamento antes de capturar (evita capturar se não puder consumir).
        try:
            scope.consume_action()
        except PermissionError:
            decision2 = evaluate_cc_action(
                has_computer_control_permission=True,
                scope=scope,
                action=CCActionType.SCREENSHOT,
                now=_now_utc(),
            )
            reason = decision2.reason if not decision2.allowed else "denied_scope_limit_exceeded"
            self._audit_record(
                success=False,
                error=reason,
                scope_id=scope_id,
                action_type=CCActionType.SCREENSHOT.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error=reason)

        try:
            info = self._driver.screenshot(target=scope.target)
            if not isinstance(info, ScreenshotInfo):
                raise TypeError("driver.screenshot must return ScreenshotInfo")
        except Exception:
            self._audit_record(
                success=False,
                error="screenshot_failed",
                scope_id=scope_id,
                action_type=CCActionType.SCREENSHOT.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="screenshot_failed")

        self._audit_record(
            success=True,
            scope_id=scope_id,
            action_type=CCActionType.SCREENSHOT.value,
            artifact_ref=info.artifact_ref,
            duration_ms=_dur_ms(),
        )
        return ToolResult(
            ok=True,
            data={
                "scope_id": scope_id,
                "screenshot": {
                    "width": info.width,
                    "height": info.height,
                    "artifact_ref": info.artifact_ref,
                },
            },
        )


class CcMouseMoveTool(ComputerControlTool):
    """Move o mouse de forma relativa (dx, dy) dentro de um scope concedido.

    MVP: apenas movimento relativo pequeno; sem clique e sem teclado.
    """

    name = "cc_mouse_move"
    description = (
        "Move o mouse de forma relativa (dx, dy) usando um scope de Computer Control previamente concedido. "
        "MVP: movimento pequeno; sem clique/teclado."
    )
    operation = OP_CC_MOUSE_MOVE

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time
        from app.computer_control.policy import evaluate_cc_action

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        dx = kwargs.get("dx")
        dy = kwargs.get("dy")

        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(dx, int) or isinstance(dx, bool):
            self._audit_record(
                success=False,
                error="invalid_input",
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_MOVE.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(dy, int) or isinstance(dy, bool):
            self._audit_record(
                success=False,
                error="invalid_input",
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_MOVE.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="invalid_input")

        # Limite de seguran?a do MVP: movimento pequeno.
        if dx < -50 or dx > 50 or dy < -50 or dy > 50:
            self._audit_record(
                success=False,
                error="invalid_input",
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_MOVE.value,
                duration_ms=_dur_ms(),
                dx=dx,
                dy=dy,
            )
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        decision = evaluate_cc_action(
            has_computer_control_permission=True,
            scope=scope,
            action=CCActionType.MOUSE_MOVE,
        )
        if not decision.allowed:
            self._audit_record(
                success=False,
                error=decision.reason,
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_MOVE.value,
                duration_ms=_dur_ms(),
                dx=dx,
                dy=dy,
            )
            return ToolResult(ok=False, error=decision.reason)

        try:
            scope.consume_action()
        except PermissionError:
            self._audit_record(
                success=False,
                error="denied_scope_limit_exceeded",
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_MOVE.value,
                duration_ms=_dur_ms(),
                dx=dx,
                dy=dy,
            )
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            x, y = self._driver.mouse_move(dx=dx, dy=dy, target=scope.target)
        except Exception:
            self._audit_record(
                success=False,
                error="mouse_move_failed",
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_MOVE.value,
                duration_ms=_dur_ms(),
                dx=dx,
                dy=dy,
            )
            return ToolResult(ok=False, error="mouse_move_failed")

        self._audit_record(
            success=True,
            scope_id=scope_id,
            action_type=CCActionType.MOUSE_MOVE.value,
            duration_ms=_dur_ms(),
            dx=dx,
            dy=dy,
            x=x,
            y=y,
        )
        return ToolResult(
            ok=True,
            data={"scope_id": scope_id, "cursor": {"x": x, "y": y, "dx": dx, "dy": dy}},
        )


class CcListScopesTool(ComputerControlTool):
    """Lista scopes de Computer Control criados na sess?o (metadados-only)."""

    name = "cc_list_scopes"
    description = (
        "Lista os scopes de Computer Control ativos na sess?o (metadados-only), "
        "incluindo a??es permitidas, expira??o e or?amento consumido."
    )
    operation = OP_CC_LIST_SCOPES

    def run(self, **kwargs) -> ToolResult:
        import time

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        now = _now_utc()
        scopes_out: list[dict] = []
        for s in self._scopes.values():
            scopes_out.append(
                {
                    "scope_id": s.scope_id,
                    "created_at": s.created_at.isoformat(),
                    "expires_at": s.expires_at.isoformat(),
                    "expired": s.is_expired(now=now),
                    "allowed_actions": [a.value for a in sorted(s.allowed_actions, key=lambda x: x.value)],
                    "target": {
                        "app_name": s.target.app_name,
                        "process_name": s.target.process_name,
                        "window_title_pattern": s.target.window_title_pattern,
                    },
                    "limits": {
                        "max_actions_total": s.limits.max_actions_total,
                        "max_actions_per_minute": s.limits.max_actions_per_minute,
                        "max_session_seconds": s.limits.max_session_seconds,
                    },
                    "actions_used": s.actions_used,
                    "remaining_actions": s.remaining_actions(),
                }
            )

        self._audit_record(success=True, duration_ms=_dur_ms(), scopes_count=len(scopes_out))
        return ToolResult(ok=True, data={"count": len(scopes_out), "scopes": scopes_out})


class CcRevokeScopeTool(ComputerControlTool):
    """Revoga (remove) um scope de Computer Control da sess?o atual."""

    name = "cc_revoke_scope"
    description = (
        "Revoga um scope de Computer Control previamente concedido nesta sess?o "
        "(redu??o de privil?gio; remove o scope)."
    )
    operation = OP_CC_REVOKE_SCOPE

    def run(self, **kwargs) -> ToolResult:
        import time

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        removed = self._scopes.pop(scope_id, None)
        if removed is None:
            self._audit_record(
                success=False,
                error="scope_not_found",
                scope_id=scope_id,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="scope_not_found")

        self._audit_record(success=True, scope_id=scope_id, duration_ms=_dur_ms())
        return ToolResult(ok=True, data={"scope_id": scope_id, "revoked": True})


class CcMouseClickTool(ComputerControlTool):
    """Clica com o mouse no ponto atual do cursor (MVP: bot?o esquerdo).

    Seguran?a:
    - Scope-gated (evaluate_cc_action) + consume_action (or?amento).
    - MVP: sem coordenadas, sem double click, sem outros bot?es.
    """

    name = "cc_mouse_click"
    description = (
        "Clica com o mouse (bot?o esquerdo) no ponto atual do cursor, usando um scope de Computer Control "
        "previamente concedido."
    )
    operation = OP_CC_MOUSE_CLICK

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time
        from app.computer_control.policy import evaluate_cc_action

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        decision = evaluate_cc_action(
            has_computer_control_permission=True,
            scope=scope,
            action=CCActionType.MOUSE_CLICK,
        )
        if not decision.allowed:
            self._audit_record(
                success=False,
                error=decision.reason,
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_CLICK.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error=decision.reason)

        try:
            scope.consume_action()
        except PermissionError:
            self._audit_record(
                success=False,
                error="denied_scope_limit_exceeded",
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_CLICK.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            x, y = self._driver.mouse_click(button="left", target=scope.target)
        except Exception:
            self._audit_record(
                success=False,
                error="mouse_click_failed",
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_CLICK.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="mouse_click_failed")

        self._audit_record(
            success=True,
            scope_id=scope_id,
            action_type=CCActionType.MOUSE_CLICK.value,
            duration_ms=_dur_ms(),
            button="left",
            x=x,
            y=y,
        )
        return ToolResult(ok=True, data={"scope_id": scope_id, "click": {"button": "left", "x": x, "y": y}})


class CcMouseClickAtTool(ComputerControlTool):
    """Move relativo (dx, dy) e clica (MVP: bot?o esquerdo).

    Seguran?a:
    - Scope-gated (evaluate_cc_action) + consume_action (or?amento).
    - MVP: dx/dy em [-50..50], sem double click, sem outros bot?es.
    """

    name = "cc_mouse_click_at"
    description = (
        "Move o mouse de forma relativa (dx, dy) e clica (bot?o esquerdo) usando um scope de Computer Control "
        "previamente concedido (MVP: movimento pequeno; 1 click)."
    )
    operation = OP_CC_MOUSE_CLICK_AT

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time
        from app.computer_control.policy import evaluate_cc_action

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        dx = kwargs.get("dx")
        dy = kwargs.get("dy")

        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(dx, int) or isinstance(dx, bool):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, action_type=CCActionType.MOUSE_CLICK.value, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(dy, int) or isinstance(dy, bool):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, action_type=CCActionType.MOUSE_CLICK.value, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        if dx < -50 or dx > 50 or dy < -50 or dy > 50:
            self._audit_record(
                success=False,
                error="invalid_input",
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_CLICK.value,
                duration_ms=_dur_ms(),
                dx=dx,
                dy=dy,
            )
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        decision = evaluate_cc_action(
            has_computer_control_permission=True,
            scope=scope,
            action=CCActionType.MOUSE_CLICK,
        )
        if not decision.allowed:
            self._audit_record(
                success=False,
                error=decision.reason,
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_CLICK.value,
                duration_ms=_dur_ms(),
                dx=dx,
                dy=dy,
            )
            return ToolResult(ok=False, error=decision.reason)

        try:
            scope.consume_action()
        except PermissionError:
            self._audit_record(
                success=False,
                error="denied_scope_limit_exceeded",
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_CLICK.value,
                duration_ms=_dur_ms(),
                dx=dx,
                dy=dy,
            )
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            x, y = self._driver.mouse_click_at(dx=dx, dy=dy, button="left", target=scope.target)
        except Exception:
            self._audit_record(
                success=False,
                error="mouse_click_failed",
                scope_id=scope_id,
                action_type=CCActionType.MOUSE_CLICK.value,
                duration_ms=_dur_ms(),
                dx=dx,
                dy=dy,
            )
            return ToolResult(ok=False, error="mouse_click_failed")

        self._audit_record(
            success=True,
            scope_id=scope_id,
            action_type=CCActionType.MOUSE_CLICK.value,
            duration_ms=_dur_ms(),
            button="left",
            dx=dx,
            dy=dy,
            x=x,
            y=y,
        )
        return ToolResult(
            ok=True,
            data={"scope_id": scope_id, "click": {"button": "left", "x": x, "y": y, "dx": dx, "dy": dy}},
        )



class CcDoubleClickAndTypeTool(ComputerControlTool):
    """Double-click (no cursor atual) e digita texto (1 aprova??o).

    Uso t?pico: usu?rio posiciona o mouse sobre um ?cone (ex.: arquivo .txt),
    aprova via ENTER no popup, e a tool faz double-click para abrir e ent?o
    digita no app (ex.: Notepad) focando por window_title_pattern do scope.

    Seguran?a:
    - Scope-gated (evaluate_cc_action) para MOUSE_CLICK e KEY_TYPE.
    - Reserva or?amento para 2 a??es antes de executar (consume_action 2x).
    - Auditoria metadata-only: nunca registra o texto.
    """

    name = "cc_double_click_and_type"
    description = (
        "Executa double-click (bot?o esquerdo) no ponto atual do cursor e em seguida "
        "digita texto (MVP) usando um scope de Computer Control previamente concedido. "
        "Pensado para 1 aprova??o (popup ENTER) sem mover o mouse."
    )
    operation = OP_CC_DOUBLE_CLICK_AND_TYPE

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time
        from app.computer_control.policy import evaluate_cc_action

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        text = kwargs.get("text")
        open_delay_ms = kwargs.get("open_delay_ms", 700)

        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(text, str) or not text:
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(open_delay_ms, int) or isinstance(open_delay_ms, bool):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if open_delay_ms < 100 or open_delay_ms > 3000:
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        # MVP safety: texto curto e sem caracteres de controle
        if len(text) > 80 or any(ord(ch) < 32 for ch in text):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms(), chars=len(text))
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        if scope is None:
            self._audit_record(success=False, error="denied_no_scope", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_no_scope")

        # Fail-closed: precisamos de window_title_pattern para focar antes de digitar
        pat = scope.target.window_title_pattern
        if not (isinstance(pat, str) and pat.strip()):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms(), chars=len(text))
            return ToolResult(ok=False, error="invalid_input")

        # Pr?-checagem de or?amento para 2 a??es (total). (rate/min ainda ? MVP no core)
        if scope.remaining_actions() < 2:
            self._audit_record(success=False, error="denied_scope_limit_exceeded", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        # Viabilidade: click e type precisam ser permitidos pelo scope/policy
        d_click = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.MOUSE_CLICK)
        if not d_click.allowed:
            self._audit_record(success=False, error=d_click.reason, scope_id=scope_id, action_type=CCActionType.MOUSE_CLICK.value, duration_ms=_dur_ms())
            return ToolResult(ok=False, error=d_click.reason)

        d_type = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.KEY_TYPE)
        if not d_type.allowed:
            self._audit_record(success=False, error=d_type.reason, scope_id=scope_id, action_type=CCActionType.KEY_TYPE.value, duration_ms=_dur_ms(), chars=len(text))
            return ToolResult(ok=False, error=d_type.reason)

        # Reserva or?amento antes de executar (2 a??es)
        try:
            scope.consume_action()
            scope.consume_action()
        except PermissionError:
            self._audit_record(success=False, error="denied_scope_limit_exceeded", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        # Executa double click (2 cliques) no cursor atual
        try:
            self._driver.mouse_click(button="left", target=scope.target)
            time.sleep(0.05)
            self._driver.mouse_click(button="left", target=scope.target)
        except Exception:
            self._audit_record(success=False, error="mouse_click_failed", scope_id=scope_id, duration_ms=_dur_ms(), clicks=2)
            return ToolResult(ok=False, error="mouse_click_failed")

        time.sleep(open_delay_ms / 1000.0)

        # Digita (driver foca pela window_title_pattern)
        try:
            typed = self._driver.key_type(text=text, target=scope.target)
        except Exception:
            self._audit_record(success=False, error="key_type_failed", scope_id=scope_id, duration_ms=_dur_ms(), chars=len(text))
            return ToolResult(ok=False, error="key_type_failed")

        self._audit_record(
            success=True,
            scope_id=scope_id,
            action_type="double_click_and_type",
            duration_ms=_dur_ms(),
            clicks=2,
            open_delay_ms=open_delay_ms,
            chars_typed=int(typed),
        )
        return ToolResult(
            ok=True,
            data={
                "scope_id": scope_id,
                "clicks": 2,
                "open_delay_ms": open_delay_ms,
                "chars_typed": int(typed),
            },
        )


class CcFocusWindowTool(ComputerControlTool):
    """Foca a janela-alvo (best-effort) pelo window_title_pattern do scope."""

    name = "cc_focus_window"
    description = (
        "Traz a janela-alvo para frente (best-effort) usando o window_title_pattern do scope. "
        "?til antes de clicar/digitar."
    )
    operation = OP_CC_WINDOW_FOCUS

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time
        from app.computer_control.policy import evaluate_cc_action

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        if scope is None:
            self._audit_record(success=False, error="denied_no_scope", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_no_scope")

        pat = scope.target.window_title_pattern
        if not (isinstance(pat, str) and pat.strip()):
            self._audit_record(
                success=False,
                error="invalid_input",
                scope_id=scope_id,
                action_type=CCActionType.WINDOW_FOCUS.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="invalid_input")

        decision = evaluate_cc_action(
            has_computer_control_permission=True,
            scope=scope,
            action=CCActionType.WINDOW_FOCUS,
        )
        if not decision.allowed:
            self._audit_record(
                success=False,
                error=decision.reason,
                scope_id=scope_id,
                action_type=CCActionType.WINDOW_FOCUS.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error=decision.reason)

        try:
            scope.consume_action()
        except PermissionError:
            self._audit_record(
                success=False,
                error="denied_scope_limit_exceeded",
                scope_id=scope_id,
                action_type=CCActionType.WINDOW_FOCUS.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            focused = bool(self._driver.focus_window(target=scope.target))
        except Exception:
            self._audit_record(
                success=False,
                error="window_focus_failed",
                scope_id=scope_id,
                action_type=CCActionType.WINDOW_FOCUS.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="window_focus_failed")

        if not focused:
            self._audit_record(
                success=False,
                error="window_not_found",
                scope_id=scope_id,
                action_type=CCActionType.WINDOW_FOCUS.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="window_not_found")

        self._audit_record(
            success=True,
            scope_id=scope_id,
            action_type=CCActionType.WINDOW_FOCUS.value,
            duration_ms=_dur_ms(),
        )
        return ToolResult(ok=True, data={"scope_id": scope_id, "focused": True})


class CcWaitForWindowTool(ComputerControlTool):
    """Espera a janela-alvo aparecer e foca (best-effort)."""

    name = "cc_wait_for_window"
    description = (
        "Espera at? a janela-alvo existir (best-effort) usando window_title_pattern do scope e ent?o a foca. "
        "?til para aguardar apps abrirem."
    )
    operation = OP_CC_WINDOW_WAIT

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time
        from app.computer_control.policy import evaluate_cc_action

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        timeout_s = kwargs.get("timeout_s", 10)

        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(timeout_s, int) or isinstance(timeout_s, bool) or timeout_s <= 0 or timeout_s > 120:
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        if scope is None:
            self._audit_record(success=False, error="denied_no_scope", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_no_scope")

        pat = scope.target.window_title_pattern
        if not (isinstance(pat, str) and pat.strip()):
            self._audit_record(
                success=False,
                error="invalid_input",
                scope_id=scope_id,
                action_type=CCActionType.WINDOW_WAIT.value,
                duration_ms=_dur_ms(),
                timeout_s=timeout_s,
            )
            return ToolResult(ok=False, error="invalid_input")

        decision = evaluate_cc_action(
            has_computer_control_permission=True,
            scope=scope,
            action=CCActionType.WINDOW_WAIT,
        )
        if not decision.allowed:
            self._audit_record(
                success=False,
                error=decision.reason,
                scope_id=scope_id,
                action_type=CCActionType.WINDOW_WAIT.value,
                duration_ms=_dur_ms(),
                timeout_s=timeout_s,
            )
            return ToolResult(ok=False, error=decision.reason)

        try:
            scope.consume_action()
        except PermissionError:
            self._audit_record(
                success=False,
                error="denied_scope_limit_exceeded",
                scope_id=scope_id,
                action_type=CCActionType.WINDOW_WAIT.value,
                duration_ms=_dur_ms(),
                timeout_s=timeout_s,
            )
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            ok = bool(self._driver.wait_for_window(target=scope.target, timeout_s=timeout_s))
        except Exception:
            self._audit_record(
                success=False,
                error="window_wait_failed",
                scope_id=scope_id,
                action_type=CCActionType.WINDOW_WAIT.value,
                duration_ms=_dur_ms(),
                timeout_s=timeout_s,
            )
            return ToolResult(ok=False, error="window_wait_failed")

        if not ok:
            self._audit_record(
                success=False,
                error="window_not_found",
                scope_id=scope_id,
                action_type=CCActionType.WINDOW_WAIT.value,
                duration_ms=_dur_ms(),
                timeout_s=timeout_s,
            )
            return ToolResult(ok=False, error="window_not_found")

        self._audit_record(
            success=True,
            scope_id=scope_id,
            action_type=CCActionType.WINDOW_WAIT.value,
            duration_ms=_dur_ms(),
            timeout_s=timeout_s,
        )
        return ToolResult(ok=True, data={"scope_id": scope_id, "found": True, "timeout_s": timeout_s})


class CcLocateTemplateTool(ComputerControlTool):
    """Localiza um template dentro de um screenshot (offline, via OpenCV).

    N?o executa mouse/teclado. Retorna coordenadas (centro) e confian?a.
    Auditoria metadata-only: n?o grava bytes nem caminhos sens?veis do template.
    """

    name = "cc_locate_template"
    description = (
        "Localiza um template dentro de um screenshot (offline, vis?o local) e retorna "
        "as coordenadas do centro e a confian?a do match."
    )
    operation = OP_CC_LOCATE_TEMPLATE

    def run(self, **kwargs) -> ToolResult:
        import time
        from pathlib import Path as _Path

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        screenshot_artifact_ref = kwargs.get("screenshot_artifact_ref")
        template_path = kwargs.get("template_path")
        threshold = kwargs.get("threshold", 0.90)

        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(screenshot_artifact_ref, str) or not screenshot_artifact_ref.strip():
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(template_path, str) or not template_path.strip():
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(threshold, (int, float)) or not (0.0 < float(threshold) <= 1.0):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        if scope is None:
            self._audit_record(success=False, error="denied_no_scope", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_no_scope")
        if scope.is_expired():
            self._audit_record(success=False, error="denied_scope_expired", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_scope_expired")

        sp = _Path(screenshot_artifact_ref)
        tp = _Path(template_path)
        if not sp.exists() or not sp.is_file():
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not tp.exists() or not tp.is_file():
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        from app.computer_vision.template_match import locate_template

        try:
            m = locate_template(screenshot_path=sp, template_path=tp, threshold=float(threshold))
        except Exception:
            self._audit_record(
                success=False,
                error="locate_failed",
                scope_id=scope_id,
                artifact_ref=str(sp),
                duration_ms=_dur_ms(),
                template_name=tp.name,
            )
            return ToolResult(ok=False, error="locate_failed")

        if m is None:
            self._audit_record(
                success=False,
                error="template_not_found",
                scope_id=scope_id,
                artifact_ref=str(sp),
                duration_ms=_dur_ms(),
                template_name=tp.name,
                threshold=float(threshold),
            )
            return ToolResult(ok=False, error="template_not_found")

        self._audit_record(
            success=True,
            scope_id=scope_id,
            artifact_ref=str(sp),
            duration_ms=_dur_ms(),
            template_name=tp.name,
            confidence=m.confidence,
            x=m.x,
            y=m.y,
            w=m.w,
            h=m.h,
            center_x=m.center_x,
            center_y=m.center_y,
        )
        return ToolResult(
            ok=True,
            data={
                "scope_id": scope_id,
                "match": {
                    "confidence": m.confidence,
                    "x": m.x,
                    "y": m.y,
                    "w": m.w,
                    "h": m.h,
                    "center_x": m.center_x,
                    "center_y": m.center_y,
                },
            },
        )


class CcMouseMoveToTool(ComputerControlTool):
    """Move o mouse para coordenadas absolutas (x,y) na tela virtual."""

    name = "cc_mouse_move_to"
    description = "Move o mouse para coordenadas absolutas (x,y) na tela virtual."
    operation = OP_CC_MOUSE_MOVE_TO

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time
        from app.computer_control.policy import evaluate_cc_action

        t0 = time.perf_counter()
        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        x = kwargs.get("x")
        y = kwargs.get("y")

        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(x, int) or isinstance(x, bool) or not isinstance(y, int) or isinstance(y, bool):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        if x < -20000 or x > 20000 or y < -20000 or y > 20000:
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms(), x=x, y=y)
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        if scope is None:
            self._audit_record(success=False, error="denied_no_scope", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_no_scope")

        d = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.MOUSE_MOVE)
        if not d.allowed:
            self._audit_record(success=False, error=d.reason, scope_id=scope_id, duration_ms=_dur_ms(), action_type=CCActionType.MOUSE_MOVE.value)
            return ToolResult(ok=False, error=d.reason)

        try:
            scope.consume_action()
        except PermissionError:
            self._audit_record(success=False, error="denied_scope_limit_exceeded", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            ax, ay = self._driver.mouse_move_to(x=int(x), y=int(y), target=scope.target)
        except Exception:
            self._audit_record(success=False, error="mouse_move_failed", scope_id=scope_id, duration_ms=_dur_ms(), x=int(x), y=int(y))
            return ToolResult(ok=False, error="mouse_move_failed")

        self._audit_record(success=True, scope_id=scope_id, duration_ms=_dur_ms(), action_type=CCActionType.MOUSE_MOVE.value, x=int(x), y=int(y))
        return ToolResult(ok=True, data={"scope_id": scope_id, "x": int(ax), "y": int(ay)})


class CcClickTemplateTool(ComputerControlTool):
    """Localiza um template em um screenshot (offline) e clica no centro encontrado.

    Fluxo: locate_template -> mouse_move_to(center) -> mouse_click
    """

    name = "cc_click_template"
    description = "Localiza um template em um screenshot (offline) e clica no centro encontrado."
    operation = OP_CC_CLICK_TEMPLATE

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time
        from pathlib import Path as _Path
        from app.computer_control.policy import evaluate_cc_action
        from app.computer_vision.template_match import locate_template

        t0 = time.perf_counter()
        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        screenshot_artifact_ref = kwargs.get("screenshot_artifact_ref")
        template_path = kwargs.get("template_path")
        threshold = kwargs.get("threshold", 0.85)
        button = kwargs.get("button", "left")

        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(screenshot_artifact_ref, str) or not screenshot_artifact_ref.strip():
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(template_path, str) or not template_path.strip():
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(threshold, (int, float)) or not (0.0 < float(threshold) <= 1.0):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if button not in ("left", "right", "middle"):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        sp = _Path(screenshot_artifact_ref)
        tp = _Path(template_path)
        if not sp.exists() or not sp.is_file() or not tp.exists() or not tp.is_file():
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms(), template_name=tp.name)
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        if scope is None:
            self._audit_record(success=False, error="denied_no_scope", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_no_scope")

        if scope.remaining_actions() < 2:
            self._audit_record(success=False, error="denied_scope_limit_exceeded", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        d1 = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.MOUSE_MOVE)
        if not d1.allowed:
            self._audit_record(success=False, error=d1.reason, scope_id=scope_id, duration_ms=_dur_ms(), action_type=CCActionType.MOUSE_MOVE.value)
            return ToolResult(ok=False, error=d1.reason)

        d2 = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.MOUSE_CLICK)
        if not d2.allowed:
            self._audit_record(success=False, error=d2.reason, scope_id=scope_id, duration_ms=_dur_ms(), action_type=CCActionType.MOUSE_CLICK.value)
            return ToolResult(ok=False, error=d2.reason)

        m = locate_template(screenshot_path=sp, template_path=tp, threshold=float(threshold))
        if m is None:
            self._audit_record(success=False, error="template_not_found", scope_id=scope_id, duration_ms=_dur_ms(), template_name=tp.name, threshold=float(threshold))
            return ToolResult(ok=False, error="template_not_found")

        try:
            scope.consume_action()
            scope.consume_action()
        except PermissionError:
            self._audit_record(success=False, error="denied_scope_limit_exceeded", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            self._driver.mouse_move_to(x=int(m.center_x), y=int(m.center_y), target=scope.target)
            self._driver.mouse_click(button=button, target=scope.target)
        except Exception:
            self._audit_record(success=False, error="click_failed", scope_id=scope_id, duration_ms=_dur_ms(), template_name=tp.name, confidence=m.confidence, center_x=m.center_x, center_y=m.center_y)
            return ToolResult(ok=False, error="click_failed")

        self._audit_record(
            success=True,
            scope_id=scope_id,
            duration_ms=_dur_ms(),
            template_name=tp.name,
            threshold=float(threshold),
            confidence=m.confidence,
            x=m.x, y=m.y, w=m.w, h=m.h,
            center_x=m.center_x, center_y=m.center_y,
            button=button,
        )
        return ToolResult(ok=True, data={"scope_id": scope_id, "clicked": True, "button": button, "match": {
            "confidence": m.confidence, "x": m.x, "y": m.y, "w": m.w, "h": m.h, "center_x": m.center_x, "center_y": m.center_y
        }})


class CcClickTemplateLiveTool(ComputerControlTool):
    """Screenshot ao vivo -> locate template (offline) -> move_to -> click.

    Resolve o problema de ter que passar screenshot_artifact_ref manualmente.
    """

    name = "cc_click_template_live"
    description = "Tira screenshot ao vivo, localiza template (offline) e clica no centro encontrado."
    operation = OP_CC_CLICK_TEMPLATE_LIVE

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time
        from pathlib import Path as _Path
        from app.computer_control.policy import evaluate_cc_action
        from app.computer_vision.template_match import locate_template

        t0 = time.perf_counter()
        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        template_path = kwargs.get("template_path")
        threshold = kwargs.get("threshold", 0.85)
        button = kwargs.get("button", "left")

        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(template_path, str) or not template_path.strip():
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(threshold, (int, float)) or not (0.0 < float(threshold) <= 1.0):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if button not in ("left", "right", "middle"):
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")

        tp = _Path(template_path)
        if not tp.exists() or not tp.is_file():
            self._audit_record(success=False, error="invalid_input", scope_id=scope_id, duration_ms=_dur_ms(), template_name=tp.name)
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        if scope is None:
            self._audit_record(success=False, error="denied_no_scope", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_no_scope")

        # precisamos de 3 a??es: screenshot + move + click
        if scope.remaining_actions() < 3:
            self._audit_record(success=False, error="denied_scope_limit_exceeded", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        d_shot = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.SCREENSHOT)
        if not d_shot.allowed:
            return ToolResult(ok=False, error=d_shot.reason)

        d_move = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.MOUSE_MOVE)
        if not d_move.allowed:
            return ToolResult(ok=False, error=d_move.reason)

        d_click = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.MOUSE_CLICK)
        if not d_click.allowed:
            return ToolResult(ok=False, error=d_click.reason)

        # 1) screenshot (consome 1)
        try:
            scope.consume_action()
        except PermissionError:
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            shot = self._driver.screenshot(target=scope.target)
            artifact = getattr(shot, "artifact_ref", None)
        except Exception:
            self._audit_record(success=False, error="screenshot_failed", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="screenshot_failed")

        if not isinstance(artifact, str) or not artifact.strip() or not _Path(artifact).exists():
            self._audit_record(success=False, error="screenshot_failed", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="screenshot_failed")

        # 2) localizar
        # 2) localizar (window-scoped; fail-closed)
        pat = getattr(scope.target, "window_title_pattern", None)
        if not (isinstance(pat, str) and pat.strip()):
            self._audit_record(success=False, error="denied_missing_window_title_pattern", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="denied_missing_window_title_pattern")

        try:
            rect = self._driver.get_window_rect(window_title_pattern=pat.strip())
        except Exception:
            rect = None
        if rect is None:
            self._audit_record(success=False, error="window_rect_not_found", scope_id=scope_id, duration_ms=_dur_ms(), window_title_pattern=pat.strip())
            return ToolResult(ok=False, error="window_rect_not_found")

        try:
            vx0, vy0 = self._driver.get_virtual_screen_origin()
        except Exception:
            self._audit_record(success=False, error="driver_missing_virtual_screen_origin", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="driver_missing_virtual_screen_origin")

        left, top, right, bottom = rect
        x1 = int(left - vx0)
        y1 = int(top - vy0)
        x2 = int(right - vx0)
        y2 = int(bottom - vy0)
        win_w = x2 - x1
        win_h = y2 - y1
        if win_w <= 0 or win_h <= 0:
            self._audit_record(success=False, error="window_rect_invalid", scope_id=scope_id, duration_ms=_dur_ms(), window_title_pattern=pat.strip())
            return ToolResult(ok=False, error="window_rect_invalid")

        # Restrict to top ~30% of the window to avoid false positives (multi-monitor).
        y2 = int(y1 + max(1, int(win_h * 0.30)))
        search_box = (x1, y1, x2, y2)

        m = locate_template(
            screenshot_path=_Path(artifact),
            template_path=tp,
            threshold=float(threshold),
            search_box=search_box,
        )
        if m is None:
            self._audit_record(success=False, error="template_not_found", scope_id=scope_id, duration_ms=_dur_ms(), template_name=tp.name, screenshot_artifact_ref=str(artifact))
            return ToolResult(ok=False, error="template_not_found")

        # 3) move+click (consome 2)
        try:
            scope.consume_action()
            scope.consume_action()
        except PermissionError:
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            self._driver.mouse_move_to(x=int(m.center_x), y=int(m.center_y), target=scope.target)
            self._driver.mouse_click(button=button, target=scope.target)
        except Exception:
            self._audit_record(success=False, error="click_failed", scope_id=scope_id, duration_ms=_dur_ms(), template_name=tp.name, confidence=m.confidence)
            return ToolResult(ok=False, error="click_failed")

        self._audit_record(
            success=True,
            scope_id=scope_id,
            duration_ms=_dur_ms(),
            template_name=tp.name,
            screenshot_artifact_ref=str(artifact),
            threshold=float(threshold),
            confidence=m.confidence,
            center_x=m.center_x,
            center_y=m.center_y,
            button=button,
        )
        return ToolResult(ok=True, data={
            "scope_id": scope_id,
            "clicked": True,
            "button": button,
            "screenshot_artifact_ref": str(artifact),
            "match": {"confidence": m.confidence, "center_x": m.center_x, "center_y": m.center_y},
        })


class CcClickTargetLiveTool(ComputerControlTool):
    """Hybrid click: offline-first template, fallback to vision provider, auto-learn.

    Params:
      - target_id: used to store learned template at templates_dir/{target_id}.png
      - query: natural language target description for provider vision
      - learn: if True, crop provider bbox and save as template for future offline runs
    """

    name = "cc_click_target_live"
    description = "Offline-first click by target_id; fallback to vision provider; auto-learn template."
    operation = OP_CC_CLICK_TARGET_LIVE

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, locator, templates_dir, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver
        self._locator = locator
        self._templates_dir = templates_dir

    def run(self, **kwargs) -> ToolResult:
        import time
        import re as _re
        from pathlib import Path as _Path
        from app.computer_control.policy import evaluate_cc_action
        from app.computer_vision.template_match import locate_template

        t0 = time.perf_counter()
        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        target_id = kwargs.get("target_id")
        query = kwargs.get("query")
        offline_threshold = kwargs.get("offline_threshold", 0.85)
        button = kwargs.get("button", "left")
        learn = kwargs.get("learn", True)

        if not isinstance(scope_id, str) or not scope_id.strip():
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(target_id, str) or not target_id.strip():
            return ToolResult(ok=False, error="invalid_input")
        if not _re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", target_id):
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(query, str) or not query.strip() or len(query) > 240:
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(offline_threshold, (int, float)) or not (0.0 < float(offline_threshold) <= 1.0):
            return ToolResult(ok=False, error="invalid_input")
        if button not in ("left", "right", "middle"):
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(learn, bool):
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        if scope is None:
            return ToolResult(ok=False, error="denied_no_scope")

        # Need: screenshot + move + click = 3 actions
        if scope.remaining_actions() < 3:
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        d_shot = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.SCREENSHOT)
        if not d_shot.allowed:
            return ToolResult(ok=False, error=d_shot.reason)
        d_move = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.MOUSE_MOVE)
        if not d_move.allowed:
            return ToolResult(ok=False, error=d_move.reason)
        d_click = evaluate_cc_action(has_computer_control_permission=True, scope=scope, action=CCActionType.MOUSE_CLICK)
        if not d_click.allowed:
            return ToolResult(ok=False, error=d_click.reason)

        # consume screenshot budget
        try:
            scope.consume_action()
        except PermissionError:
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            shot = self._driver.screenshot(target=scope.target)
            artifact = getattr(shot, "artifact_ref", None)
            width = int(getattr(shot, "width", 0))
            height = int(getattr(shot, "height", 0))
        except Exception:
            self._audit_record(success=False, error="screenshot_failed", scope_id=scope_id, duration_ms=_dur_ms())
            return ToolResult(ok=False, error="screenshot_failed")

        if not isinstance(artifact, str) or not artifact.strip() or not _Path(artifact).exists():
            return ToolResult(ok=False, error="screenshot_failed")

        sp = _Path(artifact)
        templates_dir = _Path(self._templates_dir)
        tpl_path = templates_dir / f"{target_id}.png"

        # ---------- Offline-first ----------
        m = None
        if tpl_path.exists() and tpl_path.is_file():
            try:
                # window-scoped offline locate (fail-closed: never match globally)
                pat = getattr(scope.target, "window_title_pattern", None)
                search_box = None
                if isinstance(pat, str) and pat.strip():
                    rect = None
                    try:
                        rect = self._driver.get_window_rect(window_title_pattern=pat.strip())
                    except Exception:
                        rect = None
                    if rect is not None:
                        try:
                            vx0, vy0 = self._driver.get_virtual_screen_origin()
                        except Exception:
                            rect = None
                    if rect is not None:
                        left, top, right, bottom = rect
                        x1 = int(left - vx0)
                        y1 = int(top - vy0)
                        x2 = int(right - vx0)
                        y2 = int(bottom - vy0)
                        win_w = x2 - x1
                        win_h = y2 - y1
                        if win_w > 0 and win_h > 0:
                            y2 = int(y1 + max(1, int(win_h * 0.30)))
                            search_box = (x1, y1, x2, y2)

                if search_box is not None:
                    m = locate_template(
                        screenshot_path=sp,
                        template_path=tpl_path,
                        threshold=float(offline_threshold),
                        search_box=search_box,
                    )
                else:
                    m = None
            except Exception:
                m = None

        if m is not None:
            # consume move+click
            try:
                scope.consume_action()
                scope.consume_action()
            except PermissionError:
                return ToolResult(ok=False, error="denied_scope_limit_exceeded")

            try:
                self._driver.mouse_move_to(x=int(m.center_x), y=int(m.center_y), target=scope.target)
                self._driver.mouse_click(button=button, target=scope.target)
            except Exception:
                self._audit_record(success=False, error="click_failed", scope_id=scope_id, duration_ms=_dur_ms(), target_id=target_id)
                return ToolResult(ok=False, error="click_failed")

            self._audit_record(success=True, scope_id=scope_id, duration_ms=_dur_ms(),
                               target_id=target_id, used_template=True, used_provider=False)
            return ToolResult(ok=True, data={
                "scope_id": scope_id,
                "target_id": target_id,
                "used_template": True,
                "used_provider": False,
                "template_path": str(tpl_path),
                "match": {"confidence": m.confidence, "center_x": m.center_x, "center_y": m.center_y},
            })

        # ---------- Provider fallback ----------
        try:
            vr = self._locator.locate(image_path=sp, query=query.strip())
        except Exception:
            self._audit_record(success=False, error="vision_provider_failed", scope_id=scope_id, duration_ms=_dur_ms(), target_id=target_id)
            return ToolResult(ok=False, error="vision_provider_failed")

        if vr is None:
            self._audit_record(success=False, error="target_not_found", scope_id=scope_id, duration_ms=_dur_ms(), target_id=target_id)
            return ToolResult(ok=False, error="target_not_found")

        # derive pixels; prefer real width/height from ScreenshotInfo; fallback to image decode if needed
        if width <= 0 or height <= 0:
            try:
                import cv2  # type: ignore
                img = cv2.imread(str(sp), cv2.IMREAD_COLOR)
                if img is not None:
                    height, width = img.shape[:2]
            except Exception:
                width, height = 1, 1

        cx = int(round(vr.center_x_norm * float(width)))
        cy = int(round(vr.center_y_norm * float(height)))

        # consume move+click
        try:
            scope.consume_action()
            scope.consume_action()
        except PermissionError:
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            self._driver.mouse_move_to(x=cx, y=cy, target=scope.target)
            self._driver.mouse_click(button=button, target=scope.target)
        except Exception:
            self._audit_record(success=False, error="click_failed", scope_id=scope_id, duration_ms=_dur_ms(), target_id=target_id)
            return ToolResult(ok=False, error="click_failed")

        learned = False
        if learn:
            try:
                templates_dir.mkdir(parents=True, exist_ok=True)
                import cv2  # type: ignore
                img = cv2.imread(str(sp), cv2.IMREAD_COLOR)
                if img is not None:
                    x0 = max(0, int(vr.x_norm * width))
                    y0 = max(0, int(vr.y_norm * height))
                    x1 = min(width, int((vr.x_norm + vr.w_norm) * width))
                    y1 = min(height, int((vr.y_norm + vr.h_norm) * height))
                    if x1 > x0 + 4 and y1 > y0 + 4:
                        crop = img[y0:y1, x0:x1]
                        cv2.imwrite(str(tpl_path), crop)
                        learned = True
            except Exception:
                learned = False

        self._audit_record(success=True, scope_id=scope_id, duration_ms=_dur_ms(),
                           target_id=target_id, used_template=False, used_provider=True, learned_template=learned)
        return ToolResult(ok=True, data={
            "scope_id": scope_id,
            "target_id": target_id,
            "used_template": False,
            "used_provider": True,
            "learned_template": learned,
            "template_path": str(tpl_path),
            "provider": getattr(vr, "provider", None),
            "model": getattr(vr, "model", None),
            "confidence": getattr(vr, "confidence", None),
        })

from app.security.permissions import PermissionManager  # local import style OK for tools module
from app.tools.base import ToolRegistry
from app.tools.handler import ToolCheckpoints
from app.computer_control.policy import evaluate_cc_action


class PrevalidatedComputerControlCheckpoints(ToolCheckpoints):
    """Checkpoint CC somente para a??es vi?veis (sem aprova??o decorativa).

    Pede aprova??o apenas para a??es de clique (mouse_click, mouse_click_at) e
    somente quando:
    - a tool est? registrada,
    - a permiss?o COMPUTER_CONTROL est? concedida,
    - e evaluate_cc_action(...) permite a a??o para o scope_id informado.
    """

    def __init__(self, permissions: PermissionManager, registry: ToolRegistry, scopes: dict[str, "CCScope"]) -> None:
        super().__init__(("cc_mouse_click", "cc_mouse_click_at", "cc_key_type", "cc_double_click_and_type", "cc_mouse_move_to", "cc_click_template", "cc_click_template_live", "cc_click_target_live"))
        self._permissions = permissions
        self._registry = registry
        self._scopes = scopes

    def requires_checkpoint(self, task) -> bool:  # type: ignore[override]
        if not super().requires_checkpoint(task):
            return False
        if not task.tool:
            return False
        try:
            tool = self._registry.get(task.tool)
        except Exception:
            return False  # n?o registrada: falha controlada no handler
        if not self._permissions.is_granted(tool.required_permission):
            return False
        params = dict(task.parameters or {})
        scope_id = params.get("scope_id")
        if not isinstance(scope_id, str) or not scope_id.strip():
            return False  # invi?vel: handler falha com invalid_input
        scope = self._scopes.get(scope_id)
        tool_name = task.tool

        # Par?metros por tool (viabilidade) ? sem aprova??o decorativa.
        if tool_name == "cc_click_template_live":
            from pathlib import Path as _Path

            template_path = params.get("template_path")
            threshold = params.get("threshold", 0.85)
            button = params.get("button", "left")

            if not isinstance(template_path, str) or not template_path.strip():
                return False
            if not isinstance(threshold, (int, float)) or not (0.0 < float(threshold) <= 1.0):
                return False
            if button not in ("left", "right", "middle"):
                return False

            tp = _Path(template_path)
            if not tp.exists() or not tp.is_file():
                return False

            scope = self._scopes.get(scope_id)
            if scope is None or scope.remaining_actions() < 3:
                return False

            d0 = evaluate_cc_action(
                has_computer_control_permission=True,
                scope=scope,
                action=CCActionType.SCREENSHOT,
            )
            if not d0.allowed:
                return False
            d1 = evaluate_cc_action(
                has_computer_control_permission=True,
                scope=scope,
                action=CCActionType.MOUSE_MOVE,
            )
            if not d1.allowed:
                return False
            d2 = evaluate_cc_action(
                has_computer_control_permission=True,
                scope=scope,
                action=CCActionType.MOUSE_CLICK,
            )
            return d2.allowed

        if tool_name == "cc_click_target_live":
            target_id = params.get("target_id")
            query = params.get("query")
            offline_threshold = params.get("offline_threshold", 0.85)
            button = params.get("button", "left")
            learn = params.get("learn", True)

            if not isinstance(target_id, str) or not target_id.strip():
                return False
            import re as _re
            if not _re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", target_id):
                return False
            if not isinstance(query, str) or not query.strip() or len(query) > 240:
                return False
            if not isinstance(offline_threshold, (int, float)) or not (0.0 < float(offline_threshold) <= 1.0):
                return False
            if button not in ("left", "right", "middle"):
                return False
            if not isinstance(learn, bool):
                return False

            scope = self._scopes.get(scope_id)
            if scope is None or scope.remaining_actions() < 3:
                return False

            d0 = evaluate_cc_action(
                has_computer_control_permission=True,
                scope=scope,
                action=CCActionType.SCREENSHOT,
            )
            if not d0.allowed:
                return False
            d1 = evaluate_cc_action(
                has_computer_control_permission=True,
                scope=scope,
                action=CCActionType.MOUSE_MOVE,
            )
            if not d1.allowed:
                return False
            d2 = evaluate_cc_action(
                has_computer_control_permission=True,
                scope=scope,
                action=CCActionType.MOUSE_CLICK,
            )
            return d2.allowed

        if tool_name == "cc_mouse_click_at":
            dx = params.get("dx")
            dy = params.get("dy")
            if not isinstance(dx, int) or isinstance(dx, bool):
                return False
            if not isinstance(dy, int) or isinstance(dy, bool):
                return False
            if dx < -50 or dx > 50 or dy < -50 or dy > 50:
                return False

        if tool_name == "cc_double_click_and_type":
            text = params.get("text")
            if not isinstance(text, str) or not text:
                return False
            if len(text) > 80:
                return False
            if any(ord(ch) < 32 for ch in text):
                return False
            open_delay_ms = params.get("open_delay_ms", 700)
            if not isinstance(open_delay_ms, int) or isinstance(open_delay_ms, bool):
                return False
            if open_delay_ms < 100 or open_delay_ms > 3000:
                return False

            scope = self._scopes.get(scope_id)
            pat = scope.target.window_title_pattern if scope is not None else None
            if not (isinstance(pat, str) and pat.strip()):
                return False
            # precisa de or?amento para 2 a??es (double-click + digitar)
            if scope is None or scope.remaining_actions() < 2:
                return False

            d1 = evaluate_cc_action(
                has_computer_control_permission=True,
                scope=scope,
                action=CCActionType.MOUSE_CLICK,
            )
            if not d1.allowed:
                return False
            d2 = evaluate_cc_action(
                has_computer_control_permission=True,
                scope=scope,
                action=CCActionType.KEY_TYPE,
            )
            return d2.allowed

        if tool_name == "cc_key_type":
            text = params.get("text")
            if not isinstance(text, str) or not text:
                return False
            if len(text) > 80:
                return False
            if any(ord(ch) < 32 for ch in text):
                return False
            scope = self._scopes.get(scope_id)
            pat = scope.target.window_title_pattern if scope is not None else None
            if not (isinstance(pat, str) and pat.strip()):
                return False
            action = CCActionType.KEY_TYPE
        else:
            action = CCActionType.MOUSE_CLICK

        decision = evaluate_cc_action(
            has_computer_control_permission=True,
            scope=scope,
            action=action,
        )
        return decision.allowed


class CcKeyTypeTool(ComputerControlTool):
    """Digita texto (MVP) usando um scope concedido.

    Seguran?a:
    - Scope-gated (evaluate_cc_action) + consume_action (or?amento).
    - Checkpoint ser? exigido por policy (CC-11/CC-10).
    - Auditoria metadata-only: NUNCA registra o texto digitado.
    """

    name = "cc_key_type"
    description = (
        "Digita texto usando um scope de Computer Control previamente concedido. "
        "MVP: texto curto, sem caracteres de controle; sem registrar o conte?do."
    )
    operation = OP_CC_KEY_TYPE

    def __init__(self, *, scopes: dict[str, "CCScope"], driver, audit=None):
        super().__init__(scopes=scopes, audit=audit)
        self._driver = driver

    def run(self, **kwargs) -> ToolResult:
        import time
        from app.computer_control.policy import evaluate_cc_action

        t0 = time.perf_counter()

        def _dur_ms() -> int:
            return int((time.perf_counter() - t0) * 1000)

        scope_id = kwargs.get("scope_id")
        text = kwargs.get("text")

        if not isinstance(scope_id, str) or not scope_id.strip():
            self._audit_record(success=False, error="invalid_input", duration_ms=_dur_ms())
            return ToolResult(ok=False, error="invalid_input")
        if not isinstance(text, str) or not text:
            self._audit_record(
                success=False,
                error="invalid_input",
                scope_id=scope_id,
                action_type=CCActionType.KEY_TYPE.value,
                duration_ms=_dur_ms(),
            )
            return ToolResult(ok=False, error="invalid_input")

        # MVP safety: texto curto e sem caracteres de controle (sem \n, \t, etc).
        if len(text) > 80:
            self._audit_record(
                success=False,
                error="invalid_input",
                scope_id=scope_id,
                action_type=CCActionType.KEY_TYPE.value,
                duration_ms=_dur_ms(),
                chars=len(text),
            )
            return ToolResult(ok=False, error="invalid_input")
        if any(ord(ch) < 32 for ch in text):
            self._audit_record(
                success=False,
                error="invalid_input",
                scope_id=scope_id,
                action_type=CCActionType.KEY_TYPE.value,
                duration_ms=_dur_ms(),
                chars=len(text),
            )
            return ToolResult(ok=False, error="invalid_input")

        scope = self._scopes.get(scope_id)
        if scope is not None:
            pat = scope.target.window_title_pattern
            if not (isinstance(pat, str) and pat.strip()):
                # Fail-closed: sem alvo de janela n?o digitamos (a UI rouba foco no approve).
                self._audit_record(
                    success=False,
                    error="invalid_input",
                    scope_id=scope_id,
                    action_type=CCActionType.KEY_TYPE.value,
                    duration_ms=_dur_ms(),
                    chars=len(text),
                )
                return ToolResult(ok=False, error="invalid_input")

        decision = evaluate_cc_action(
            has_computer_control_permission=True,
            scope=scope,
            action=CCActionType.KEY_TYPE,
        )
        if not decision.allowed:
            self._audit_record(
                success=False,
                error=decision.reason,
                scope_id=scope_id,
                action_type=CCActionType.KEY_TYPE.value,
                duration_ms=_dur_ms(),
                chars=len(text),
            )
            return ToolResult(ok=False, error=decision.reason)

        try:
            scope.consume_action()
        except PermissionError:
            self._audit_record(
                success=False,
                error="denied_scope_limit_exceeded",
                scope_id=scope_id,
                action_type=CCActionType.KEY_TYPE.value,
                duration_ms=_dur_ms(),
                chars=len(text),
            )
            return ToolResult(ok=False, error="denied_scope_limit_exceeded")

        try:
            typed = self._driver.key_type(text=text, target=scope.target)
        except Exception:
            self._audit_record(
                success=False,
                error="key_type_failed",
                scope_id=scope_id,
                action_type=CCActionType.KEY_TYPE.value,
                duration_ms=_dur_ms(),
                chars=len(text),
            )
            return ToolResult(ok=False, error="key_type_failed")

        # Auditoria metadata-only: nunca inclui o texto.
        self._audit_record(
            success=True,
            scope_id=scope_id,
            action_type=CCActionType.KEY_TYPE.value,
            duration_ms=_dur_ms(),
            chars_typed=int(typed),
        )
        return ToolResult(ok=True, data={"scope_id": scope_id, "chars_typed": int(typed)})
