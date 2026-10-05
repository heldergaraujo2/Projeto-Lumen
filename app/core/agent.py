"""Agent Core da Lumen com runtime universal opcional."""
from __future__ import annotations

import logging
import threading

from app.ai.provider import AIProvider, DeltaCallback, ProviderError, user_message_for
from app.ai.types import AIResponse
from app.config.persona import build_system_prompt
from app.core.bridge import AgentOutcome, RequestState, ToolCallingBridge
from app.memory.store import MemoryStore
from app.memory.system import MemorySystem
from app.planner.models import Plan
from app.planner.planner import Planner
from app.security.permissions import PermissionLevel, PermissionManager
from app.tasks.manager import TaskManager

logger = logging.getLogger("lumen.agent")


class AgentError(RuntimeError):
    """Falha dentro do Agent Core."""


class Agent:
    """Núcleo conversacional da Lumen."""

    def __init__(
        self,
        provider: AIProvider,
        memory: MemoryStore,
        permissions: PermissionManager | None = None,
        task_manager: TaskManager | None = None,
        context_window: int = 50,
        system_prompt: str | None = None,
        memory_system: MemorySystem | None = None,
    ) -> None:
        if context_window < 1:
            raise ValueError("context_window deve ser >= 1.")
        self._provider = provider
        self._provider_lock = threading.RLock()
        self._memory = memory
        self._permissions = permissions
        self._task_manager = task_manager
        self._context_window = context_window
        self._system_prompt = system_prompt or build_system_prompt()
        self._tools_controller = None
        self._universal_runtime = None
        self._memory_system = memory_system
        self.last_response: AIResponse | None = None

    @property
    def provider(self) -> AIProvider:
        with self._provider_lock:
            return self._provider

    def set_provider(self, provider: AIProvider) -> None:
        with self._provider_lock:
            self._provider = provider
        logger.info("Provider do Agent alterado para '%s' (modelo=%s).", provider.name, provider.model_name or "-")

    @property
    def memory(self) -> MemoryStore:
        return self._memory

    @property
    def task_manager(self) -> TaskManager | None:
        return self._task_manager

    @property
    def memory_system(self) -> MemorySystem | None:
        return self._memory_system

    @property
    def permissions(self) -> PermissionManager | None:
        return self._permissions

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def set_tools_controller(self, controller) -> None:
        self._tools_controller = controller

    def set_universal_runtime(self, runtime) -> None:
        self._universal_runtime = runtime

    @property
    def universal_runtime(self):
        return self._universal_runtime

    def process_message(self, text: str, on_delta: DeltaCallback | None = None) -> AgentOutcome:
        if self._tools_controller is None:
            reply = self.send_message(text, on_delta=on_delta)
            return AgentOutcome(RequestState.CONVERSATIONAL, reply)
        bridge = ToolCallingBridge(self, self._tools_controller, universal_runtime=self._universal_runtime)
        return bridge.process(text, on_delta=on_delta)

    def request_tool_plan(self, text: str, catalog: dict | None = None):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("O pedido do plano não pode ser vazio.")
        cleaned = text.strip()
        if self._permissions is not None:
            self._permissions.require(PermissionLevel.CHAT)
        with self._provider_lock:
            provider = self._provider
        planner = Planner(provider, memory=self._memory_system, catalog=catalog)
        history = [m.to_dict() for m in self._memory.recent(self._context_window)]
        return planner.create_tool_plan(cleaned, history)

    def send_message(self, text: str, on_delta: DeltaCallback | None = None) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("A mensagem não pode ser vazia.")
        cleaned = text.strip()
        if self._permissions is not None:
            self._permissions.require(PermissionLevel.CHAT)
        with self._provider_lock:
            provider = self._provider
        history = self._memory.recent(self._context_window)
        self._memory.add_message("user", cleaned)
        try:
            response = provider.chat(
                cleaned,
                [m.to_dict() for m in history],
                system_prompt=self._system_prompt,
                on_delta=on_delta,
            )
        except ProviderError as exc:
            raise AgentError(user_message_for(exc)) from exc
        except Exception as exc:
            raise AgentError(f"Erro inesperado ao contatar o provedor: {exc}") from exc
        if not isinstance(response, AIResponse):
            raise AgentError(
                f"O provedor '{provider.name}' devolveu um tipo inesperado "
                f"({type(response).__name__}); esperado AIResponse."
            )
        if not response.content or not response.content.strip():
            raise AgentError("O provedor retornou uma resposta vazia.")
        reply = response.content.strip()
        self._memory.add_message("assistant", reply)
        self.last_response = response
        return reply

    def request_plan(self, text: str) -> Plan:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("O pedido do plano não pode ser vazio.")
        cleaned = text.strip()
        if self._permissions is not None:
            self._permissions.require(PermissionLevel.CHAT)
        with self._provider_lock:
            provider = self._provider
        planner = Planner(provider, memory=self._memory_system)
        history = [m.to_dict() for m in self._memory.recent(self._context_window)]
        return planner.create_plan(cleaned, history)

    def execute_plan(self, plan, handler=None, *, verifier=None, retry=None, checkpoints=None):
        if self._permissions is not None:
            self._permissions.require(PermissionLevel.CHAT)
        from app.executor import PlanExecutor, SimulatedHandler
        executor = PlanExecutor(
            plan,
            handler or SimulatedHandler(),
            verifier=verifier,
            retry=retry,
            checkpoints=checkpoints,
        )
        return executor.run_all()
