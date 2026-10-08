"""Transporte stdio do servidor MCP (Fase 3).

Regras da spec que este módulo implementa:

- o servidor lê JSON-RPC do ``stdin`` e escreve no ``stdout``;
- as mensagens são delimitadas por ``\\n`` e não contêm newlines embutidas;
- **nada** além de mensagem MCP vai para o ``stdout`` — logs vão para o
  ``stderr`` (por isso o logging do processo aponta para lá em
  ``__main__.py``);
- EOF no ``stdin`` encerra o laço (o cliente fechou o processo).

O laço é escrito sobre objetos de arquivo injetáveis para que os testes
rodem sem subprocess.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import IO, Any

from app.mcp_server.jsonrpc import (
    INVALID_REQUEST,
    JsonRpcError,
    dumps_line,
    error_response,
    parse_message,
)

logger = logging.getLogger(__name__)

#: Teto de bytes de uma linha recebida, antes de recusar por tamanho.
MAX_LINE_BYTES = 4 * 1024 * 1024


@dataclass
class StdioStats:
    """Contadores do laço, úteis para log de encerramento e para testes."""

    messages_read: int = 0
    responses_written: int = 0
    parse_errors: int = 0
    bytes_written: int = 0


def serve_stdio(
    server: Any,
    stdin: IO[str],
    stdout: IO[str],
    *,
    stderr: IO[str] | None = None,
    stats: StdioStats | None = None,
    max_line_bytes: int = MAX_LINE_BYTES,
) -> StdioStats:
    """Laço principal: lê linhas do ``stdin``, responde no ``stdout``.

    Retorna ao encontrar EOF, após registrar o resumo em ``stderr``.
    Erros de nível de transporte (linha ilegível, escrita quebrada) são
    fatais e encerram o laço — não há protocolo de recuperação em stdio
    além de continuar lendo a próxima linha, que é o que fazemos para
    erros de *conteúdo*.
    """
    counters = stats if stats is not None else StdioStats()

    while True:
        try:
            raw = stdin.readline()
        except UnicodeDecodeError:  # pragma: no cover - entrada binária inválida
            logger.error("Entrada não é UTF-8 válido; encerrando o servidor MCP.")
            break
        if raw == "":
            break  # EOF: o cliente fechou a entrada
        counters.messages_read += 1

        if len(raw.encode("utf-8", errors="replace")) > max_line_bytes:
            counters.parse_errors += 1
            # `_write` recebe a linha JÁ serializada — passar o dict cru aqui
            # estourava TypeError no meio do laço e derrubava o servidor.
            _write(
                stdout,
                dumps_line(error_response(
                    None,
                    INVALID_REQUEST,
                    f"Mensagem excede o limite de {max_line_bytes} bytes.",
                )),
                counters,
            )
            continue

        try:
            text = server.handle_line_to_text(raw.rstrip("\n"))
        except JsonRpcError as exc:  # pragma: no cover - handle_message trata
            counters.parse_errors += 1
            text = dumps_line(error_response(None, exc.code, exc.message, exc.data))
        if text is None:
            continue  # notificação: não há resposta
        _write(stdout, text, counters)

    if stderr is not None:
        stderr.write(
            f"[mcp] encerrado: {counters.messages_read} mensagem(ns) lida(s), "
            f"{counters.responses_written} resposta(s) escrita(s).\n"
        )
        stderr.flush()
    return counters


def _write(stdout: IO[str], text: str, counters: StdioStats) -> None:
    stdout.write(text + "\n")
    stdout.flush()
    counters.responses_written += 1
    counters.bytes_written += len(text) + 1


def decode_params(payload: Any) -> Any:  # pragma: no cover - utilidade de teste
    """Helper exposto para testes que querem validar params brutos."""
    return parse_message(dumps_line(payload)).params


__all__ = ["MAX_LINE_BYTES", "StdioStats", "serve_stdio"]
