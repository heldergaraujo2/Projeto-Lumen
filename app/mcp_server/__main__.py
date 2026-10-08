"""Entrada executável do servidor MCP: ``python -m app.mcp_server``.

Uso típico (chamado pelo cliente MCP, ex.: Claude Desktop ou Cline)::

    python -m app.mcp_server --workspace "C:/MeuProjeto" --allow-read

Variáveis de ambiente (todas opcionais, nenhuma concede escrita sozinha):

- ``LUMEN_MCP_WORKSPACES``: caminhos separados por ``os.pathsep``;
- ``LUMEN_MCP_ALLOW_WRITE``: ``1``/``true`` expõe as tools destrutivas;
- ``LUMEN_MCP_AUTO_APPROVE``: ``1``/``true`` resolve os checkpoints
  automaticamente (**exige** ``ALLOW_WRITE``) — é autorização prévia e
  explícita do humano que inicia o processo;
- ``LUMEN_MCP_TERMINAL_ALLOWLIST``: comandos separados por vírgula que
  habilitam ``run_command``/``run_pytest``.

Sobre ``--allow-write``/``--auto-approve``: o checkpoint do LUMEN existe
para impedir escrita destrutiva *sem consentimento*. Um cliente MCP não
tem como clicar "aprovar" na UI do LUMEN quando o servidor roda como
subprocess do Claude Desktop. Estas flags são o consentimento — dado de
forma explícita, nomeada e auditada por quem inicia o servidor. Sem elas,
o servidor é somente-leitura e diz isso ao cliente.

Nenhuma parte do logging vai para o stdout: a spec de stdio proíbe
qualquer byte que não seja mensagem MCP (logs vão para o stderr).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from app.mcp_server.gateway import ControllerToolGateway, McpGatewayError
from app.mcp_server.server import McpServer
from app.mcp_server.stdio import serve_stdio
from app.security.permissions import PermissionLevel, PermissionManager
from app.tools.control import ToolsController

logger = logging.getLogger("lumen.mcp")

WRITE_FLAG = "LUMEN_MCP_ALLOW_WRITE"
AUTO_APPROVE_FLAG = "LUMEN_MCP_AUTO_APPROVE"
WORKSPACES_ENV = "LUMEN_MCP_WORKSPACES"
TERMINAL_ENV = "LUMEN_MCP_TERMINAL_ALLOWLIST"
LOG_ENV = "LUMEN_MCP_LOG_LEVEL"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.mcp_server",
        description="Servidor MCP do LUMEN (JSON-RPC 2.0 sobre stdio).",
    )
    parser.add_argument(
        "--workspace", action="append", default=[], metavar="CAMINHO",
        help="Diretório autorizado (pode repetir). Sem isto, só os workspaces "
             "salvos no LUMEN valem.",
    )
    parser.add_argument(
        "--allow-read", action="store_true",
        help="Concede permissão READ (listar/ler arquivos).",
    )
    parser.add_argument(
        "--allow-write", action="store_true",
        help="Expõe as ferramentas destrutivas (write_file/create_file/"
             "create_directory/delete_file/edit_file). Sem esta flag o "
             "servidor é SOMENTE LEITURA.",
    )
    parser.add_argument(
        "--auto-approve", action="store_true",
        help="Aprova automaticamente os checkpoints (exige --allow-write). "
             "Equivale a autorizar previamente toda escrita do cliente MCP.",
    )
    parser.add_argument(
        "--terminal", default="", metavar="CMD1,CMD2",
        help="Allowlist do terminal (ex.: 'UnrealBuildTool,git'). Habilita "
             "run_command/run_pytest; exige concessão de permissão TERMINAL.",
    )
    parser.add_argument(
        "--allow-terminal", action="store_true",
        help="Concede permissão TERMINAL (só faz sentido com --terminal).",
    )
    parser.add_argument(
        "--enable-web-search", action="store_true",
        help="Habilita web_search se TAVILY_API_KEY/BRAVE_API_KEY estiver configurada.",
    )
    parser.add_argument(
        "--enable-unreal-bridge", action="store_true",
        help="Habilita as tools unreal_* (exigem também --allow-write); não conecta até o uso.",
    )
    parser.add_argument(
        "--data-dir", default="", metavar="PASTA",
        help="Pasta de dados do LUMEN. Default: a mesma que a aplicação usa "
             "(LUMEN_DATA_DIR ou <repo>/data), para reaproveitar os workspaces "
             "que o usuário já autorizou na UI.",
    )
    parser.add_argument("--version", action="store_true", help="Mostra a versão e sai.")
    return parser


def _data_dir(raw: str) -> Path:
    """Resolve a pasta de dados do LUMEN sem depender da UI.

    Reusar a mesma pasta do app é deliberado: os workspaces que o usuário
    autorizou na UI passam a valer para o servidor MCP, em vez de existir
    uma segunda lista de autorizações que ninguém revisou.
    """
    from app.config.settings import Settings

    if raw:
        os.environ["LUMEN_DATA_DIR"] = raw
    return Settings.load().data_dir


def _configure_logging() -> None:
    level = os.environ.get(LOG_ENV, "WARNING").strip().upper() or "WARNING"
    logging.basicConfig(
        stream=sys.stderr,          # NUNCA stdout: a spec proíbe
        level=getattr(logging, level, logging.WARNING),
        format="[lumen-mcp] %(levelname)s %(name)s: %(message)s",
    )


def build_controller(args: argparse.Namespace) -> ToolsController:
    """Monta o controller com **exatamente** o que o operador autorizou."""
    permissions = PermissionManager()
    if args.allow_read:
        permissions.grant(PermissionLevel.READ)
    if args.allow_write:
        permissions.grant(PermissionLevel.WRITE)
    if args.allow_terminal:
        permissions.grant(PermissionLevel.TERMINAL)

    data_dir = _data_dir(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    controller = ToolsController(
        permissions,
        workspaces_file=data_dir / "workspaces.json",
        audit_file=data_dir / "audit" / "audit.jsonl",
        # Sem `terminal_file`: o servidor MCP não persiste nem restaura
        # allowlist do disco. A allowlist de terminal aqui vem só de
        # `--terminal`/env desta execução — decisão explícita por processo.
        terminal_file=None,
    )
    for path in list(args.workspace) + _env_workspaces():
        try:
            controller.add_workspace(
                path, writable=args.allow_write, allow_delete=False
            )
        except Exception as exc:  # caminho inválido não deve derrubar o servidor
            logger.error("Workspace recusado (%s): %s", path, exc)

    allowlist = [c.strip() for c in args.terminal.split(",") if c.strip()]
    if allowlist:
        try:
            controller.enable_terminal(allowlist)
        except Exception as exc:
            logger.error("Allowlist de terminal recusada: %s", exc)
    return controller


def _env_workspaces() -> list[str]:
    raw = os.environ.get(WORKSPACES_ENV, "")
    return [part for part in raw.split(os.pathsep) if part.strip()] if raw else []


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging()

    if args.version:
        from app import __version__

        print(f"LUMEN MCP server {__version__}", file=sys.stderr)
        return 0

    allow_write = bool(args.allow_write) or _env_flag(WRITE_FLAG)
    auto_approve = bool(args.auto_approve) or _env_flag(AUTO_APPROVE_FLAG)
    if auto_approve and not allow_write:
        print("[lumen-mcp] auto_approve exige allow_write (--allow-write ou LUMEN_MCP_ALLOW_WRITE).", file=sys.stderr)
        return 2
    # A mesma decisão efetiva precisa reger a exposição, a concessão WRITE
    # e a política writable dos workspaces (inclusive quando veio do env).
    args.allow_write = allow_write
    if not args.terminal:
        args.terminal = os.environ.get(TERMINAL_ENV, "")

    controller = build_controller(args)
    if args.enable_web_search:
        result = controller.enable_web_search()
        if not result["enabled"]:
            logger.warning("Pesquisa web não habilitada: %s", result["reason"])
    if args.enable_unreal_bridge:
        from app.unreal_bridge.client import RemoteControlClient
        from app.unreal_bridge.config import UnrealBridgeConfig

        try:
            client = RemoteControlClient(UnrealBridgeConfig.from_env())
            result = controller.enable_unreal_bridge(client=client)
            if not result["enabled"]:
                logger.warning("Ponte Unreal não habilitada: %s", result["reason"])
        except Exception as exc:
            logger.warning("Ponte Unreal não habilitada: %s", exc)
    try:
        gateway = ControllerToolGateway(
            controller, allow_write=allow_write, auto_approve=auto_approve
        )
    except McpGatewayError as exc:
        print(f"[lumen-mcp] configuração inválida: {exc}", file=sys.stderr)
        return 2

    server = McpServer(gateway)
    logger.warning(
        "Servidor MCP iniciado: %d ferramenta(s) exposta(s); escrita=%s; "
        "auto-aprovação=%s; workspaces=%s.",
        len(gateway.exposed_names()),
        "SIM" if allow_write else "não",
        "SIM" if auto_approve else "não",
        sorted(controller.list_workspaces()) if hasattr(controller, "list_workspaces") else args.workspace,
    )
    if auto_approve:
        logger.warning(
            "AUTO-APROVAÇÃO ATIVA: operações destrutivas solicitadas pelo cliente "
            "MCP serão aprovadas sem confirmação interativa no LUMEN."
        )

    serve_stdio(server, sys.stdin, sys.stdout, stderr=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
