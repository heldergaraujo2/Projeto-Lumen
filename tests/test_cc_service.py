from datetime import datetime, timedelta, timezone

from app.computer_control.actions import CCActionRequest
from app.computer_control.api import CCActionType, CCTarget, ScreenRegion
from app.computer_control.fake_driver import FakeComputerControlDriver
from app.computer_control.grounding import GroundedTarget, GroundingSource
from app.computer_control.scopes import CCLimits, CCScope
from app.computer_control.service import ComputerControlService
from app.security.permissions import PermissionLevel, PermissionManager


class FakeActionDriver(FakeComputerControlDriver):
    def __init__(self):
        super().__init__()
        self.calls = []

    def mouse_move(self, x, y): self.calls.append(("move", x, y))
    def mouse_click(self, x, y, button="left"): self.calls.append(("click", x, y, button))
    def mouse_double_click(self, x, y, button="left"): self.calls.append(("double", x, y, button))
    def scroll(self, delta): self.calls.append(("scroll", delta))
    def key_press(self, key): self.calls.append(("press", key))
    def key_combo(self, keys): self.calls.append(("combo", keys))
    def type_text(self, text): self.calls.append(("type", text))
    def focus_window(self, target): self.calls.append(("focus", target.app_name))


def make_scope(*actions, region=None, total=2, per_minute=10):
    n = datetime.now(timezone.utc)
    return CCScope(
        "s", n, n + timedelta(minutes=1), CCTarget(app_name="Lumen"),
        frozenset(actions or {CCActionType.MOUSE_CLICK}),
        CCLimits(total, per_minute), region,
    )


def service():
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.COMPUTER_CONTROL)
    return ComputerControlService(permissions=permissions, driver=FakeActionDriver())


def test_service_denies_without_permission():
    driver = FakeActionDriver()
    result = ComputerControlService(
        permissions=PermissionManager(), driver=driver
    ).execute(scope=make_scope(), request=CCActionRequest(CCActionType.MOUSE_CLICK, x=10, y=10))
    assert not result.success and driver.calls == []
    assert result.error == "denied_no_permission"


def test_service_requires_checkpoint_before_driver_execution():
    svc = service()
    result = svc.execute(
        scope=make_scope(),
        request=CCActionRequest(CCActionType.MOUSE_CLICK, x=10, y=10),
    )
    assert not result.success
    assert result.error == "checkpoint_required"
    assert result.checkpoint is not None
    assert result.checkpoint.pending
    assert svc.driver.calls == []


def test_approved_checkpoint_executes_once():
    svc = service()
    scope = make_scope()
    request = CCActionRequest(CCActionType.MOUSE_CLICK, x=10, y=10)
    pending = svc.execute(scope=scope, request=request)
    approved = svc.approve(pending.checkpoint.id, scope=scope, request=request, note="user approved")
    assert approved.success
    assert approved.checkpoint.status == "CONSUMED"
    assert svc.driver.calls == [("click", 10, 10, "left")]
    replay = svc.execute(
        scope=scope, request=request, approved_checkpoint_id=pending.checkpoint.id
    )
    assert not replay.success
    assert replay.error == "checkpoint_not_pending"
    assert svc.driver.calls == [("click", 10, 10, "left")]


def test_checkpoint_cannot_be_reused_for_different_target():
    svc = service()
    scope = make_scope()
    pending = svc.execute(
        scope=scope, request=CCActionRequest(CCActionType.MOUSE_CLICK, x=10, y=10)
    )
    result = svc.approve(
        pending.checkpoint.id, scope=scope,
        request=CCActionRequest(CCActionType.MOUSE_CLICK, x=11, y=10),
    )
    assert not result.success
    assert result.error == "checkpoint_request_mismatch"
    assert svc.driver.calls == []


def test_refused_checkpoint_never_executes():
    svc = service()
    scope = make_scope()
    request = CCActionRequest(CCActionType.MOUSE_CLICK, x=10, y=10)
    pending = svc.execute(scope=scope, request=request)
    refused = svc.refuse(pending.checkpoint.id, note="no")
    assert refused.status == "REFUSED"
    assert svc.driver.calls == []
    result = svc.execute(scope=scope, request=request, approved_checkpoint_id=pending.checkpoint.id)
    assert not result.success
    assert result.error == "checkpoint_not_pending"


def test_scope_region_is_rechecked_at_execution():
    svc = service()
    scope = make_scope(region=ScreenRegion(0, 0, 20, 20))
    request = CCActionRequest(CCActionType.MOUSE_CLICK, x=10, y=10)
    pending = svc.execute(scope=scope, request=request)
    scope.allowed_region = ScreenRegion(0, 0, 5, 5)
    result = svc.approve(pending.checkpoint.id, scope=scope, request=request)
    assert not result.success
    assert result.error == "execution_failed"
    assert svc.driver.calls == []


def test_scope_budget_is_not_consumed_by_denial_or_pending():
    svc = service()
    scope = make_scope(total=1)
    request = CCActionRequest(CCActionType.MOUSE_CLICK, x=10, y=10)
    pending = svc.execute(scope=scope, request=request)
    assert scope.actions_used == 0
    result = svc.approve(pending.checkpoint.id, scope=scope, request=request)
    assert result.success
    assert scope.actions_used == 1


def test_grounded_target_point_is_revalidated_by_scope():
    svc = service()
    scope = make_scope(region=ScreenRegion(0, 0, 20, 20))
    target = GroundedTarget("Compile", GroundingSource.VISION, 0.95, 30, 30, 10, 10)
    request = CCActionRequest(CCActionType.MOUSE_CLICK, target=target)
    pending = svc.execute(scope=scope, request=request)
    result = svc.approve(pending.checkpoint.id, scope=scope, request=request)
    assert not result.success
    assert result.error == "execution_failed"
    assert svc.driver.calls == []


def test_action_not_allowed_never_creates_checkpoint():
    svc = service()
    scope = make_scope(CCActionType.SCREENSHOT)
    result = svc.execute(
        scope=scope, request=CCActionRequest(CCActionType.MOUSE_CLICK, x=10, y=10)
    )
    assert not result.success
    assert result.error == "denied_action_not_allowed"
    assert result.checkpoint is None


def test_legacy_no_checkpoint_mode_is_explicit_opt_out():
    permissions = PermissionManager([PermissionLevel.CHAT, PermissionLevel.COMPUTER_CONTROL])
    driver = FakeActionDriver()
    svc = ComputerControlService(
        permissions=permissions, driver=driver, require_checkpoint=False
    )
    result = svc.execute(
        scope=make_scope(), request=CCActionRequest(CCActionType.MOUSE_CLICK, x=10, y=10)
    )
    assert result.success
    assert driver.calls == [("click", 10, 10, "left")]


def test_screenshot_region_cannot_escape_scope():
    svc = service()
    scope = make_scope(CCActionType.SCREENSHOT, region=ScreenRegion(0, 0, 50, 50))
    request = CCActionRequest(
        CCActionType.SCREENSHOT, region=ScreenRegion(40, 40, 20, 20)
    )
    pending = svc.execute(scope=scope, request=request)
    result = svc.approve(pending.checkpoint.id, scope=scope, request=request)
    assert not result.success
    assert result.error == "execution_failed"
    assert svc.driver.calls == []


def test_unsupported_driver_action_fails_closed_after_approval():
    svc = service()
    scope = make_scope(CCActionType.MOUSE_DRAG)
    request = CCActionRequest(CCActionType.MOUSE_DRAG, x=10, y=10)
    pending = svc.execute(scope=scope, request=request)
    result = svc.approve(pending.checkpoint.id, scope=scope, request=request)
    assert not result.success
    assert "mouse_drag" in (result.error or "")
    assert svc.driver.calls == []
