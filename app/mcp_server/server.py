"""Servidor MCP (Fase 3) — JSON-RPC 2.0 sobre stdio.

Implementa o subconjunto do MCP necessário para expor as ferramentas do
LUMEN a um cliente (Claude Desktop, Cline, …):

- ``initialize`` → negociação de versão + capacidades + ``serverInfo``;
- ``notifications/initialized`` → marca a sessão como pronta;
- ``tools/list`` → schemas no formato oficial, derivados do
  ``ToolDefinition`` do LUMEN (``schema.py``);
- ``tools/call`` → execução pelo gateway que preserva permissões/sandbox/
  checkpoint (``gateway.py``);
- ``ping`` → keep-alive.

O método ``handle_message`` é **puro em relação ao transporte**: recebe uma
linha crua e devolve o dicionário de resposta (ou ``None`` para
notificações). Por isso é testável sem subprocess.

Referências:
- https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
- https://modelcontextprotocol.io/specification/2025-06-18/server/tools
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from app.mcp_server.gateway import ControllerToolGateway, McpGatewayError
from app.mcp_server.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    JsonRpcError,
    METHOD_NOT_FOUND,
    SERVER_ERROR,
    dumps_line,
    error_response,
    parse_message,
    success_response,
)
from app.mcp_server.schema import tool_definitions_to_mcp_schemas

logger = logging.getLogger(__name__)

#: Versão do protocolo MCP que este servidor implementa e prefere.
#: Verificada contra a spec em 2026-10-08 (a "latest" é 2026-07-28; a
#: 2025-06-18 é a versão cujo schema de tools foi conferido linha a linha).
PROTOCOL_VERSION = "2025-06-18"

#: Versões que aceitamos ecoar quando o cliente pede uma delas.
#: A regra da spec: se o servidor suporta a versão pedida, responde com
#: **a mesma**; caso contrário responde com a que ele suporta.
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)

SERVER_NAME = "lumen"
SERVER_INSTRUCTIONS = (
    "Servidor MCP do LUMEN. As ferramentas operam no PC do usuário através "
    "da cadeia de segurança do LUMEN: permissões, workspaces autorizados e "
    "checkpoints continuam valendo. Ferramentas destrutivas só aparecem se o "
    "operador habilitou escrita ao iniciar o servidor; e mesmo então cada "
    "operação pode exigir aprovação do usuário."
)


class McpServer:
    """Manipulador de mensagens MCP.

    Args:
        gateway: ponte para as ferramentas do LUMEN.
        server_name/server_version: identidade informada em ``initialize``.
        instructions: texto opcional entregue ao LLM na inicialização.
    """

    def __init__(
        self,
        gateway: ControllerToolGateway,
        *,
        server_name: str = SERVER_NAME,
        server_version: str = "0.1.0",
        instructions: str = SERVER_INSTRUCTIONS,
    ) -> None:
        self._gateway = gateway
        self._server_name = server_name
        self._server_version = server_version
        self._instructions = instructions
        self._initialized = False
        self._client_info: Mapping[str, Any] | None = None
        self._negotiated_version: str | None = None
        self._checkpoints_seen: list[dict[str, Any]] = []

    # ------------------------------------------------------------- estado
    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def negotiated_version(self) -> str | None:
        return self._negotiated_version

    @property
    def client_info(self) -> Mapping[str, Any] | None:
        return self._client_info

    @property
    def checkpoints_seen(self) -> tuple[dict[str, Any], ...]:
        """Checkpoints encontrados em chamadas — para inspeção/teste."""
        return tuple(self._checkpoints_seen)

    @property
    def gateway(self) -> ControllerToolGateway:
        return self._gateway

    # ------------------------------------------------------------ roteador
    def handle_message(self, raw: str) -> dict[str, Any] | None:
        """Processa uma linha e devolve a resposta (``None`` p/ notificação)."""
        try:
            message = parse_message(raw)
        except JsonRpcError as exc:
            # Id desconhecido em erro de parse: a spec manda id null.
            return error_response(None, exc.code, exc.message, exc.data)

        if message.is_response:
            logger.debug("Resposta inesperada do cliente ignorada: %s", message.id)
            return None

        if message.is_notification:
            self._handle_notification(message.method or "", message.params)
            return None

        try:
            result = self._dispatch(message.method or "", message.params)
        except JsonRpcError as exc:
            return error_response(message.id, exc.code, exc.message, exc.data)
        except Exception as exc:  # pragma: no cover - salvaguarda
            logger.exception("Erro interno processando %s.", message.method)
            return error_response(
                message.id, INTERNAL_ERROR, f"Erro interno: {exc}"
            )
        return success_response(message.id, result)

    def handle_line_to_text(self, raw: str) -> str | None:
        """Conveniência para transporte: resposta já serializada em uma linha."""
        response = self.handle_message(raw)
        return None if response is None else dumps_line(response)

    # ------------------------------------------------------------- métodos
    def _dispatch(self, method: str, params: Mapping[str, Any] | None) -> Any:
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            self._require_initialized()
            return {"tools": tool_definitions_to_mcp_schemas(self._gateway.definitions())}
        if method == "tools/call":
            self._require_initialized()
            return self._tools_call(params)
        raise JsonRpcError(METHOD_NOT_FOUND, f"Método não suportado: {method!r}.")

    def _handle_notification(self, method: str, params: Mapping[str, Any] | None) -> None:
        if method == "notifications/initialized":
            self._initialized = True
            logger.info("Cliente MCP concluiu a inicialização.")
            return
        if method == "notifications/cancelled":
            logger.info("Cliente MCP cancelou uma requisição: %s", params)
            return
        # Notificações desconhecidas são ignoradas de propósito (spec §lifecycle:
        # o receptor NÃO deve responder a notificações, nem com erro).
        logger.debug("Notificação MCP ignorada: %s", method)

    def _initialize(self, params: Mapping[str, Any] | None) -> dict[str, Any]:
        if not isinstance(params, Mapping):
            raise JsonRpcError(INVALID_PARAMS, "'initialize' exige um objeto de parâmetros.")
        requested = params.get("protocolVersion")
        if not isinstance(requested, str) or not requested.strip():
            raise JsonRpcError(
                INVALID_PARAMS, "'initialize' exige 'protocolVersion' como texto."
            )
        client_info = params.get("clientInfo")
        if client_info is not None and not isinstance(client_info, Mapping):
            raise JsonRpcError(INVALID_PARAMS, "'clientInfo' deve ser um objeto.")

        # Negociação: ecoa a versão pedida quando suportada; senão oferece a nossa.
        negotiated = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        if negotiated != requested:
            logger.warning(
                "Cliente pediu MCP %s; respondendo com %s (não suportada).",
                requested, negotiated,
            )
        self._negotiated_version = negotiated
        self._client_info = client_info

        return {
            "protocolVersion": negotiated,
            "capabilities": {
                # Só `tools`. Não anunciamos `listChanged` porque o catálogo do
                # LUMEN é fixo durante a sessão (mudar isso exigiria emitir
                # notifications/tools/list_changed, que não fazemos).
                "tools": {"listChanged": False},
            },
            "serverInfo": {"name": self._server_name, "version": self._server_version},
            "instructions": self._instructions,
        }

    def _require_initialized(self) -> None:
        if self._negotiated_version is None:
            raise JsonRpcError(
                SERVER_ERROR,
                "O cliente precisa enviar 'initialize' antes de 'tools/list'/'tools/call'.",
            )

    def _tools_call(self, params: Mapping[str, Any] | None) -> dict[str, Any]:
        if not isinstance(params, Mapping):
            raise JsonRpcError(INVALID_PARAMS, "'tools/call' exige um objeto de parâmetros.")
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise JsonRpcError(INVALID_PARAMS, "'tools/call' exige 'name' como texto.")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping):
            raise JsonRpcError(INVALID_PARAMS, "'arguments' deve ser um objeto.")

        try:
            outcome = self._gateway.call(
                name, arguments,
                on_checkpoint=self._checkpoints_seen.append,
            )
        except McpGatewayError as exc:
            # Tool fora da exposição: para o MCP é "tool desconhecida".
            raise JsonRpcError(METHOD_NOT_FOUND, str(exc)) from exc

        content: list[dict[str, Any]] = [{"type": "text", "text": outcome.text}]
        return {
            "content": content,
            "structuredContent": outcome.structured,
            # `isError` é o único sinal de falha no resultado de tools/call.
            # Aguardar aprovação NÃO é erro de execução: nada rodou ainda.
            "isError": not outcome.ok and not outcome.awaiting_approval,
        }


__all__ = [
    "McpServer",
    "PROTOCOL_VERSION",
    "SERVER_INSTRUCTIONS",
    "SERVER_NAME",
    "SUPPORTED_PROTOCOL_VERSIONS",
]
