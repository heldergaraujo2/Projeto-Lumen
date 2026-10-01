"""Secure lifecycle coordinator for UI-driven Unreal execution.

This module is intentionally independent from Tkinter. It owns only the
lifecycle of an already-authorized UnrealExecutionSession; it never grants
permissions, creates scopes, arms drivers, or changes policy.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.computer_control.service import ComputerControlService
from app.computer_control.scopes import CCScope

from .agent import UnrealAgent
from .execution import UnrealExecutionSession, UnrealExecutionState
from .models import UnrealPlan


@dataclass(frozen=True)
class UnrealWorkflowStatus:
    """UI-safe status snapshot."""

    active: bool
    state: UnrealExecutionState | None
    checkpoint_id: str | None = None


class UnrealWorkflowCoordinator:
    """Bridge the UI lifecycle to the existing secure Unreal session.

    The caller must supply the ComputerControlService and a pre-authorized
    CCScope. This class never creates or broadens either authority.
    """

    def __init__(
        self,
        *,
        service: ComputerControlService,
        agent: UnrealAgent | None = None,
    ) -> None:
        self._service = service
        self._agent = agent
        self._session: UnrealExecutionSession | None = None

    def start(
        self,
        *,
        plan: UnrealPlan,
        scope: CCScope,
        observation_fingerprint: str,
    ) -> UnrealWorkflowStatus:
        if self._session is not None and not self._session.state.completed:
            raise RuntimeError("an Unreal workflow is already active")
        self._session = UnrealExecutionSession(
            service=self._service,
            scope=scope,
            plan=plan,
            observation_fingerprint=observation_fingerprint,
            agent=self._agent,
        )
        return self.status()

    def status(self) -> UnrealWorkflowStatus:
        session = self._session
        if session is None:
            return UnrealWorkflowStatus(False, None)
        state = session.state
        return UnrealWorkflowStatus(
            active=not state.completed,
            state=state,
            checkpoint_id=state.checkpoint_id,
        )

    def prepare_next(self):
        session = self._require_session()
        return session.prepare_next()

    def approve_current(self, *, note: str = ""):
        session = self._require_session()
        return session.approve_current(note=note)

    def refuse_current(self, *, note: str = ""):
        session = self._require_session()
        return session.refuse_current(note=note)

    def clear(self) -> None:
        self._session = None

    def _require_session(self) -> UnrealExecutionSession:
        if self._session is None:
            raise RuntimeError("no Unreal workflow is active")
        return self._session
