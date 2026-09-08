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
OP_CC_KEY_TYPE = "cc_key_type"
OP_CC_DOUBLE_CLICK_AND_TYPE = "cc_double_click_and_type"
OP_CC_WINDOW_FOCUS = "cc_window_focus"
OP_CC_WINDOW_WAIT = "cc_window_wait"
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
        super().__init__(("cc_mouse_click", "cc_mouse_click_at", "cc_key_type", "cc_double_click_and_type"))
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
