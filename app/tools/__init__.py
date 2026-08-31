"""Sistema de ferramentas (tools) da Lumen.

0.5: além do contrato (``Tool``/``ToolRegistry``/``ToolResult``), o
pacote traz a primeira camada de ferramentas reais — **filesystem
confinado a um workspace autorizado e auditado**
(:mod:`app.tools.filesystem`) — e a ponte Executor ↔ ferramentas
(:mod:`app.tools.handler`). 0.6: **terminal controlado** — allowlist
explícita, denylist permanente, timeout, limite de saída e auditoria
(:mod:`app.tools.terminal`). Registro de ferramentas é sempre
**explícito** (nada é registrado no startup).
"""

from app.tools.base import (
    StructuredTool,
    Tool,
    ToolError,
    ToolNotFoundError,
    ToolRegistry,
    ToolResult,
)
from app.tools.audit_log import JsonlAuditSink, read_audit_tail
from app.tools.correction import (
    ToolCorrectionStrategy,
    build_proposal_validator,
)
from app.tools.control import (
    MANAGEABLE_LEVELS,
    OPERATION_LABELS,
    ToolsControlError,
    ToolsController,
)
from app.tools.filesystem import (
    FILESYSTEM_DESTRUCTIVE_TOOLS,
    FILESYSTEM_TOOLS,
    AuditRecord,
    DeleteNotAllowedError,
    FilesystemAudit,
    FilesystemError,
    FilesystemTool,
    InvalidPathError,
    PathOutsideWorkspaceError,
    WorkspaceSandbox,
    WriteNotAllowedError,
    build_filesystem_registry,
)
from app.tools.handler import ToolCheckpoints, ToolTaskHandler
from app.tools.terminal import (
    DANGEROUS_ARGUMENTS,
    FORBIDDEN_COMMANDS,
    AllowedCommand,
    CommandNotAllowlistedError,
    InterpreterForbiddenError,
    OperatorForbiddenError,
    PrevalidatedTerminalCheckpoints,
    RunCommandTool,
    TERMINAL_OPERATION,
    TERMINAL_TOOL_NAME,
    TerminalPolicy,
    TerminalSecurityError,
    TerminalStore,
    TerminalStoreError,
    build_terminal_registry,
)
from app.tools.workspaces import (
    MultiWorkspaceSandbox,
    WorkspaceEntry,
    WorkspaceStore,
    WorkspaceStoreError,
)

__all__ = [
    "AuditRecord",
    "DANGEROUS_ARGUMENTS",
    "DeleteNotAllowedError",
    "FORBIDDEN_COMMANDS",
    "AllowedCommand",
    "CommandNotAllowlistedError",
    "InterpreterForbiddenError",
    "OperatorForbiddenError",
    "FILESYSTEM_DESTRUCTIVE_TOOLS",
    "FILESYSTEM_TOOLS",
    "FilesystemAudit",
    "FilesystemError",
    "FilesystemTool",
    "InvalidPathError",
    "JsonlAuditSink",
    "MANAGEABLE_LEVELS",
    "MultiWorkspaceSandbox",
    "OPERATION_LABELS",
    "PathOutsideWorkspaceError",
    "PrevalidatedTerminalCheckpoints",
    "RunCommandTool",
    "StructuredTool",
    "TERMINAL_OPERATION",
    "TERMINAL_TOOL_NAME",
    "TerminalPolicy",
    "TerminalSecurityError",
    "TerminalStore",
    "TerminalStoreError",
    "ToolCorrectionStrategy",
    "build_proposal_validator",
    "Tool",
    "ToolCheckpoints",
    "ToolError",
    "ToolNotFoundError",
    "ToolRegistry",
    "ToolResult",
    "ToolTaskHandler",
    "ToolsControlError",
    "ToolsController",
    "WorkspaceEntry",
    "WorkspaceSandbox",
    "WorkspaceStore",
    "WorkspaceStoreError",
    "WriteNotAllowedError",
    "build_filesystem_registry",
    "build_terminal_registry",
    "read_audit_tail",
]
