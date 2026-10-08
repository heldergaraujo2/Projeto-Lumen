"""Testes do servidor MCP (Fase 3).

Três alvos:

1. **envelope JSON-RPC 2.0** — códigos de erro, id ecoado, notificação sem
   resposta, mensagem malformada;
2. **serializer de schema** — ``ToolDefinition`` → formato oficial de tool
   MCP (``inputSchema``/``annotations``), incluindo tipos não mapeados;
3. **fronteira de segurança** — o que o servidor expõe e o que acontece
   quando o cliente tenta passar por cima (tool não exposta, escrita sem
   autorização, checkpoint pendente).

Nada aqui abre socket nem sobe subprocess: o servidor é alimentado com
strings, como o transporte stdio faria.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from app.mcp_server import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    ControllerToolGateway,
    JsonRpcError,
    McpGatewayError,
    McpServer,
    PROTOCOL_VERSION,
    dumps_line,
    parse_message,
    serve_stdio,
)
from app.mcp_server.schema import (
    UnsupportedParameterTypeError,
    parameter_to_json_schema,
    tool_definition_to_mcp_schema,
)
from app.security.permissions import PermissionLevel, PermissionManager
from app.tools.control import ToolsController
from app.tools.protocol import ParameterDefinition, ToolDefinition

INIT_PARAMS = {"protocolVersion": PROTOCOL_VERSION, "clientInfo": {"name": "t", "version": "1"}}


# ------------------------------------------------------------------ fixtures
@pytest.fixture()
def workspace(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "existente.txt").write_text("conteúdo lido", encoding="utf-8")
    (root / "sub").mkdir()
    return root


def make_controller(tmp_path, workspace, *, write=True, terminal=False):
    permissions = PermissionManager()
    permissions.grant(PermissionLevel.CHAT)
    permissions.grant(PermissionLevel.READ)
    if write:
        permissions.grant(PermissionLevel.WRITE)
    if terminal:
        permissions.grant(PermissionLevel.TERMINAL)
    controller = ToolsController(
        permissions,
        workspaces_file=tmp_path / "workspaces.json",
        audit_file=tmp_path / "audit.jsonl",
        terminal_file=tmp_path / "terminal.json",
    )
    controller.add_workspace(str(workspace), writable=write)
    if terminal:
        controller.enable_terminal(["git"])
    return controller


def make_server(controller, *, allow_write=False, auto_approve=False) -> McpServer:
    gateway = ControllerToolGateway(
        controller, allow_write=allow_write, auto_approve=auto_approve
    )
    return McpServer(gateway, server_version="test")


def handshake(server, version=PROTOCOL_VERSION) -> dict:
    """initialize + notifications/initialized, como um cliente real faz."""
    response = server.handle_message(dumps_line({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": version, "clientInfo": {"name": "pytest", "version": "0"}},
    }))
    server.handle_message(dumps_line({"jsonrpc": "2.0", "method": "notifications/initialized"}))
    return response


def call(server, name, arguments, *, request_id=2) -> dict:
    return server.handle_message(dumps_line({
        "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }))


def result_text(response) -> str:
    return response["result"]["content"][0]["text"]


# =========================================================== envelope JSON-RPC
class TestJsonRpcEnvelope:
    def test_parse_valid_request(self):
        message = parse_message('{"jsonrpc":"2.0","id":1,"method":"ping"}')
        assert message.method == "ping"
        assert message.id == 1
        assert message.is_notification is False

    def test_parse_notification_has_no_id(self):
        message = parse_message('{"jsonrpc":"2.0","method":"notifications/initialized"}')
        assert message.is_notification is True
        assert message.id is None

    def test_explicit_null_id_is_a_notification(self):
        message = parse_message('{"jsonrpc":"2.0","id":null,"method":"ping"}')
        assert message.is_notification is True

    def test_string_id_is_accepted(self):
        assert parse_message('{"jsonrpc":"2.0","id":"abc","method":"ping"}').id == "abc"

    def test_parse_error_on_invalid_json(self):
        with pytest.raises(JsonRpcError) as info:
            parse_message("{isso não é json")
        assert info.value.code == PARSE_ERROR

    def test_invalid_request_on_non_object(self):
        with pytest.raises(JsonRpcError) as info:
            parse_message("[1,2,3]")
        assert info.value.code == INVALID_REQUEST

    def test_invalid_request_on_wrong_jsonrpc_version(self):
        with pytest.raises(JsonRpcError) as info:
            parse_message('{"jsonrpc":"1.0","id":1,"method":"ping"}')
        assert info.value.code == INVALID_REQUEST

    def test_invalid_request_when_method_and_result_both_present(self):
        with pytest.raises(JsonRpcError) as info:
            parse_message('{"jsonrpc":"2.0","id":1,"method":"ping","result":{}}')
        assert "method" in info.value.message

    def test_invalid_request_without_method_or_result(self):
        with pytest.raises(JsonRpcError) as info:
            parse_message('{"jsonrpc":"2.0","id":1}')
        assert info.value.code == INVALID_REQUEST

    def test_invalid_request_on_boolean_id(self):
        with pytest.raises(JsonRpcError):
            parse_message('{"jsonrpc":"2.0","id":true,"method":"ping"}')

    def test_invalid_params_when_params_is_scalar(self):
        with pytest.raises(JsonRpcError) as info:
            parse_message('{"jsonrpc":"2.0","id":1,"method":"ping","params":42}')
        assert info.value.code == INVALID_PARAMS

    def test_parse_error_response_has_null_id(self, tmp_path):
        server = self._server(tmp_path)
        response = server.handle_message("não é json")
        assert response["error"]["code"] == PARSE_ERROR
        assert response["id"] is None

    def test_notification_produces_no_response(self, tmp_path):
        server = self._server(tmp_path)
        assert server.handle_message(
            '{"jsonrpc":"2.0","method":"notifications/initialized"}'
        ) is None

    def test_unknown_notification_is_ignored_not_errored(self, tmp_path):
        """A spec proíbe responder a notificações, mesmo desconhecidas."""
        server = self._server(tmp_path)
        assert server.handle_message(
            '{"jsonrpc":"2.0","method":"notifications/whatever"}'
        ) is None

    def test_method_not_found(self, tmp_path):
        server = self._server(tmp_path)
        handshake(server)
        response = server.handle_message('{"jsonrpc":"2.0","id":7,"method":"resources/list"}')
        assert response["error"]["code"] == METHOD_NOT_FOUND
        assert response["id"] == 7

    def test_unknown_method_is_rejected_even_before_init(self, tmp_path):
        server = self._server(tmp_path)
        response = server.handle_message('{"jsonrpc":"2.0","id":1,"method":"nope"}')
        assert response["error"]["code"] == METHOD_NOT_FOUND

    def test_ping_returns_empty_result(self, tmp_path):
        server = self._server(tmp_path)
        response = server.handle_message('{"jsonrpc":"2.0","id":5,"method":"ping"}')
        assert response == {"jsonrpc": "2.0", "id": 5, "result": {}}

    def test_response_is_compact_single_line(self):
        """A spec de stdio proíbe newlines embutidas na mensagem."""
        line = dumps_line({"jsonrpc": "2.0", "id": 1, "result": {"texto": "a\nb"}})
        assert "\n" not in line
        assert json.loads(line)["result"]["texto"] == "a\nb"

    def test_id_is_echoed_verbatim(self, tmp_path):
        server = self._server(tmp_path)
        handshake(server)
        response = server.handle_message(
            '{"jsonrpc":"2.0","id":"meu-id","method":"tools/list"}'
        )
        assert response["id"] == "meu-id"

    def _server(self, tmp_path):
        """Servidor mínimo — os testes deste bloco não tocam ferramentas."""
        permissions = PermissionManager()
        controller = ToolsController(
            permissions,
            workspaces_file=tmp_path / "w.json",
            audit_file=tmp_path / "a.jsonl",
            terminal_file=tmp_path / "t.json",
        )
        return make_server(controller)


# ============================================================== ciclo de vida
class TestLifecycle:
    def test_initialize_returns_protocol_version_and_capabilities(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        response = server.handle_message(dumps_line({
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT_PARAMS,
        }))
        result = response["result"]
        assert result["protocolVersion"] == PROTOCOL_VERSION
        assert result["capabilities"]["tools"]["listChanged"] is False
        assert result["serverInfo"]["name"] == "lumen"
        assert "instructions" in result

    def test_initialize_adopts_supported_version(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        response = server.handle_message(dumps_line({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }))
        assert response["result"]["protocolVersion"] == "2024-11-05"

    def test_initialize_falls_back_on_unsupported_version(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        response = server.handle_message(dumps_line({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "1999-01-01"},
        }))
        assert response["result"]["protocolVersion"] == PROTOCOL_VERSION

    def test_initialize_requires_protocol_version(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        response = server.handle_message(dumps_line({
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
        }))
        assert response["error"]["code"] == INVALID_PARAMS

    def test_tools_list_before_initialize_is_an_error(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        response = server.handle_message('{"jsonrpc":"2.0","id":3,"method":"tools/list"}')
        assert "error" in response
        assert "initialize" in response["error"]["message"]

    def test_initialized_flag_tracks_notification(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        assert server.initialized is False
        handshake(server)
        assert server.initialized is True
        assert server.negotiated_version == PROTOCOL_VERSION

    def test_client_info_is_recorded(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        handshake(server)
        assert server.client_info["name"] == "pytest"


# =================================================================== schema
class TestToolSchema:
    def test_basic_shape(self):
        definition = ToolDefinition(
            name="read_file", description="Lê um arquivo.",
            parameters=(ParameterDefinition("path", "string", True, "Caminho."),),
        )
        schema = tool_definition_to_mcp_schema(definition)
        assert schema["name"] == "read_file"
        assert schema["description"] == "Lê um arquivo."
        assert schema["inputSchema"]["type"] == "object"
        assert schema["inputSchema"]["properties"]["path"]["type"] == "string"
        assert schema["inputSchema"]["required"] == ["path"]

    def test_additional_properties_is_false(self):
        """O LUMEN rejeita parâmetros desconhecidos — o schema diz a verdade."""
        schema = tool_definition_to_mcp_schema(
            ToolDefinition(name="t", description="d")
        )
        assert schema["inputSchema"]["additionalProperties"] is False

    def test_optional_parameters_are_not_required(self):
        definition = ToolDefinition(
            name="t", description="d",
            parameters=(
                ParameterDefinition("a", "string", True),
                ParameterDefinition("b", "integer", False),
            ),
        )
        schema = tool_definition_to_mcp_schema(definition)
        assert schema["inputSchema"]["required"] == ["a"]
        assert "b" in schema["inputSchema"]["properties"]

    def test_no_required_key_when_all_optional(self):
        schema = tool_definition_to_mcp_schema(
            ToolDefinition(name="t", description="d",
                           parameters=(ParameterDefinition("a", "string"),))
        )
        assert "required" not in schema["inputSchema"]

    def test_every_lumen_type_maps_to_json_schema(self):
        for lumen_type, expected in (
            ("string", "string"), ("integer", "integer"), ("number", "number"),
            ("boolean", "boolean"), ("array", "array"), ("object", "object"),
        ):
            schema = parameter_to_json_schema(ParameterDefinition("p", lumen_type))
            assert schema["type"] == expected

    def test_array_declares_items(self):
        schema = parameter_to_json_schema(ParameterDefinition("p", "array"))
        assert schema["items"] == {}

    def test_unknown_type_raises_instead_of_silently_mapping(self):
        with pytest.raises(UnsupportedParameterTypeError, match="não tem equivalente"):
            parameter_to_json_schema(ParameterDefinition("p", "datetime"))

    def test_annotations_mark_read_only_tools(self):
        schema = tool_definition_to_mcp_schema(
            ToolDefinition(name="read_file", description="d", destructive=False)
        )
        assert schema["annotations"]["readOnlyHint"] is True
        assert schema["annotations"]["destructiveHint"] is False

    def test_annotations_mark_destructive_tools(self):
        schema = tool_definition_to_mcp_schema(
            ToolDefinition(name="write_file", description="d", destructive=True)
        )
        assert schema["annotations"]["readOnlyHint"] is False
        assert schema["annotations"]["destructiveHint"] is True

    def test_title_only_when_present(self):
        plain = tool_definition_to_mcp_schema(ToolDefinition(name="t", description="d"))
        assert "title" not in plain
        titled = tool_definition_to_mcp_schema(
            ToolDefinition(name="t", description="d", metadata={"title": "Título"})
        )
        assert titled["title"] == "Título"

    def test_tools_list_returns_real_definitions(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        handshake(server)
        response = server.handle_message('{"jsonrpc":"2.0","id":2,"method":"tools/list"}')
        tools = response["result"]["tools"]
        names = {t["name"] for t in tools}
        assert {"list_directory", "read_file", "file_exists", "search_files"} <= names
        for tool in tools:
            assert tool["inputSchema"]["type"] == "object"
            assert "annotations" in tool

    def test_tools_list_is_sorted_for_stable_output(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        handshake(server)
        tools = server.handle_message(
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
        )["result"]["tools"]
        assert [t["name"] for t in tools] == sorted(t["name"] for t in tools)


# ======================================================= fronteira de segurança
class TestSecurityBoundary:
    def test_default_exposes_no_destructive_tool(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        handshake(server)
        names = {
            t["name"] for t in server.handle_message(
                '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
            )["result"]["tools"]
        }
        assert names.isdisjoint(
            {"write_file", "create_file", "create_directory", "delete_file", "edit_file"}
        )

    def test_write_mode_exposes_destructive_tools(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace), allow_write=True)
        handshake(server)
        names = {
            t["name"] for t in server.handle_message(
                '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
            )["result"]["tools"]
        }
        assert {"write_file", "create_file", "create_directory"} <= names

    def test_calling_unexposed_tool_is_rejected_and_writes_nothing(
        self, tmp_path, workspace
    ):
        server = make_server(make_controller(tmp_path, workspace))  # read-only
        handshake(server)

        response = call(server, "write_file", {"path": "novo.txt", "content": "x"})

        assert response["error"]["code"] == METHOD_NOT_FOUND
        assert not (workspace / "novo.txt").exists()

    def test_gateway_refuses_unexposed_tool_even_if_called_directly(
        self, tmp_path, workspace
    ):
        """Defesa em profundidade: o `tools/list` não é a única barreira."""
        gateway = ControllerToolGateway(
            make_controller(tmp_path, workspace), allow_write=False
        )
        with pytest.raises(McpGatewayError, match="não está exposta"):
            gateway.call("delete_file", {"path": "existente.txt"})
        assert (workspace / "existente.txt").exists()

    def test_auto_approve_requires_allow_write(self, tmp_path, workspace):
        with pytest.raises(McpGatewayError, match="allow_write"):
            ControllerToolGateway(
                make_controller(tmp_path, workspace), allow_write=False, auto_approve=True
            )

    def test_write_without_auto_approve_waits_for_the_checkpoint(
        self, tmp_path, workspace
    ):
        """O caminho crítico: nada é escrito sem o usuário decidir."""
        controller = make_controller(tmp_path, workspace)
        server = make_server(controller, allow_write=True)
        handshake(server)

        response = call(server, "write_file", {"path": "novo.txt", "content": "x"})
        result = response["result"]

        assert result["isError"] is False, "aguardar aprovação não é erro de execução"
        assert "aguardando aprovação" in result_text(response)
        assert result["structuredContent"]["awaiting_approval"] is True
        assert result["structuredContent"]["checkpoint_id"]
        assert not (workspace / "novo.txt").exists(), "nada pode ter sido escrito"
        assert controller.pending_approval() is not None

    def test_pending_checkpoint_appears_in_server_history(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace), allow_write=True)
        handshake(server)
        call(server, "write_file", {"path": "novo.txt", "content": "x"})
        assert len(server.checkpoints_seen) == 1
        assert server.checkpoints_seen[0]["tool"] == "write_file"

    def test_auto_approve_writes_and_reports_success(self, tmp_path, workspace):
        server = make_server(
            make_controller(tmp_path, workspace), allow_write=True, auto_approve=True
        )
        handshake(server)

        response = call(server, "write_file", {"path": "novo.txt", "content": "olá"})

        assert response["result"]["isError"] is False
        assert (workspace / "novo.txt").read_text(encoding="utf-8") == "olá"
        assert response["result"]["structuredContent"]["auto_approvals"] == 1

    def test_read_tool_never_asks_for_a_checkpoint(self, tmp_path, workspace):
        controller = make_controller(tmp_path, workspace)
        server = make_server(controller)
        handshake(server)

        response = call(server, "read_file", {"path": "existente.txt"})

        assert response["result"]["isError"] is False
        assert "conteúdo lido" in result_text(response)
        assert controller.pending_approval() is None

    def test_read_result_is_decoded_json_not_escaped_string(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        handshake(server)
        response = call(server, "read_file", {"path": "existente.txt"})
        # Se o JSON interno não fosse decodificado, o texto viria com \" escapes
        assert '\\"content\\"' not in result_text(response)

    def test_unknown_argument_becomes_legible_error_not_crash(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        handshake(server)

        response = call(server, "read_file", {"caminho_errado": "x"})

        assert response["result"]["isError"] is True
        assert "caminho_errado" in result_text(response)

    def test_missing_required_argument_is_reported(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        handshake(server)

        response = call(server, "read_file", {})

        assert response["result"]["isError"] is True
        assert "path" in result_text(response)

    def test_path_outside_workspace_is_blocked(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace))
        handshake(server)

        response = call(server, "read_file", {"path": "../../etc/passwd"})

        assert response["result"]["isError"] is True

    def test_read_without_permission_fails_closed(self, tmp_path, workspace):
        """Sem READ concedido, nem listar funciona — e o erro é claro."""
        permissions = PermissionManager()  # só CHAT
        controller = ToolsController(
            permissions,
            workspaces_file=tmp_path / "w.json",
            audit_file=tmp_path / "a.jsonl",
            terminal_file=tmp_path / "t.json",
        )
        controller.add_workspace(str(workspace), writable=True)
        server = make_server(controller)
        handshake(server)

        response = call(server, "list_directory", {"path": "."})

        assert response["result"]["isError"] is True

    def test_terminal_not_exposed_without_enablement(self, tmp_path, workspace):
        server = make_server(make_controller(tmp_path, workspace), allow_write=True)
        handshake(server)
        names = {
            t["name"] for t in server.handle_message(
                '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
            )["result"]["tools"]
        }
        assert "run_command" not in names

    def test_terminal_exposed_when_enabled(self, tmp_path, workspace):
        controller = make_controller(tmp_path, workspace, terminal=True)
        server = make_server(controller, allow_write=True)
        handshake(server)
        names = {
            t["name"] for t in server.handle_message(
                '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
            )["result"]["tools"]
        }
        assert "run_command" in names

    def test_enabling_write_does_not_grant_write_permission(self, tmp_path, workspace):
        """Expor a tool não é conceder permissão: são coisas separadas."""
        controller = make_controller(tmp_path, workspace, write=False)
        server = make_server(controller, allow_write=True, auto_approve=True)
        handshake(server)

        response = call(server, "write_file", {"path": "novo.txt", "content": "x"})

        assert not (workspace / "novo.txt").exists()
        assert response["result"]["isError"] is True


# ============================================================== transporte stdio
class TestStdioTransport:
    def _server(self, tmp_path, workspace, **kwargs):
        return make_server(make_controller(tmp_path, workspace), **kwargs)

    def test_full_session_round_trip(self, tmp_path, workspace):
        stdin = io.StringIO("\n".join([
            dumps_line({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": INIT_PARAMS}),
            dumps_line({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            dumps_line({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            dumps_line({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "read_file",
                                   "arguments": {"path": "existente.txt"}}}),
        ]) + "\n")
        stdout, stderr = io.StringIO(), io.StringIO()

        stats = serve_stdio(self._server(tmp_path, workspace), stdin, stdout, stderr=stderr)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        assert stats.messages_read == 4
        assert stats.responses_written == 3  # a notificação não gera resposta
        assert lines[0]["id"] == 1
        assert lines[1]["id"] == 2
        assert "conteúdo lido" in lines[2]["result"]["content"][0]["text"]
        assert "encerrado" in stderr.getvalue()

    def test_every_stdout_line_is_valid_json(self, tmp_path, workspace):
        stdin = io.StringIO(
            'isto não é json\n'
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
            '{"jsonrpc":"2.0","id":2,"method":"metodo/inexistente"}\n'
        )
        stdout = io.StringIO()
        serve_stdio(self._server(tmp_path, workspace), stdin, stdout)
        for line in stdout.getvalue().splitlines():
            assert json.loads(line)["jsonrpc"] == "2.0"

    def test_eof_terminates_the_loop(self, tmp_path, workspace):
        stdout = io.StringIO()
        stats = serve_stdio(self._server(tmp_path, workspace), io.StringIO(""), stdout)
        assert stats.messages_read == 0
        assert stdout.getvalue() == ""

    def test_oversized_line_is_rejected_without_crashing(self, tmp_path, workspace):
        huge = '{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"' + "y" * 200 + '"}}'
        stdout = io.StringIO()
        stats = serve_stdio(
            self._server(tmp_path, workspace), io.StringIO(huge + "\n"), stdout,
            max_line_bytes=64,
        )
        assert stats.parse_errors == 1
        assert json.loads(stdout.getvalue().splitlines()[0])["id"] is None

    def test_no_extra_output_in_stdout(self, tmp_path, workspace):
        """Só mensagem MCP pode sair no stdout (regra da spec)."""
        stdin = io.StringIO(dumps_line({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n")
        stdout = io.StringIO()
        serve_stdio(self._server(tmp_path, workspace), stdin, stdout)
        payload = json.loads(stdout.getvalue().strip())
        assert set(payload) == {"jsonrpc", "id", "result"}

    def test_stats_are_accumulated_into_provided_object(self, tmp_path, workspace):
        from app.mcp_server import StdioStats

        stats = StdioStats()
        serve_stdio(
            self._server(tmp_path, workspace),
            io.StringIO(dumps_line({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"),
            io.StringIO(),
            stats=stats,
        )
        assert stats.messages_read == 1 and stats.responses_written == 1

    def test_write_session_over_stdio_with_auto_approve(self, tmp_path, workspace):
        stdin = io.StringIO("\n".join([
            dumps_line({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": INIT_PARAMS}),
            dumps_line({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            dumps_line({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "write_file",
                                   "arguments": {"path": "sub/novo.txt",
                                                 "content": "via stdio"}}}),
        ]) + "\n")
        stdout = io.StringIO()

        server = self._server(tmp_path, workspace, allow_write=True, auto_approve=True)
        serve_stdio(server, stdin, stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        assert lines[1]["result"]["isError"] is False
        assert (workspace / "sub" / "novo.txt").read_text(encoding="utf-8") == "via stdio"

    def test_internal_error_is_reported_as_jsonrpc_error(self, tmp_path, workspace):
        server = self._server(tmp_path, workspace)
        handshake(server)

        def explode(*args, **kwargs):
            raise RuntimeError("boom interno")

        server.gateway.call = explode  # type: ignore[method-assign]
        response = call(server, "read_file", {"path": "existente.txt"})
        assert response["error"]["code"] == INTERNAL_ERROR
        assert "boom interno" in response["error"]["message"]


# =========================================== servidor real como subprocesso
class TestRealSubprocess:
    """Sobe o servidor de verdade: ``python -m app.mcp_server``.

    É o único teste que prova que o **entry point** funciona como o Claude
    Desktop/Cline o lançam (processo separado, stdio, sem importar nada).
    Os testes unitários acima não pegariam um construtor quebrado no
    ``__main__`` — este pega.
    """

    def _run(self, lines, *, workspace, data_dir, args=(), env=None):
        import subprocess
        import sys
        import os

        payload = "\n".join(dumps_line(line) for line in lines) + "\n"
        proc = subprocess.run(
            [sys.executable, "-m", "app.mcp_server",
             "--workspace", str(workspace), "--data-dir", str(data_dir), *args],
            # MCP stdio é UTF-8 por contrato. `text=True` sozinho usa o locale
            # do PAI (cp1252 no Windows), corrompendo input e stdout.
            input=payload, capture_output=True, encoding="utf-8", errors="strict",
            timeout=90,
            env={**os.environ, **(env or {})},
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        responses = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
        return responses, proc

    def test_initialize_and_tools_list_over_a_real_process(self, tmp_path, workspace):
        responses, proc = self._run(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": PROTOCOL_VERSION,
                            "clientInfo": {"name": "subprocess", "version": "1"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            ],
            workspace=workspace, data_dir=tmp_path / "data", args=("--allow-read",),
        )
        assert proc.returncode == 0, proc.stderr
        assert responses[0]["result"]["protocolVersion"] == PROTOCOL_VERSION
        assert [r["id"] for r in responses] == [1, 2], "notificação não gera resposta"
        names = {t["name"] for t in responses[1]["result"]["tools"]}
        assert "read_file" in names

    def test_every_stdout_line_is_an_mcp_message(self, tmp_path, workspace):
        """A spec proíbe qualquer byte que não seja mensagem MCP no stdout."""
        responses, proc = self._run(
            [{"jsonrpc": "2.0", "id": 1, "method": "ping"}],
            workspace=workspace, data_dir=tmp_path / "data", args=("--allow-read",),
        )
        for response in responses:
            assert response["jsonrpc"] == "2.0"
            assert "result" in response or "error" in response
        # Logs existem, mas no stderr (o warning de startup vai para lá).
        assert "[lumen-mcp]" in proc.stderr

    def test_read_over_subprocess(self, tmp_path, workspace):
        responses, proc = self._run(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": PROTOCOL_VERSION}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "read_file",
                            "arguments": {"path": "existente.txt"}}},
            ],
            workspace=workspace, data_dir=tmp_path / "data", args=("--allow-read",),
        )
        assert proc.returncode == 0, proc.stderr
        text = responses[1]["result"]["content"][0]["text"]
        assert "conteúdo lido" in text

    def test_cp1252_parent_locale_keeps_mcp_utf8(self, tmp_path, workspace, monkeypatch):
        """O locale do processo PAI não pode codificar/decodificar o MCP."""
        import subprocess

        # Simula a escolha de codec do Windows quando `text=True` omite
        # encoding, mesmo que o runner Linux tenha sys.flags.utf8_mode=1.
        monkeypatch.setattr(subprocess, "_text_encoding", lambda: "cp1252")
        responses, proc = self._run(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": PROTOCOL_VERSION}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "create_file",
                            "arguments": {"path": "ação.txt", "content": "olá, mundo!"}}},
            ],
            workspace=workspace, data_dir=tmp_path / "data",
            args=("--allow-read", "--allow-write", "--auto-approve"),
            env={"PYTHONIOENCODING": "cp1252"},
        )
        assert proc.returncode == 0, proc.stderr
        assert responses[1]["result"]["isError"] is False
        assert (workspace / "ação.txt").read_text(encoding="utf-8") == "olá, mundo!"

    def test_cp1252_console_still_emits_utf8_checkpoint(self, tmp_path, workspace):
        """Regressão Windows: ⏸ não pode derrubar o subprocesso MCP."""
        responses, proc = self._run(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": PROTOCOL_VERSION}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "create_file",
                            "arguments": {"path": "teste.txt", "content": "olá"}}},
            ],
            workspace=workspace, data_dir=tmp_path / "data",
            args=("--allow-read", "--allow-write"),
            env={"PYTHONIOENCODING": "cp1252"},
        )
        assert proc.returncode == 0, proc.stderr
        assert "⏸" in responses[1]["result"]["content"][0]["text"]
        assert "não" in proc.stderr, "stderr também deve ser UTF-8"
        assert not (workspace / "teste.txt").exists()

    def test_cp1252_console_decodes_utf8_input(self, tmp_path, workspace):
        """Cliente MCP sempre envia UTF-8; stdin não pode corromper acentos."""
        responses, proc = self._run(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": PROTOCOL_VERSION}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "create_file",
                            "arguments": {"path": "ação.txt", "content": "olá, mundo!"}}},
            ],
            workspace=workspace, data_dir=tmp_path / "data",
            args=("--allow-read", "--allow-write", "--auto-approve"),
            env={"PYTHONIOENCODING": "cp1252"},
        )
        assert proc.returncode == 0, proc.stderr
        assert responses[1]["result"]["isError"] is False
        assert (workspace / "ação.txt").read_text(encoding="utf-8") == "olá, mundo!"

    def test_write_requires_write_mode_over_subprocess(self, tmp_path, workspace):
        responses, proc = self._run(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": PROTOCOL_VERSION}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "write_file",
                            "arguments": {"path": "novo.txt", "content": "x"}}},
            ],
            workspace=workspace, data_dir=tmp_path / "data", args=("--allow-read",),
        )
        assert proc.returncode == 0, proc.stderr
        assert responses[1]["error"]["code"] == METHOD_NOT_FOUND
        assert not (workspace / "novo.txt").exists()

    def test_write_with_auto_approve_creates_nested_file(self, tmp_path, workspace):
        responses, proc = self._run(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": PROTOCOL_VERSION}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "create_directory",
                            "arguments": {"path": "Source/Jogo"}}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "create_file",
                            "arguments": {"path": "Source/Jogo/Ator.h",
                                          "content": "#pragma once\n"}}},
            ],
            workspace=workspace, data_dir=tmp_path / "data",
            args=("--allow-read", "--allow-write", "--auto-approve"),
        )
        assert proc.returncode == 0, proc.stderr
        assert responses[1]["result"]["isError"] is False
        assert responses[2]["result"]["isError"] is False
        assert (workspace / "Source" / "Jogo" / "Ator.h").is_file()

    def test_write_without_auto_approve_writes_nothing_over_subprocess(
        self, tmp_path, workspace
    ):
        responses, proc = self._run(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": PROTOCOL_VERSION}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "write_file",
                            "arguments": {"path": "novo.txt", "content": "x"}}},
            ],
            workspace=workspace, data_dir=tmp_path / "data",
            args=("--allow-read", "--allow-write"),
        )
        assert proc.returncode == 0, proc.stderr
        result = responses[1]["result"]
        assert result["isError"] is False
        assert "aguardando aprovação" in result["content"][0]["text"]
        assert not (workspace / "novo.txt").exists()

    def test_auto_approve_without_allow_write_fails_loudly(self, tmp_path, workspace):
        responses, proc = self._run(
            [{"jsonrpc": "2.0", "id": 1, "method": "ping"}],
            workspace=workspace, data_dir=tmp_path / "data",
            args=("--allow-read", "--auto-approve"),
        )
        assert proc.returncode == 2
        assert "allow_write" in proc.stderr


# Revisão PR #33: estes cenários só aparecem no entry point real, não num
# McpServer montado manualmente em teste.
class TestFinalReviewEntrypoint:
    def test_write_env_grants_permission_and_writable_workspace(self, tmp_path, workspace):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": PROTOCOL_VERSION}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "create_file", "arguments":
                        {"path": "revisao.txt", "content": "ok"}}},
        ]
        responses, proc = TestRealSubprocess()._run(
            lines, workspace=workspace, data_dir=tmp_path / "data",
            args=("--allow-read", "--auto-approve"),
            env={"LUMEN_MCP_ALLOW_WRITE": "true"},
        )
        assert proc.returncode == 0, proc.stderr
        assert responses[1]["result"]["isError"] is False
        assert (workspace / "revisao.txt").read_text(encoding="utf-8") == "ok"

    def test_web_search_requires_opt_in_and_key(self, tmp_path, workspace):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": PROTOCOL_VERSION}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        env = {"TAVILY_API_KEY": "tvly-FAKE-REVIEW-KEY"}
        no_opt, _ = TestRealSubprocess()._run(
            lines, workspace=workspace, data_dir=tmp_path / "data1",
            args=("--allow-read",), env=env,
        )
        yes_opt, proc = TestRealSubprocess()._run(
            lines, workspace=workspace, data_dir=tmp_path / "data2",
            args=("--allow-read", "--enable-web-search"), env=env,
        )
        assert proc.returncode == 0, proc.stderr
        names = lambda responses: {t["name"] for t in responses[1]["result"]["tools"]}
        assert "web_search" not in names(no_opt)
        assert "web_search" in names(yes_opt)
        assert env["TAVILY_API_KEY"] not in proc.stderr + proc.stdout

    def test_unreal_tools_require_opt_in_and_separate_read_from_write(
        self, tmp_path, workspace
    ):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": PROTOCOL_VERSION}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        no_opt, _ = TestRealSubprocess()._run(
            lines, workspace=workspace, data_dir=tmp_path / "data0",
            args=("--allow-read",),
        )
        read_only, _ = TestRealSubprocess()._run(
            lines, workspace=workspace, data_dir=tmp_path / "data1",
            args=("--allow-read", "--enable-unreal-bridge"),
        )
        write_enabled, proc = TestRealSubprocess()._run(
            lines, workspace=workspace, data_dir=tmp_path / "data2",
            args=("--allow-read", "--allow-write", "--enable-unreal-bridge"),
        )
        assert proc.returncode == 0, proc.stderr
        names = lambda responses: {t["name"] for t in responses[1]["result"]["tools"]}
        mutating = {
            "unreal_create_blueprint_class", "unreal_add_component",
            "unreal_set_property", "unreal_call_function",
        }
        read_only_names = {
            "unreal_get_info", "unreal_search_assets", "unreal_describe_object",
        }
        assert not any(n.startswith("unreal_") for n in names(no_opt))
        assert read_only_names <= names(read_only)
        assert not (mutating & names(read_only))
        assert mutating <= names(write_enabled)
        assert read_only_names <= names(write_enabled)
