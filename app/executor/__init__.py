"""Executor de Planos da Lumen (0.4.x).

Executa as tarefas de um ``Plan`` READY de forma controlada e
determinística, **apenas com handlers/verificadores simulados
in-memory** — nenhuma ferramenta real existe nesta etapa. Separação
rigorosa: o Planner produz planos; o Executor coordena a execução
(ordem/dependências, checkpoints, retry, verificação); a ação de cada
tarefa vive em um :class:`TaskHandler` e a conferência de resultados em
um :class:`TaskVerifier` (futuro: ferramentas reais via ToolRegistry).
"""
from app.executor.checkpoints import (
    CheckpointPolicy,
    CheckpointRequest,
    CheckpointStatus,
    EveryTaskCheckpoints,
    NeverCheckpoints,
)
from app.executor.correction import (
    CorrectionProposal,
    CorrectionStrategy,
    NoopCorrectionStrategy,
)
from app.executor.executor import (
    ExecutionEvent,
    ExecutionObserver,
    ExecutionReport,
    ExecutorError,
    PlanExecutor,
    TaskRun,
)
from app.executor.handlers import HandlerError, SimulatedHandler, TaskHandler
from app.executor.retry import AttemptRecord, RetryPolicy
from app.executor.verification import (
    SimulatedVerifier,
    TaskVerifier,
    VerificationResult,
)

__all__ = [
    "AttemptRecord",
    "CheckpointPolicy",
    "CheckpointRequest",
    "CheckpointStatus",
    "CorrectionProposal",
    "CorrectionStrategy",
    "EveryTaskCheckpoints",
    "ExecutionEvent",
    "ExecutionObserver",
    "ExecutionReport",
    "ExecutorError",
    "HandlerError",
    "NeverCheckpoints",
    "NoopCorrectionStrategy",
    "PlanExecutor",
    "RetryPolicy",
    "SimulatedHandler",
    "SimulatedVerifier",
    "TaskHandler",
    "TaskRun",
    "TaskVerifier",
    "VerificationResult",
]
