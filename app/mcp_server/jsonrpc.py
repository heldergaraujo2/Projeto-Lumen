"""Primitivas do JSON-RPC 2.0 usadas pelo servidor MCP (Fase 3).

O MCP é JSON-RPC 2.0 sobre stdio. Este módulo implementa **só o envelope**
— parsing, validação, respostas e erros — sem conhecer MCP nem LUMEN.
Isso permite testá-lo isoladamente e reusá-lo em outro transporte.

Referência: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
(latest em 2026-07-28). Regras relevantes para stdio:

- mensagens são JSON codificado em UTF-8;
- delimitadas por ``\\n`` e **não podem conter newlines embutidas**
  (por isso ``dumps_line`` sempre emite JSON compacto);
- o servidor **não pode** escrever em stdout nada que não seja mensagem MCP
  (logs vão para stderr).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

# --------------------------------------------------------------------- códigos
#: Códigos reservados pelo JSON-RPC 2.0.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

#: Faixa reservada a implementações (-32000 a -32099).
SERVER_ERROR = -32000


class JsonRpcError(Exception):
    """Erro JSON-RPC com código e dados opcionais (vira resposta de erro)."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_error_object(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            payload["data"] = self.data
        return payload


@dataclass(frozen=True)
class JsonRpcMessage:
    """Mensagem JSON-RPC já validada no envelope.

    ``id`` é ``None`` para notificações. O JSON-RPC 2.0 aceita string,
    número ou ``None`` como id — mas **não** aceita ``null`` explícito como
    id de requisição, que é o que distingue notificação de requisição aqui.
    """

    method: str | None = None
    params: Mapping[str, Any] | None = None
    id: str | int | None = None
    result: Any = None
    error: Mapping[str, Any] | None = None
    is_notification: bool = False
    is_response: bool = False


def parse_message(raw: str) -> JsonRpcMessage:
    """Valida o envelope JSON-RPC de uma linha recebida do cliente.

    Raises:
        JsonRpcError: ``PARSE_ERROR`` para JSON inválido; ``INVALID_REQUEST``
            para JSON válido que não é um envelope JSON-RPC 2.0.
    """
    if not isinstance(raw, str):
        raise JsonRpcError(INVALID_REQUEST, "Mensagem deve ser texto UTF-8.")
    text = raw.strip()
    if not text:
        raise JsonRpcError(INVALID_REQUEST, "Mensagem vazia.")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonRpcError(PARSE_ERROR, f"JSON inválido: {exc.msg}.") from exc

    if not isinstance(payload, dict):
        raise JsonRpcError(INVALID_REQUEST, "Mensagem JSON-RPC deve ser um objeto.")

    version = payload.get("jsonrpc")
    if version != "2.0":
        raise JsonRpcError(
            INVALID_REQUEST,
            f"'jsonrpc' deve ser exatamente '2.0' (recebido: {version!r}).",
        )

    has_method = "method" in payload
    has_result = "result" in payload
    has_error = "error" in payload
    if has_method and (has_result or has_error):
        raise JsonRpcError(INVALID_REQUEST, "Mensagem não pode ter 'method' e 'result'/'error'.")
    if not has_method and not (has_result or has_error):
        raise JsonRpcError(INVALID_REQUEST, "Mensagem sem 'method' nem 'result'/'error'.")
    if has_result and has_error:
        raise JsonRpcError(INVALID_REQUEST, "Mensagem não pode ter 'result' e 'error'.")

    identifier = payload.get("id")
    if identifier is not None and not isinstance(identifier, (str, int)) \
            or isinstance(identifier, bool):
        raise JsonRpcError(
            INVALID_REQUEST,
            "'id' deve ser string, número ou ausente (notificação).",
        )

    if has_method:
        method = payload["method"]
        if not isinstance(method, str) or not method.strip():
            raise JsonRpcError(INVALID_REQUEST, "'method' deve ser texto não vazio.")
        params = payload.get("params")
        if params is not None and not isinstance(params, (dict, list)):
            raise JsonRpcError(
                INVALID_PARAMS, "'params' deve ser objeto ou lista quando presente."
            )
        # id ausente OU null => notificação (JSON-RPC 2.0 §4.1)
        return JsonRpcMessage(
            method=method,
            params=params,
            id=None if identifier is None else identifier,
            is_notification="id" not in payload or identifier is None,
        )

    return JsonRpcMessage(id=identifier, result=payload.get("result"),
                          error=payload.get("error"), is_response=True)


def success_response(identifier: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def error_response(
    identifier: str | int | None, code: int, message: str, data: Any = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return {"jsonrpc": "2.0", "id": identifier, "error": payload}


def notification(method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = dict(params)
    return payload


def dumps_line(payload: Mapping[str, Any]) -> str:
    """Serializa **compacto** — a linha não pode conter newlines (spec stdio)."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


__all__ = [
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "JsonRpcError",
    "JsonRpcMessage",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "SERVER_ERROR",
    "dumps_line",
    "error_response",
    "notification",
    "parse_message",
    "success_response",
]
