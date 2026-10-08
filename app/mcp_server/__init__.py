"""Servidor MCP do LUMEN (Fase 3).

Expõe as ferramentas do LUMEN a clientes MCP (Claude Desktop, Cline, …)
via **JSON-RPC 2.0 sobre stdio** — o transporte oficial para servidores
locais segundo a spec.

A regra que organiza este pacote: **o MCP é uma porta, não uma porta dos
fundos.** Toda chamada vinda do cliente entra pela mesma cadeia de
segurança que o usuário veria na UI (``run_tool_call`` → ``Plan`` →
permissões → sandbox → checkpoint → auditoria). Nada aqui concede
permissão ou aprova escrita por conta própria.

::

    cliente MCP ──stdio──▶ jsonrpc.py ──▶ server.py ──▶ gateway.py
                                                          │
                                             ToolsController.run_tool_call
                                                          │
                                        permissões · sandbox · checkpoints
"""
from __future__ import annotations

from app.mcp_server.gateway import (
    CHECKPOINT_PENDING_MESSAGE,
    ControllerToolGateway,
    McpGatewayError,
    ToolCallOutcome,
)
from app.mcp_server.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    JsonRpcError,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    dumps_line,
    error_response,
    notification,
    parse_message,
    success_response,
)
from app.mcp_server.schema import (
    parameter_to_json_schema,
    tool_definition_to_mcp_schema,
    tool_definitions_to_mcp_schemas,
)
from app.mcp_server.server import (
    PROTOCOL_VERSION,
    SERVER_INSTRUCTIONS,
    SERVER_NAME,
    SUPPORTED_PROTOCOL_VERSIONS,
    McpServer,
)
from app.mcp_server.stdio import StdioStats, serve_stdio

__all__ = [
    "CHECKPOINT_PENDING_MESSAGE",
    "ControllerToolGateway",
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "JsonRpcError",
    "METHOD_NOT_FOUND",
    "McpGatewayError",
    "McpServer",
    "PARSE_ERROR",
    "PROTOCOL_VERSION",
    "SERVER_INSTRUCTIONS",
    "SERVER_NAME",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "StdioStats",
    "ToolCallOutcome",
    "dumps_line",
    "error_response",
    "notification",
    "parameter_to_json_schema",
    "parse_message",
    "serve_stdio",
    "success_response",
    "tool_definition_to_mcp_schema",
    "tool_definitions_to_mcp_schemas",
]
