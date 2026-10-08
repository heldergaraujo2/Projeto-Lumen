"""Testes da ponte com o Unreal Editor (Fase 4).

Nenhum teste toca a rede nem precisa de um Unreal instalado: o transporte
HTTP é injetado e devolve as respostas **copiadas da referência oficial**
da Remote Control API (as mesmas formas dos exemplos da Epic).

A distinção que a suíte mantém explícita:

- o que é RC API pura é testado contra a forma documentada — se o corpo da
  requisição mudar, o teste quebra;
- o que executa Python no editor é testado quanto ao **contrato** (script
  gerado, erro propagado, recusa quando o transporte não suporta) e marca
  `needs_manual_validation` — os testes não afirmam que o Unreal aceita.
"""
from __future__ import annotations

import json

import pytest

from app.unreal_bridge import (
    NEEDS_MANUAL_VALIDATION,
    UNREAL_READ_ONLY_TOOLS,
    UNREAL_TOOLS,
    VALIDATED_AGAINST_DOC,
    RemoteControlClient,
    UnrealBridgeConfig,
    UnrealBridgeError,
    UnrealUnavailableError,
    build_add_component_script,
    build_blueprint_creation_script,
    build_compile_script,
    build_save_script,
    build_unreal_registry,
    parse_execution_result,
    unreal_definitions,
)
from app.unreal_bridge.python_script import PythonScriptError

INFO_BODY = {
    "HttpRoutes": [
        {"Path": "/remote/info", "Verb": "Get", "Description": "Get information."},
        {"Path": "/remote/object/call", "Verb": "Put", "Description": "Call function."},
        {"Path": "/remote/object/property", "Verb": "Put", "Description": "Property."},
        {"Path": "/remote/object/describe", "Verb": "Put", "Description": "Describe."},
        {"Path": "/remote/search/assets", "Verb": "Put", "Description": "Search."},
        {"Path": "/remote/batch", "Verb": "Put", "Description": "Batch."},
    ]
}

DESCRIBE_BODY = {
    "Name": "CubeMesh_5",
    "Class": "/Script/Engine.StaticMeshActor",
    "Properties": [
        {"Name": "StaticMeshComponent", "Type": "UStaticMeshComponent*",
         "ContainerType": "", "KeyType": "", "Metadata": {}},
        {"Name": "bHidden", "Type": "uint8", "ContainerType": "", "KeyType": "", "Metadata": {}},
    ],
    "Functions": [{"Name": "SetActorLocation"}, {"Name": "K2_DestroyActor"}],
}

SEARCH_BODY = {
    "Assets": [
        {"Name": "CubeMaterial", "Class": "Material",
         "Path": "/Game/Geometry/Meshes/CubeMaterial.CubeMaterial"},
        {"Name": "1M_Cube", "Class": "StaticMesh",
         "Path": "/Game/Geometry/Meshes/1M_Cube.1M_Cube"},
    ]
}

PYTHON_OK_BODY = {
    "CommandResult": "LUMEN: blueprint criado em /Game/Blueprints/BP_Teste",
    "LogOutput": [
        {"Type": "Info", "Output": "LUMEN: blueprint criado em /Game/Blueprints/BP_Teste"},
    ],
}

PYTHON_ERROR_BODY = {
    "CommandResult": "",
    "LogOutput": [
        {"Type": "Error", "Output": "LUMEN: create_asset devolveu None"},
    ],
}


class FakeTransport:
    """Transporte HTTP de teste: responde por rota e registra as chamadas."""

    def __init__(self, responses=None, *, status=200):
        self.calls: list[dict] = []
        self._responses = responses or {}
        self._status = status

    def __call__(self, method, url, body, headers, timeout):
        parsed = json.loads(body) if body else None
        self.calls.append({
            "method": method, "url": url, "body": parsed,
            "headers": dict(headers), "timeout": timeout,
        })
        path = "/" + url.split("/", 3)[3] if url.count("/") >= 3 else url
        for suffix, response in self._responses.items():
            if url.endswith(suffix):
                if isinstance(response, tuple):
                    return response
                return 200, json.dumps(response).encode("utf-8")
        return 404, b'{"errorMessage": "rota nao encontrada"}'

    @property
    def last(self) -> dict:
        return self.calls[-1]

    def body_for(self, suffix: str):
        for call in reversed(self.calls):
            if call["url"].endswith(suffix):
                return call["body"]
        return None


def client_with(responses=None, **kwargs) -> tuple[RemoteControlClient, FakeTransport]:
    transport = FakeTransport(responses)
    client = RemoteControlClient(
        UnrealBridgeConfig(**kwargs), transport=transport, verify_on_start=False
    )
    return client, transport


def tools_for(client) -> dict:
    return {tool.name: tool for tool in build_unreal_registry(client)}


# ================================================================= configuração
class TestConfig:
    def test_defaults_match_the_epic_convention(self):
        config = UnrealBridgeConfig()
        assert config.port == 30010
        assert config.host == "127.0.0.1"
        assert config.base_url == "http://127.0.0.1:30010"

    def test_reads_environment(self):
        config = UnrealBridgeConfig.from_env({
            "LUMEN_UNREAL_RC_PORT": "30100",
            "LUMEN_UNREAL_RC_HOST": "10.0.0.5",
            "LUMEN_UNREAL_TIMEOUT": "45",
            "LUMEN_UNREAL_TRANSPORT": "PYTHON",
        })
        assert (config.port, config.host, config.timeout) == (30100, "10.0.0.5", 45.0)
        assert config.transport == "python"

    def test_empty_env_falls_back_to_defaults(self):
        config = UnrealBridgeConfig.from_env({"LUMEN_UNREAL_RC_PORT": "   "})
        assert config.port == 30010

    def test_non_numeric_port_is_a_clear_error(self):
        with pytest.raises(UnrealBridgeError, match="numérico"):
            UnrealBridgeConfig.from_env({"LUMEN_UNREAL_RC_PORT": "abc"})

    def test_invalid_transport_is_rejected(self):
        with pytest.raises(UnrealBridgeError, match="transporte inválido"):
            UnrealBridgeConfig(transport="websocket")

    def test_absurd_timeout_is_rejected(self):
        with pytest.raises(UnrealBridgeError, match="timeout"):
            UnrealBridgeConfig(timeout=99999)

    def test_python_flags(self):
        assert UnrealBridgeConfig(transport="python").python_required is True
        assert UnrealBridgeConfig(transport="auto").python_enabled is True
        assert UnrealBridgeConfig(transport="rc").python_enabled is False


# ================================================================ cliente HTTP
class TestClient:
    def test_info_uses_get_on_remote_info(self):
        client, transport = client_with({"/remote/info": INFO_BODY})
        payload = client.info()
        assert transport.last["method"] == "GET"
        assert transport.last["url"] == "http://127.0.0.1:30010/remote/info"
        assert "HttpRoutes" in payload

    def test_routes_are_extracted(self):
        client, _ = client_with({"/remote/info": INFO_BODY})
        assert "/remote/object/call" in client.routes()

    def test_is_available_is_a_probe_that_never_raises(self):
        transport = FakeTransport({})  # tudo 404
        client = RemoteControlClient(
            UnrealBridgeConfig(), transport=transport, verify_on_start=False
        )
        assert client.is_available() is False

    def test_connection_refused_becomes_actionable_error(self):
        from urllib.error import URLError

        def dead(*args, **kwargs):
            raise URLError("Connection refused")

        client = RemoteControlClient(UnrealBridgeConfig(), transport=dead)
        with pytest.raises(UnrealUnavailableError, match="Unreal"):
            client.info()

    def test_error_message_mentions_the_plugin(self):
        from urllib.error import URLError

        def dead(*args, **kwargs):
            raise URLError("Connection refused")

        client = RemoteControlClient(UnrealBridgeConfig(), transport=dead)
        with pytest.raises(UnrealUnavailableError, match="Remote Control API"):
            client.info()

    def test_http_error_body_is_surfaced(self):
        transport = FakeTransport({"/remote/object/call": (500, b'{"errorMessage": "boom"}')})
        client = RemoteControlClient(
            UnrealBridgeConfig(), transport=transport, verify_on_start=False
        )
        with pytest.raises(UnrealBridgeError, match="boom"):
            client.call_function("/Game/A.A:A", "F")

    def test_empty_body_is_success_not_a_crash(self):
        """WRITE_ACCESS responde 200 com corpo vazio — isso é sucesso."""
        transport = FakeTransport({"/remote/object/property": (200, b"")})
        client = RemoteControlClient(
            UnrealBridgeConfig(), transport=transport, verify_on_start=False
        )
        assert client.set_property("/Game/A.A:A", "P", 1) is None

    def test_oversized_response_is_refused(self):
        from app.unreal_bridge.client import MAX_RESPONSE_BYTES

        transport = FakeTransport({"/remote/info": (200, b"x" * (MAX_RESPONSE_BYTES + 10))})
        client = RemoteControlClient(
            UnrealBridgeConfig(), transport=transport, verify_on_start=False
        )
        with pytest.raises(UnrealBridgeError, match="excedeu"):
            client.info()

    def test_non_json_response_is_refused(self):
        transport = FakeTransport({"/remote/info": (200, b"<html>nao</html>")})
        client = RemoteControlClient(
            UnrealBridgeConfig(), transport=transport, verify_on_start=False
        )
        with pytest.raises(UnrealBridgeError, match="JSON"):
            client.info()

    def test_verify_on_start_pings_before_first_operation(self):
        transport = FakeTransport({
            "/remote/info": INFO_BODY,
            "/remote/object/call": {"ReturnValue": True},
        })
        client = RemoteControlClient(UnrealBridgeConfig(), transport=transport)
        client.call_function("/Game/A.A:A", "F")
        assert transport.calls[0]["url"].endswith("/remote/info")


# ================================================ corpo exato da doc oficial
class TestOfficialWireFormat:
    """Se a forma do corpo mudar, estes testes quebram — é o objetivo."""

    def test_call_function_body(self):
        client, transport = client_with({"/remote/object/call": {"ReturnValue": True}})
        client.call_function(
            "/Game/Map.Map:PersistentLevel.CubeMesh_5",
            "SetActorLocation",
            {"NewLocation": {"X": 100, "Y": 0, "Z": 30}, "bSweep": True},
        )
        body = transport.body_for("/remote/object/call")
        assert transport.last["method"] == "PUT"
        assert body == {
            "objectPath": "/Game/Map.Map:PersistentLevel.CubeMesh_5",
            "functionName": "SetActorLocation",
            "parameters": {"NewLocation": {"X": 100, "Y": 0, "Z": 30}, "bSweep": True},
            "generateTransaction": True,
        }

    def test_call_function_can_disable_transaction(self):
        client, transport = client_with({"/remote/object/call": {}})
        client.call_function("/Game/A.A:A", "F", generate_transaction=False)
        assert transport.body_for("/remote/object/call")["generateTransaction"] is False

    def test_update_property_body_matches_the_documented_example(self):
        client, transport = client_with({"/remote/object/property": (200, b"")})
        client.set_property(
            "/Game/Map.Map:PersistentLevel.CubeMesh_5.StaticMeshComponent0",
            "StreamingDistanceMultiplier", 2,
        )
        assert transport.body_for("/remote/object/property") == {
            "objectPath": (
                "/Game/Map.Map:PersistentLevel.CubeMesh_5.StaticMeshComponent0"
            ),
            "propertyName": "StreamingDistanceMultiplier",
            "access": "WRITE_TRANSACTION_ACCESS",
            "propertyValue": {"StreamingDistanceMultiplier": 2},
        }

    def test_read_property_body(self):
        client, transport = client_with({
            "/remote/object/property": {"StreamingDistanceMultiplier": 1}
        })
        client.get_property("/Game/A.A:A", "StreamingDistanceMultiplier")
        assert transport.body_for("/remote/object/property") == {
            "objectPath": "/Game/A.A:A",
            "access": "READ_ACCESS",
            "propertyName": "StreamingDistanceMultiplier",
        }

    def test_read_all_properties_omits_property_name(self):
        client, transport = client_with({"/remote/object/property": {"bHidden": False}})
        client.get_property("/Game/A.A:A")
        body = transport.body_for("/remote/object/property")
        assert "propertyName" not in body
        assert body["access"] == "READ_ACCESS"

    def test_search_assets_body(self):
        client, transport = client_with({"/remote/search/assets": SEARCH_BODY})
        assets = client.search_assets("Cube", class_names=["StaticMesh"])
        assert transport.body_for("/remote/search/assets") == {
            "Query": "Cube",
            "Filter": {
                "PackageNames": [],
                "ClassNames": ["StaticMesh"],
                "PackagePaths": [],
                "RecursiveClassesExclusionSet": [],
                "RecursivePaths": True,
                "RecursiveClasses": False,
            },
        }
        assert assets[0]["Name"] == "CubeMaterial"

    def test_batch_body_and_response(self):
        client, transport = client_with({
            "/remote/batch": {"Responses": [
                {"RequestId": 1, "ResponseCode": 200,
                 "ResponseBody": {"StreamingDistanceMultiplier": 2}},
            ]}
        })
        responses = client.batch([
            {"URL": "/remote/object/property", "Verb": "PUT",
             "Body": {"objectPath": "/Game/A.A:A"}},
        ])
        assert transport.body_for("/remote/batch")["Requests"] == [{
            "RequestId": 1, "URL": "/remote/object/property", "Verb": "PUT",
            "Body": {"objectPath": "/Game/A.A:A"},
        }]
        assert responses[0]["ResponseCode"] == 200

    def test_batch_rejects_empty_and_oversized(self):
        from app.unreal_bridge.client import MAX_BATCH_REQUESTS

        client, _ = client_with({})
        with pytest.raises(UnrealBridgeError, match="ao menos uma"):
            client.batch([])
        with pytest.raises(UnrealBridgeError, match="máximo"):
            client.batch(
                [{"URL": "/remote/info", "Verb": "GET"}] * (MAX_BATCH_REQUESTS + 1)
            )

    def test_describe_body(self):
        client, transport = client_with({"/remote/object/describe": DESCRIBE_BODY})
        client.describe("/Game/A.A:A")
        assert transport.body_for("/remote/object/describe") == {"objectPath": "/Game/A.A:A"}

    def test_content_type_is_json_when_there_is_a_body(self):
        client, transport = client_with({"/remote/object/describe": DESCRIBE_BODY})
        client.describe("/Game/A.A:A")
        assert transport.last["headers"]["Content-Type"] == "application/json"


# ================================================================== ferramentas
class TestTools:
    def test_all_seven_tools_exist(self):
        assert len(UNREAL_TOOLS) == 7
        assert "unreal_create_blueprint_class" in UNREAL_TOOLS
        assert "unreal_add_component" in UNREAL_TOOLS
        assert "unreal_set_property" in UNREAL_TOOLS
        assert "unreal_call_function" in UNREAL_TOOLS

    def test_definitions_declare_validation_status(self):
        client, _ = client_with({})
        for definition in unreal_definitions(client):
            assert definition.metadata["validation"] in {
                VALIDATED_AGAINST_DOC, NEEDS_MANUAL_VALIDATION
            }
            assert definition.destructive is (
                definition.name not in UNREAL_READ_ONLY_TOOLS
            )
            assert definition.description.strip()

    def test_pure_rc_tools_are_marked_as_doc_validated(self):
        client, _ = client_with({})
        by_name = {d.name: d for d in unreal_definitions(client)}
        for name in ("unreal_get_info", "unreal_set_property", "unreal_call_function",
                     "unreal_describe_object", "unreal_search_assets"):
            assert by_name[name].metadata["validation"] == VALIDATED_AGAINST_DOC

    def test_python_dependent_tools_are_marked_as_unvalidated(self):
        client, _ = client_with({})
        by_name = {d.name: d for d in unreal_definitions(client)}
        for name in ("unreal_create_blueprint_class", "unreal_add_component"):
            assert by_name[name].metadata["validation"] == NEEDS_MANUAL_VALIDATION

    def test_read_only_tools_require_read_and_mutations_require_write(self):
        from app.security.permissions import PermissionLevel

        client, _ = client_with({})
        for tool in build_unreal_registry(client):
            expected = (
                PermissionLevel.READ if tool.name in UNREAL_READ_ONLY_TOOLS
                else PermissionLevel.WRITE
            )
            assert tool.required_permission is expected

    # ------------------------------------------------------------- get_info
    def test_get_info_reports_connection_and_routes(self):
        client, _ = client_with({"/remote/info": INFO_BODY})
        result = tools_for(client)["unreal_get_info"].run()
        assert result.ok is True
        assert result.data["connected"] is True
        assert result.data["route_count"] == 6
        assert "/remote/object/call" in result.data["routes"]

    def test_get_info_fails_cleanly_when_editor_is_closed(self):
        from urllib.error import URLError

        def dead(*args, **kwargs):
            raise URLError("Connection refused")

        client = RemoteControlClient(UnrealBridgeConfig(), transport=dead)
        result = tools_for(client)["unreal_get_info"].run()
        assert result.ok is False
        assert result.data["connected"] is False
        assert "TESTE_LOCAL.md" in result.error

    # ----------------------------------------------------- describe / search
    def test_describe_lists_real_names(self):
        client, _ = client_with({"/remote/object/describe": DESCRIBE_BODY})
        result = tools_for(client)["unreal_describe_object"].run(
            object_path="/Game/A.A:A"
        )
        assert result.ok is True
        assert result.data["properties"] == ["StaticMeshComponent", "bHidden"]
        assert "SetActorLocation" in result.data["functions"]

    def test_describe_requires_object_path(self):
        client, _ = client_with({})
        result = tools_for(client)["unreal_describe_object"].run()
        assert result.ok is False
        assert "object_path" in result.error

    def test_search_assets_returns_paths(self):
        client, _ = client_with({"/remote/search/assets": SEARCH_BODY})
        result = tools_for(client)["unreal_search_assets"].run(query="Cube")
        assert result.ok is True
        assert result.data["count"] == 2
        assert result.data["assets"][0]["path"].startswith("/Game/")

    # ------------------------------------------------------- set_property
    def test_set_property_coerces_string_numbers(self):
        """O MCP entrega texto; o editor espera número. Sem isso, falha."""
        client, transport = client_with({"/remote/object/property": (200, b"")})
        result = tools_for(client)["unreal_set_property"].run(
            object_path="/Game/A.A:A", property_name="DistMultiplier", value="2"
        )
        assert result.ok is True
        assert result.data["value"] == 2
        assert result.data["coercion"] == "inteiro"
        assert transport.body_for("/remote/object/property")["propertyValue"] == {
            "DistMultiplier": 2
        }

    def test_set_property_coerces_booleans_and_json(self):
        client, _ = client_with({"/remote/object/property": (200, b"")})
        tools = tools_for(client)
        assert tools["unreal_set_property"].run(
            object_path="/G.G:G", property_name="bHidden", value="true"
        ).data["value"] is True
        vector = tools["unreal_set_property"].run(
            object_path="/G.G:G", property_name="Location", value='{"X":1,"Y":2,"Z":3}'
        ).data["value"]
        assert vector == {"X": 1, "Y": 2, "Z": 3}

    def test_set_property_keeps_plain_text_as_text(self):
        client, _ = client_with({"/remote/object/property": (200, b"")})
        result = tools_for(client)["unreal_set_property"].run(
            object_path="/G.G:G", property_name="ActorLabel", value="MeuAtor"
        )
        assert result.data["value"] == "MeuAtor"
        assert result.data["coercion"] == "texto"

    def test_set_property_error_suggests_describe(self):
        transport = FakeTransport({
            "/remote/object/property": (400, b'{"errorMessage": "invalid"}')
        })
        client = RemoteControlClient(
            UnrealBridgeConfig(), transport=transport, verify_on_start=False
        )
        result = tools_for(client)["unreal_set_property"].run(
            object_path="/G.G:G", property_name="NaoExiste", value="1"
        )
        assert result.ok is False
        assert "unreal_describe_object" in result.data["hint"]

    def test_set_property_requires_all_three_arguments(self):
        client, _ = client_with({})
        tool = tools_for(client)["unreal_set_property"]
        assert tool.run(property_name="P", value="1").ok is False
        assert tool.run(object_path="/G.G:G", value="1").ok is False
        assert tool.run(object_path="/G.G:G", property_name="P").ok is False

    # ------------------------------------------------------ call_function
    def test_call_function_returns_return_value(self):
        client, _ = client_with({"/remote/object/call": {"ReturnValue": True}})
        result = tools_for(client)["unreal_call_function"].run(
            object_path="/Game/A.A:A", function_name="SetActorLocation",
            parameters_json='{"NewLocation": {"X": 100, "Y": 0, "Z": 30}}',
        )
        assert result.ok is True
        assert result.data["return"]["ReturnValue"] is True

    def test_call_function_without_parameters_sends_empty_object(self):
        client, transport = client_with({"/remote/object/call": {}})
        tools_for(client)["unreal_call_function"].run(
            object_path="/G.G:G", function_name="K2_DestroyActor"
        )
        assert transport.body_for("/remote/object/call")["parameters"] == {}

    def test_call_function_rejects_malformed_json(self):
        client, _ = client_with({})
        result = tools_for(client)["unreal_call_function"].run(
            object_path="/G.G:G", function_name="F", parameters_json="{nao é json}"
        )
        assert result.ok is False
        assert "JSON" in result.error

    def test_call_function_rejects_json_array(self):
        client, _ = client_with({})
        result = tools_for(client)["unreal_call_function"].run(
            object_path="/G.G:G", function_name="F", parameters_json="[1,2]"
        )
        assert result.ok is False
        assert "OBJETO" in result.error

    def test_call_function_error_explains_blueprintcallable(self):
        transport = FakeTransport({
            "/remote/object/call": (400, b'{"errorMessage": "Function not found"}')
        })
        client = RemoteControlClient(
            UnrealBridgeConfig(), transport=transport, verify_on_start=False
        )
        result = tools_for(client)["unreal_call_function"].run(
            object_path="/G.G:G", function_name="MetodoPrivado"
        )
        assert result.ok is False
        assert "BlueprintCallable" in result.data["hint"]

    # -------------------------------------------------- ferramentas Python
    def test_create_blueprint_refuses_rc_only_transport(self):
        client, _ = client_with({}, transport="rc")
        result = tools_for(client)["unreal_create_blueprint_class"].run(
            asset_name="BP_Inventario"
        )
        assert result.ok is False
        assert "Python Editor Script Plugin" in result.error
        assert "NÃO tem rota para criar assets" in result.error
        assert "LUMEN_UNREAL_TRANSPORT" in result.error

    def test_create_blueprint_marks_result_as_unvalidated(self):
        client, transport = client_with(
            {"/remote/object/call": PYTHON_OK_BODY}, transport="auto"
        )
        result = tools_for(client)["unreal_create_blueprint_class"].run(
            asset_name="BP_Inventario", package_path="/Game/Blueprints",
            parent_class="Actor",
        )
        assert result.ok is True
        assert result.data["needs_manual_validation"] is True
        assert result.data["validation"] == NEEDS_MANUAL_VALIDATION
        assert result.data["notes"]

    def test_create_blueprint_calls_the_python_library(self):
        client, transport = client_with(
            {"/remote/object/call": PYTHON_OK_BODY}, transport="auto"
        )
        tools_for(client)["unreal_create_blueprint_class"].run(asset_name="BP_X")
        body = transport.body_for("/remote/object/call")
        assert body["objectPath"] == (
            "/Script/PythonScriptPlugin.Default__PythonScriptLibrary"
        )
        assert body["functionName"] == "ExecutePythonCommandEx"
        assert "BP_X" in body["parameters"]["PythonCommand"]

    def test_create_blueprint_propagates_editor_error(self):
        """Erro do editor não pode virar sucesso silencioso."""
        client, _ = client_with(
            {"/remote/object/call": PYTHON_ERROR_BODY}, transport="auto"
        )
        result = tools_for(client)["unreal_create_blueprint_class"].run(
            asset_name="BP_Inventario"
        )
        assert result.ok is False
        assert "não confirmou sucesso" in result.error
        assert result.data["needs_manual_validation"] is True

    def test_create_blueprint_rejects_bad_asset_name(self):
        client, _ = client_with({}, transport="auto")
        result = tools_for(client)["unreal_create_blueprint_class"].run(
            asset_name="../../etc/passwd"
        )
        assert result.ok is False
        assert "inválido" in result.error

    def test_add_component_refuses_rc_only_transport(self):
        client, _ = client_with({}, transport="rc")
        result = tools_for(client)["unreal_add_component"].run(
            blueprint_path="/Game/Blueprints/BP_A.BP_A",
            component_class="StaticMeshComponent",
        )
        assert result.ok is False
        assert "grafo" in result.error or "Python" in result.error

    def test_add_component_embeds_class_and_path_in_the_script(self):
        client, transport = client_with(
            {"/remote/object/call": PYTHON_OK_BODY}, transport="auto"
        )
        result = tools_for(client)["unreal_add_component"].run(
            blueprint_path="/Game/Blueprints/BP_A.BP_A",
            component_class="StaticMeshComponent",
            component_name="Mesh",
        )
        assert result.ok is True
        code = transport.body_for("/remote/object/call")["parameters"]["PythonCommand"]
        assert "StaticMeshComponent" in code
        assert "/Game/Blueprints/BP_A.BP_A" in code

    def test_add_component_rejects_bad_path(self):
        client, _ = client_with({}, transport="auto")
        result = tools_for(client)["unreal_add_component"].run(
            blueprint_path="nao-e-um-caminho", component_class="StaticMeshComponent"
        )
        assert result.ok is False


# ============================================================ geradores de código
class TestScriptGeneration:
    def test_blueprint_script_contains_the_essentials(self):
        script = build_blueprint_creation_script("BP_Inventario", "/Game/Blueprints")
        assert "create_asset" in script.code
        assert "BlueprintFactory" in script.code
        assert "BP_Inventario" in script.code
        assert script.needs_validation is True
        assert "TESTE_LOCAL.md" in script.code

    def test_blueprint_script_never_interpolates_raw_strings(self):
        """Uma aspa no nome não pode virar código."""
        script = build_blueprint_creation_script("BP_Ok", "/Game/Ok")
        assert "BLUEPRINT_NAME = " in script.code
        # o valor é um literal JSON entre aspas duplas, não concatenação crua
        line = [l for l in script.code.splitlines() if l.startswith("BLUEPRINT_NAME")]
        assert line[0] == 'BLUEPRINT_NAME = "BP_Ok"'

    def test_blueprint_script_rejects_injection_attempts(self):
        for bad in ('BP"; import os; os.system("rm -rf /")', "BP Ator", "BP/x", "1BP"):
            with pytest.raises(PythonScriptError):
                build_blueprint_creation_script(bad)

    def test_package_path_must_start_with_slash(self):
        with pytest.raises(PythonScriptError, match="caminho de pacote"):
            build_blueprint_creation_script("BP_X", "Game/Blueprints")

    def test_add_component_rejects_relative_path(self):
        with pytest.raises(PythonScriptError, match="caminho de pacote"):
            build_add_component_script("Game/BP_A.BP_A", "StaticMeshComponent")

    def test_add_component_rejects_invalid_class_name(self):
        with pytest.raises(PythonScriptError, match="classe"):
            build_add_component_script("/Game/BP_A.BP_A", "Static Mesh; drop")

    def test_add_component_accepts_path_with_or_without_dot(self):
        with_dot = build_add_component_script("/Game/BP_A.BP_A", "StaticMeshComponent")
        without = build_add_component_script("/Game/BP_A", "StaticMeshComponent")
        assert "StaticMeshComponent" in with_dot.code
        assert "StaticMeshComponent" in without.code

    def test_properties_are_embbeded_as_literals(self):
        script = build_add_component_script(
            "/Game/BP_A.BP_A", "StaticMeshComponent", "Mesh",
            properties={"CastShadow": "true"},
        )
        assert 'PROPERTIES = {"CastShadow": "true"}' in script.code

    def test_unsupported_property_value_type_is_refused(self):
        with pytest.raises(PythonScriptError, match="segurança"):
            build_add_component_script(
                "/Game/BP_A.BP_A", "StaticMeshComponent", properties={"X": ["a"]}
            )

    def test_compile_script_is_generated(self):
        script = build_compile_script("/Game/BP_A.BP_A")
        assert "compile_blueprint" in script.code

    def test_save_script_with_and_without_paths(self):
        assert "save_directory" in build_save_script(["/Game/Blueprints"]).code
        assert "save_dirty_packages" in build_save_script().code

    def test_every_script_is_valid_python(self):
        """O script será executado dentro do editor: precisa ao menos compilar."""
        scripts = [
            build_blueprint_creation_script("BP_X"),
            build_add_component_script("/Game/BP_X.BP_X", "StaticMeshComponent"),
            build_compile_script("/Game/BP_X.BP_X"),
            build_save_script(),
            build_save_script(["/Game/Blueprints"]),
        ]
        for script in scripts:
            compile(script.code, "<unreal-script>", "exec")


# ========================================================= interpretação de saída
class TestExecutionResultParsing:
    def test_success_payload(self):
        result = parse_execution_result(PYTHON_OK_BODY)
        assert result["ok"] is True
        assert "blueprint criado" in result["output"]

    def test_error_log_marks_failure(self):
        result = parse_execution_result(PYTHON_ERROR_BODY)
        assert result["ok"] is False
        assert result["errors"][0]["type"] == "Error"

    def test_unrecognized_payload_is_not_reported_as_success(self):
        """Sem campo conhecido, o parser diz que não sabe — não inventa."""
        result = parse_execution_result({"algo": "diferente"})
        assert result["ok"] is False
        assert result["unrecognized"] is True

    def test_non_mapping_payload_is_not_reported_as_success(self):
        assert parse_execution_result(None)["ok"] is False
        assert parse_execution_result("texto")["ok"] is False

    def test_logs_in_snake_case_are_understood(self):
        result = parse_execution_result({
            "command_result": "ok",
            "log_output": [{"type": "Info", "output": "feito"}],
        })
        assert result["ok"] is True
        assert result["logs"][0]["text"] == "feito"


# ============================================================== integração MCP
class TestMcpIntegration:
    """As ferramentas da ponte aparecem no `tools/list` do servidor MCP."""

    def _server_with_unreal(self, tmp_path, *, enabled=True):
        """Servidor MCP com a ponte habilitada pela API pública do controller.

        Nada é injetado por baixo do pano: usa ``enable_unreal_bridge()``,
        que é exatamente o que a aplicação faz.
        """
        import logging

        from app.mcp_server import ControllerToolGateway, McpServer, dumps_line
        from app.security.permissions import PermissionLevel, PermissionManager
        from app.tools.control import ToolsController

        logging.disable(logging.CRITICAL)
        permissions = PermissionManager()
        permissions.grant(PermissionLevel.CHAT)
        permissions.grant(PermissionLevel.READ)
        permissions.grant(PermissionLevel.WRITE)
        controller = ToolsController(
            permissions,
            workspaces_file=tmp_path / "w.json",
            audit_file=tmp_path / "a.jsonl",
            terminal_file=tmp_path / "t.json",
        )
        transport = FakeTransport({"/remote/info": INFO_BODY})
        client = RemoteControlClient(
            UnrealBridgeConfig(transport="auto"),
            transport=transport, verify_on_start=False,
        )
        if enabled:
            controller.enable_unreal_bridge(client)
        server = McpServer(ControllerToolGateway(controller, allow_write=True))
        server.handle_message(dumps_line({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }))
        server.handle_message(dumps_line({
            "jsonrpc": "2.0", "method": "notifications/initialized",
        }))
        return server, dumps_line, transport

    def test_unreal_tools_are_absent_when_bridge_is_disabled(self, tmp_path):
        """Fail-closed: sem enable_unreal_bridge não há ferramenta unreal_*."""
        server, dumps_line, _ = self._server_with_unreal(tmp_path, enabled=False)
        response = server.handle_message(dumps_line({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
        }))
        names = {t["name"] for t in response["result"]["tools"]}
        assert not (set(UNREAL_TOOLS) & names)

    def test_unreal_tools_are_offered_to_the_client(self, tmp_path):
        server, dumps_line, _ = self._server_with_unreal(tmp_path)
        response = server.handle_message(dumps_line({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
        }))
        names = {t["name"] for t in response["result"]["tools"]}
        assert set(UNREAL_TOOLS) <= names

    def test_unreal_tool_schema_has_object_input(self, tmp_path):
        server, dumps_line, _ = self._server_with_unreal(tmp_path)
        response = server.handle_message(dumps_line({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
        }))
        tool = next(
            t for t in response["result"]["tools"]
            if t["name"] == "unreal_create_blueprint_class"
        )
        assert tool["inputSchema"]["type"] == "object"
        assert tool["inputSchema"]["required"] == ["asset_name"]
        assert "package_path" in tool["inputSchema"]["properties"]

    def test_calling_unreal_get_info_through_mcp(self, tmp_path):
        server, dumps_line, transport = self._server_with_unreal(tmp_path)
        response = server.handle_message(dumps_line({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "unreal_get_info", "arguments": {}},
        }))
        result = response["result"]
        assert result["isError"] is False
        assert "unreal_get_info" in result["content"][0]["text"]


# ============================================ catálogo do Planner (anti-drift)
class TestPlannerCatalogIntegration:
    """As `unreal_*` entram no catálogo do Planner só quando habilitadas.

    O catálogo é a allowlist que impede o Planner de inventar nomes, então
    os dois lados (catálogo e ferramentas) precisam concordar. Estes testes
    quebram se alguém renomear um parâmetro em um lugar só.
    """

    def test_catalog_omits_unreal_tools_by_default(self):
        from app.planner.catalog import build_catalog

        assert not [n for n in build_catalog(include_terminal=False) if n.startswith("unreal_")]

    def test_catalog_includes_all_seven_when_enabled(self):
        from app.planner.catalog import build_catalog

        catalog = build_catalog(include_terminal=False, include_unreal=True)
        assert sorted(n for n in catalog if n.startswith("unreal_")) == sorted(UNREAL_TOOLS)

    def test_catalog_can_filter_to_only_read_only_tools(self):
        from app.planner.catalog import build_catalog

        catalog = build_catalog(
            include_terminal=False, include_unreal=True,
            include_unreal_mutating=False,
        )
        assert {n for n in catalog if n.startswith("unreal_")} == set(UNREAL_READ_ONLY_TOOLS)

    def test_catalog_parameters_match_the_tool_definitions(self):
        """O catálogo e a ToolDefinition têm de listar os MESMOS parâmetros."""
        from app.planner.catalog import build_catalog

        catalog = build_catalog(include_terminal=False, include_unreal=True)
        client, _ = client_with({})
        for definition in unreal_definitions(client):
            if not definition.name.startswith("unreal_"):
                continue
            spec_params = {p["name"] for p in catalog[definition.name]["parameters"]}
            tool_params = {p.name for p in definition.parameters}
            assert spec_params == tool_params, (
                f"{definition.name}: catálogo {sorted(spec_params)} != "
                f"ferramenta {sorted(tool_params)}"
            )

    def test_catalog_required_flags_match(self):
        from app.planner.catalog import build_catalog

        catalog = build_catalog(include_terminal=False, include_unreal=True)
        client, _ = client_with({})
        for definition in unreal_definitions(client):
            if not definition.name.startswith("unreal_"):
                continue
            spec_required = {
                p["name"] for p in catalog[definition.name]["parameters"] if p["required"]
            }
            tool_required = {p.name for p in definition.parameters if p.required}
            assert spec_required == tool_required, definition.name

    def test_catalog_types_are_supported_by_the_planner(self):
        """O Planner só valida string/integer/array — nada de tipo exótico."""
        from app.planner.catalog import build_catalog

        catalog = build_catalog(include_terminal=False, include_unreal=True)
        for name, spec in catalog.items():
            for param in spec["parameters"]:
                assert param["type"] in ("string", "integer", "array"), (name, param)

    def test_controller_is_fail_closed_by_default(self, tmp_path):
        import logging

        from app.security.permissions import PermissionManager
        from app.tools.control import ToolsController

        logging.disable(logging.CRITICAL)
        controller = ToolsController(
            PermissionManager(),
            workspaces_file=tmp_path / "w.json",
            audit_file=tmp_path / "a.jsonl",
            terminal_file=tmp_path / "t.json",
        )
        assert controller.unreal_bridge_enabled is False
        assert not [
            n for n in controller.planning_catalog() if n.startswith("unreal_")
        ]
        assert not [
            t["name"] for t in controller.build_registry().list_tools()
            if t["name"].startswith("unreal_")
        ]

    def test_enable_then_disable_removes_everything(self, tmp_path):
        import logging

        from app.security.permissions import PermissionManager
        from app.tools.control import ToolsController

        logging.disable(logging.CRITICAL)
        controller = ToolsController(
            PermissionManager(),
            workspaces_file=tmp_path / "w.json",
            audit_file=tmp_path / "a.jsonl",
            terminal_file=tmp_path / "t.json",
        )
        client, _ = client_with({})
        outcome = controller.enable_unreal_bridge(client)
        assert outcome["enabled"] is True
        assert outcome["base_url"] == "http://127.0.0.1:30010"

        assert sorted(
            n for n in controller.planning_catalog() if n.startswith("unreal_")
        ) == sorted(UNREAL_TOOLS)
        assert sorted(
            d.name for d in controller.tool_protocol().definitions
            if d.name.startswith("unreal_")
        ) == sorted(UNREAL_TOOLS)

        controller.disable_unreal_bridge()
        assert controller.unreal_bridge_enabled is False
        assert not [
            n for n in controller.planning_catalog() if n.startswith("unreal_")
        ]

    def test_bad_config_reports_failure_instead_of_raising(self, tmp_path):
        import logging

        from app.security.permissions import PermissionManager
        from app.tools.control import ToolsController

        logging.disable(logging.CRITICAL)
        controller = ToolsController(
            PermissionManager(),
            workspaces_file=tmp_path / "w.json",
            audit_file=tmp_path / "a.jsonl",
            terminal_file=tmp_path / "t.json",
        )
        outcome = controller.enable_unreal_bridge(port=99999)
        assert outcome["enabled"] is False
        assert outcome["reason"]
        assert controller.unreal_bridge_enabled is False

    def test_enabling_the_bridge_grants_no_permission(self, tmp_path):
        """Aparecer no catálogo não é poder executar: permissão é outra coisa."""
        import logging

        from app.security.permissions import PermissionDeniedError, PermissionManager
        from app.tools.control import ToolsController

        logging.disable(logging.CRITICAL)
        permissions = PermissionManager()  # só CHAT
        controller = ToolsController(
            permissions,
            workspaces_file=tmp_path / "w.json",
            audit_file=tmp_path / "a.jsonl",
            terminal_file=tmp_path / "t.json",
        )
        client, _ = client_with({})
        controller.enable_unreal_bridge(client)

        with pytest.raises(PermissionDeniedError):
            controller.build_registry().execute("unreal_get_info")


def test_unreal_config_reads_env_file_with_environment_precedence(tmp_path, monkeypatch):
    import app.unreal_bridge.config as module
    env_file = tmp_path / ".env"
    env_file.write_text("LUMEN_UNREAL_RC_PORT=30011\nLUMEN_UNREAL_TRANSPORT=rc\n", encoding="utf-8")
    monkeypatch.setattr(module, "ENV_FILE", env_file)
    for name in ("LUMEN_UNREAL_RC_PORT", "LUMEN_UNREAL_TRANSPORT"):
        monkeypatch.delenv(name, raising=False)
    assert module.UnrealBridgeConfig.from_env().port == 30011
    assert module.UnrealBridgeConfig.from_env().transport == "rc"
    monkeypatch.setenv("LUMEN_UNREAL_RC_PORT", "30012")
    assert module.UnrealBridgeConfig.from_env().port == 30012


def test_unreal_mutation_waits_for_approval_before_any_http(tmp_path):
    from app.mcp_server.gateway import ControllerToolGateway
    from app.security.permissions import PermissionLevel, PermissionManager
    from app.tools.control import ToolsController

    permissions = PermissionManager()
    permissions.grant(PermissionLevel.WRITE)
    client, transport = client_with({
        "/remote/info": INFO_BODY,
        "/remote/object/property": (200, b""),
    })
    controller = ToolsController(
        permissions, workspaces_file=tmp_path / "w.json",
        audit_file=tmp_path / "a.jsonl", terminal_file=tmp_path / "t.json",
    )
    controller.enable_unreal_bridge(client)
    definitions = {d.name: d for d in controller.tool_protocol().definitions}
    assert all(not definitions[name].destructive for name in UNREAL_READ_ONLY_TOOLS)
    assert all(
        definitions[name].destructive
        for name in set(UNREAL_TOOLS) - set(UNREAL_READ_ONLY_TOOLS)
    )
    assert definitions["unreal_add_component"].metadata["validation"] == NEEDS_MANUAL_VALIDATION

    gateway = ControllerToolGateway(controller, allow_write=True)
    outcome = gateway.call("unreal_set_property", {
        "object_path": "/Game/A.A:A", "property_name": "bHidden", "value": "true",
    })
    assert outcome.awaiting_approval is True
    assert transport.calls == [], "o editor não pode ser alterado antes de aprovar"
    controller.refuse()
    assert transport.calls == [], "recusa não toca a RC API"

    outcome = gateway.call("unreal_set_property", {
        "object_path": "/Game/A.A:A", "property_name": "bHidden", "value": "true",
    })
    assert outcome.awaiting_approval is True
    assert transport.calls == []
    controller.approve()
    assert any(call["url"].endswith("/remote/object/property") for call in transport.calls)


def test_unreal_mutation_without_write_never_calls_editor(tmp_path):
    from app.security.permissions import PermissionManager
    from app.tools.control import ToolsController
    from app.tools.protocol import ToolCall

    client, transport = client_with({"/remote/info": INFO_BODY})
    controller = ToolsController(
        PermissionManager(), workspaces_file=tmp_path / "w.json",
        audit_file=tmp_path / "a.jsonl", terminal_file=tmp_path / "t.json",
    )
    controller.enable_unreal_bridge(client)
    result = controller.run_tool_call(ToolCall(tool="unreal_set_property", parameters={
        "object_path": "/Game/A.A:A", "property_name": "bHidden", "value": "true",
    }))
    assert result.ok is False
    assert not result.data.get("awaiting_approval")
    assert transport.calls == []
