"""Agent Core da Lumen.

Orquestra o fluxo conversacional:

    permissão CHAT → contexto da memória → salvar mensagem do usuário
    → provedor de IA (com system prompt + histórico limitado
    + streaming opcional) → salvar resposta → devolver à UI.

Não conhece interface gráfica nem provedores concretos — depende apenas
das abstrações ``AIProvider`` (com :class:`~app.ai.types.AIResponse`),
``MemoryStore`` e ``PermissionManager``. O system prompt vem da persona
central (:mod:`app.config.persona`).

0.4: além do fluxo conversacional, expõe :meth:`request_plan`, que pede
ao :mod:`app.planner` um plano estruturado para um objetivo do usuário
(apenas planejamento — nenhuma tarefa é executada), e :meth:`execute_plan`,
que executa um plano READY **apenas com handlers simulados** (0.4.x —
fundação do Executor; sem ferramentas reais).
"""
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
    """Falha dentro do Agent Core (mensagem amigável ao usuário)."""


class Agent:
    """Núcleo conversacional da Lumen.

    Args:
        provider: provedor de IA (abstração — ``MockProvider``,
            ``OpenAIProvider``, …).
        memory: memória de conversa persistida.
        permissions: gerenciador de permissões (opcional; se ausente, o
            gate de ``CHAT`` é pulado — útil em testes unitários).
        task_manager: registro de tarefas (opcional; prepara o futuro
            Planner sem ser usado no fluxo de conversa).
        context_window: quantas mensagens recentes vão ao provedor
            (padrão alinhado a ``LUMEN_MAX_CONTEXT_MESSAGES``).
        system_prompt: prompt de sistema; se omitido, usa a persona
            central da Lumen (:func:`app.config.persona.build_system_prompt`).
        memory_system: memória estruturada 0.3 opcional — usada apenas
            como contexto de **leitura** pelo Planner em
            :meth:`request_plan` (o fluxo de conversa não muda).
    """

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
        #: Fachada de ferramentas (0.6.3) — injetada depois via
        #: :meth:`set_tools_controller` (main.py). Sem ela o chat segue
        #: puramente conversacional (comportamento anterior preservado).
        self._tools_controller = None
        self._memory_system = memory_system
        #: Última resposta normalizada do provedor (uso/tokens/finish_reason).
        self.last_response: AIResponse | None = None

    # ------------------------------------------------------------ propriedades
    @property
    def provider(self) -> AIProvider:
        with self._provider_lock:
            return self._provider

    def set_provider(self, provider: AIProvider) -> None:
        """Troca o provedor de IA em tempo de execução (thread-safe).

        Usado pela tela de configurações: a próxima mensagem usa o novo
        provider, sem reiniciar a aplicação.
        """
        with self._provider_lock:
            self._provider = provider
        logger.info("Provider do Agent alterado para '%s' (modelo=%s).",
                    provider.name, provider.model_name or "-")

    @property
    def memory(self) -> MemoryStore:
        return self._memory

    @property
    def task_manager(self) -> TaskManager | None:
        return self._task_manager

    @property
    def memory_system(self) -> MemorySystem | None:
        """Memória estruturada 0.3 (contexto de leitura para o Planner)."""
        return self._memory_system

    @property
    def permissions(self) -> PermissionManager | None:
        """Gerenciador de permissões do Agent (0.5.x: compõe a camada de
        controle de ferramentas — mesma instância dos gates do Agent)."""
        return self._permissions

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    # -------------------------------------------------------------------- API
    def set_tools_controller(self, controller) -> None:
        """Injeta a fachada de ferramentas para o tool calling (0.6.3).

        O Agent não ganha lógica de filesystem/terminal: ele apenas
        delega ao controller (a autoridade de segurança continua lá).
        Sem controller injetado, :meth:`process_message` se comporta
        exatamente como :meth:`send_message`.
        """
        self._tools_controller = controller

    def process_message(
        self, text: str, on_delta: DeltaCallback | None = None
    ) -> AgentOutcome:
        """Processa uma mensagem decidindo CONVERSA × AÇÃO (0.6.3).

        Com fachada de ferramentas injetada, a mensagem passa pela
        ponte CHAT → PLANNER (allowlist de ferramentas) → VALIDAÇÃO →
        ``ToolsController.run_plan`` → permissões → workspace →
        checkpoint → execução → verificação. Sem fachada (ou para
        pedidos conversacionais), o fluxo clássico de
        :meth:`send_message` roda intacto (streaming incluído).

        Devolve um :class:`~app.core.bridge.AgentOutcome` — ``text`` é
        sempre uma mensagem pronta para a UI.
        """
        if self._tools_controller is None:
            reply = self.send_message(text, on_delta=on_delta)
            return AgentOutcome(RequestState.CONVERSATIONAL, reply)
        bridge = ToolCallingBridge(self, self._tools_controller)
        return bridge.process(text, on_delta=on_delta)

    def request_tool_plan(self, text: str, catalog: dict | None = None):
        """Pede ao Planner um plano COM ferramentas (0.6.3 — tool calling).

        Usa o provedor vigente com a **allowlist** ``catalog`` (produzida
        pelo ``ToolsController.planning_catalog()``): o provedor só pode
        referenciar ferramentas dessa lista; a validação de protocolo
        acontece no Planner (:mod:`app.planner.catalog`) e a de execução
        (permissões/sandbox/checkpoint) na cadeia de tools. Nenhuma
        tarefa é executada aqui.

        Raises:
            ValueError: pedido vazio.
            PermissionDeniedError: sem permissão ``CHAT``.
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("O pedido do plano não pode ser vazio.")
        cleaned = text.strip()

        if self._permissions is not None:
            self._permissions.require(PermissionLevel.CHAT)

        with self._provider_lock:
            provider = self._provider  # snapshot thread-safe

        planner = Planner(provider, memory=self._memory_system, catalog=catalog)
        history = [m.to_dict() for m in self._memory.recent(self._context_window)]
        result = planner.create_tool_plan(cleaned, history)
        plan = result.plan
        logger.info(
            "Plano com ferramentas %s: kind=%s, status=%s, %d tarefa(s) "
            "(provedor=%s).",
            plan.id, result.kind, plan.status.value, len(plan.tasks),
            provider.name,
        )
        return result

    def send_message(self, text: str, on_delta: DeltaCallback | None = None) -> str:
        """Processa uma mensagem do usuário e devolve a resposta (texto).

        Args:
            text: mensagem atual do usuário.
            on_delta: callback opcional que recebe pedaços de texto assim
                que chegam (streaming); a soma dos pedaços equivale ao
                texto final devolvido.

        Raises:
            ValueError: mensagem vazia.
            PermissionDeniedError: sem permissão ``CHAT``.
            AgentError: falha do provedor (mensagem amigável; detalhes
                técnicos ficam no log).
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("A mensagem não pode ser vazia.")
        cleaned = text.strip()

        if self._permissions is not None:
            # Gate mínimo da fase 0 — demonstra o padrão para tools futuras.
            self._permissions.require(PermissionLevel.CHAT)

        with self._provider_lock:
            provider = self._provider  # snapshot thread-safe

        history = self._memory.recent(self._context_window)
        self._memory.add_message("user", cleaned)
        logger.info("Mensagem do usuário recebida (%d caracteres).", len(cleaned))

        try:
            response = provider.chat(
                cleaned,
                [m.to_dict() for m in history],
                system_prompt=self._system_prompt,
                on_delta=on_delta,
            )
        except ProviderError as exc:
            friendly = user_message_for(exc)
            logger.error(
                "Provedor '%s' falhou (%s): %s",
                provider.name, type(exc).__name__, exc,
            )
            raise AgentError(friendly) from exc
        except Exception as exc:  # erros inesperados do provedor
            logger.error(
                "Erro inesperado no provedor '%s' (%s).",
                provider.name, type(exc).__name__,
            )
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
        logger.info(
            "Resposta gerada pelo provedor '%s' (modelo=%s, %d caracteres).",
            provider.name, response.model or "?", len(reply),
        )
        return reply

    # ------------------------------------------------------------ planejamento
    def request_plan(self, text: str) -> Plan:
        """Pede ao Planner um plano estruturado para ``text`` (0.4).

        Usa o provedor vigente (respeita troca em runtime) e, quando
        disponível, consulta a memória estruturada 0.3 como contexto de
        leitura. **Nenhuma tarefa é executada** — o plano devolvido é
        apenas dados (ver :mod:`app.planner`).

        Não altera a conversa nem o fluxo de :meth:`send_message`.

        Raises:
            ValueError: pedido vazio.
            PermissionDeniedError: sem permissão ``CHAT``.
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("O pedido do plano não pode ser vazio.")
        cleaned = text.strip()

        if self._permissions is not None:
            self._permissions.require(PermissionLevel.CHAT)

        with self._provider_lock:
            provider = self._provider  # snapshot thread-safe

        planner = Planner(provider, memory=self._memory_system)
        history = [m.to_dict() for m in self._memory.recent(self._context_window)]
        plan = planner.create_plan(cleaned, history)
        logger.info(
            "Plano %s: status=%s, %d tarefa(s) (provedor=%s).",
            plan.id, plan.status.value, len(plan.tasks), provider.name,
        )
        return plan

    # -------------------------------------------------------------- execução
    def execute_plan(
        self,
        plan,
        handler=None,
        *,
        verifier=None,
        retry=None,
        checkpoints=None,
    ):
        """Executa as tarefas de um ``Plan`` READY (0.4.x).

        Usa o :class:`~app.executor.PlanExecutor` com um handler
        **simulado/in-memory** por padrão — nenhuma ferramenta real
        existe nesta versão. Parâmetros nomeados opcionais (0.4.x):
        ``verifier`` (:class:`~app.executor.TaskVerifier` simulado),
        ``retry`` (:class:`~app.executor.RetryPolicy`) e ``checkpoints``
        (:class:`~app.executor.CheckpointPolicy`). Não altera a conversa
        nem a memória; o resultado completo volta no
        :class:`~app.executor.ExecutionReport`.

        Raises:
            PermissionDeniedError: sem permissão ``CHAT``.
            ExecutorError: plano não ``READY``/inválido para execução.
        """
        if self._permissions is not None:
            self._permissions.require(PermissionLevel.CHAT)

        from app.executor import PlanExecutor, SimulatedHandler  # lazy: mantém o Agent enxuto

        executor = PlanExecutor(
            plan, handler or SimulatedHandler(),
            verifier=verifier, retry=retry, checkpoints=checkpoints,
        )
        report = executor.run_all()
        logger.info(
            "Execução do plano %s: %s (%d/%d tarefas concluídas).",
            report.plan_id, report.status.value,
            sum(1 for r in report.tasks if r.status.value == "DONE"),
            len(report.tasks),
        )
        return report
