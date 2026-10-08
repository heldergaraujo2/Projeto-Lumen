"""Ferramentas da ponte com o Unreal Editor (Fase 4).

Segue o contrato de ``app/tools/base.py`` (``StructuredTool`` → ``ToolResult``),
o mesmo das ferramentas de filesystem/terminal. Assim elas entram no
``ToolRegistry``, passam pelo porteiro de permissões e aparecem no MCP e no
planner da UI conforme as opções de exposição de cada consumer.

As quatro ferramentas que alteram o projeto:

=========================================  ===========================  ==========
Ferramenta                                 Como alcança o editor        Validação
=========================================  ===========================  ==========
``unreal_create_blueprint_class``          Python (Editor Script)       manual
``unreal_add_component``                   Python (Editor Script)       manual
``unreal_set_property``                    RC API pura                  doc oficial
``unreal_call_function``                   RC API pura                  doc oficial
=========================================  ===========================  ==========

Três consultas somente de leitura, disponíveis separadamente das ações:

- ``unreal_get_info`` — ``GET /remote/info``: diz se há editor e quais rotas
  existem. É o **primeiro** teste de conexão;
- ``unreal_describe_object`` — ``PUT /remote/object/describe``: descobre os
  nomes reais de propriedades e funções sem alterá-las;
- ``unreal_search_assets`` — ``PUT /remote/search/assets``: localiza assets
  no Content Browser sem modificá-los.

Cada ``ToolDefinition`` carrega ``metadata["validation"]`` dizendo o que foi
conferido contra a documentação oficial e o que **ainda depende de teste
manual num Unreal real**. A saída de cada tool repete isso, para que o
usuário veja em vez de supor.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.security.permissions import PermissionLevel
from app.tools.base import StructuredTool, ToolResult
from app.tools.protocol import ParameterDefinition, ToolDefinition
from app.unreal_bridge.client import RemoteControlClient
from app.unreal_bridge.config import UnrealBridgeError, UnrealUnavailableError
from app.unreal_bridge.python_script import (
    PythonScriptError,
    build_add_component_script,
    build_blueprint_creation_script,
    parse_execution_result,
)

#: Marcadores de validação usados em ``ToolDefinition.metadata["validation"]``.
VALIDATED_AGAINST_DOC = "doc-oficial"
NEEDS_MANUAL_VALIDATION = "precisa-validacao-manual"

#: Gate padrão das ferramentas mutáveis da ponte.
REQUIRED_PERMISSION = PermissionLevel.WRITE
#: Consultas Unreal exigem READ e não criam checkpoints de escrita.
READ_ONLY_PERMISSION = PermissionLevel.READ


class UnrealTool(StructuredTool):
    """Base das ferramentas da ponte: validação de argumentos + erros claros."""

    _abstract_base = True

    required_permission = REQUIRED_PERMISSION
    mutates_state = True
    operation = "unreal"

    def __init__(self, client: RemoteControlClient) -> None:
        self._client = client

    @property
    def client(self) -> RemoteControlClient:
        return self._client

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters(),
            destructive=self.mutates_state,
            metadata={"validation": self.validation_status},
        )

    def parameters(self) -> tuple[ParameterDefinition, ...]:  # pragma: no cover - abstrato
        raise NotImplementedError

    @property
    def validation_status(self) -> str:  # pragma: no cover - abstrato
        raise NotImplementedError

    # ------------------------------------------------------------ utilidades
    def _require_text(self, kwargs: Mapping[str, Any], key: str) -> tuple[str, ToolResult | None]:
        value = kwargs.get(key)
        if not isinstance(value, str) or not value.strip():
            return "", ToolResult(
                ok=False,
                data={"tool": self.name, "missing": key},
                error=f"Parâmetro '{key}' é obrigatório e deve ser texto não vazio.",
            )
        return value.strip(), None

    def _fail(self, error: str, **data: Any) -> ToolResult:
        return ToolResult(ok=False, data={"tool": self.name, **data}, error=error)


# ======================================================= infraestrutura/saúde
class UnrealGetInfoTool(UnrealTool):
    """``GET /remote/info`` — o teste de conexão da Fase 4."""

    name = "unreal_get_info"
    required_permission = READ_ONLY_PERMISSION
    mutates_state = False
    description = (
        "Verifica a conexão com o Unreal Editor e lista as rotas da Remote "
        "Control API disponíveis. É uma consulta de saúde, sem alterações "
        "no projeto."
    )
    validation_status = VALIDATED_AGAINST_DOC

    def parameters(self) -> tuple[ParameterDefinition, ...]:
        return ()

    def run(self, **kwargs: Any) -> ToolResult:
        config = self._client.config
        try:
            payload = self._client.info()
        except UnrealUnavailableError as exc:
            return self._fail(str(exc), base_url=config.base_url, connected=False)
        except UnrealBridgeError as exc:
            return self._fail(str(exc), base_url=config.base_url, connected=True)

        routes = [str(e.get("Path")) for e in (payload.get("HttpRoutes") or [])
                  if isinstance(e, Mapping)]
        return ToolResult(ok=True, data={
            "tool": self.name,
            "connected": True,
            "base_url": config.base_url,
            "transport": config.transport,
            "python_available": config.python_enabled,
            "route_count": len(routes),
            "routes": sorted(routes),
            "has_python_route": any(
                "python" in route.lower() for route in routes
            ),
        })


class UnrealDescribeObjectTool(UnrealTool):
    """``PUT /remote/object/describe`` — descobrir nomes reais antes de usar."""

    name = "unreal_describe_object"
    required_permission = READ_ONLY_PERMISSION
    mutates_state = False
    description = (
        "Consulta um objeto do Unreal Editor em memória (Actor no nível ou "
        "asset) e lista propriedades e funções com tipos. Somente leitura: "
        "não altera o objeto nem o projeto."
    )
    validation_status = VALIDATED_AGAINST_DOC

    def parameters(self) -> tuple[ParameterDefinition, ...]:
        return (
            ParameterDefinition(
                "object_path", "string", True,
                "Caminho do UObject, ex.: "
                "'/Game/Maps/MeuMapa.MeuMapa:PersistentLevel.MeuAtor'.",
            ),
        )

    def run(self, **kwargs: Any) -> ToolResult:
        object_path, failure = self._require_text(kwargs, "object_path")
        if failure:
            return failure
        try:
            payload = self._client.describe(object_path)
        except UnrealBridgeError as exc:
            return self._fail(str(exc), object_path=object_path)

        properties = payload.get("Properties") or []
        functions = payload.get("Functions") or []
        names = [
            str(p.get("Name")) for p in properties
            if isinstance(p, Mapping) and p.get("Name")
        ]
        function_names = [
            str(f.get("Name")) for f in functions
            if isinstance(f, Mapping) and f.get("Name")
        ]
        return ToolResult(ok=True, data={
            "tool": self.name,
            "object_path": object_path,
            "class": payload.get("Class"),
            "name": payload.get("Name"),
            "property_count": len(names),
            "properties": names[:200],
            "function_count": len(function_names),
            "functions": function_names[:200],
        })


class UnrealSearchAssetsTool(UnrealTool):
    """``PUT /remote/search/assets`` — achar o caminho de um asset."""

    name = "unreal_search_assets"
    required_permission = READ_ONLY_PERMISSION
    mutates_state = False
    description = (
        "Busca assets no Content Browser pelo nome. Use para descobrir o "
        "caminho exato (ex.: '/Game/Blueprints/BP_Ator.BP_Ator') antes de "
        "referenciá-lo em outra ferramenta."
    )
    validation_status = VALIDATED_AGAINST_DOC

    def parameters(self) -> tuple[ParameterDefinition, ...]:
        return (
            ParameterDefinition(
                "query", "string", True,
                "Texto a procurar no nome do asset ('' devolve tudo).",
            ),
            ParameterDefinition(
                "class_names", "array", False,
                "Filtra por classe, ex.: ['Blueprint', 'StaticMesh'].",
            ),
            ParameterDefinition(
                "package_paths", "array", False,
                "Filtra por pasta, ex.: ['/Game/Blueprints'].",
            ),
        )

    def run(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query")
        if not isinstance(query, str):
            return self._fail("Parâmetro 'query' é obrigatório (pode ser vazio).")

        def _string_list(key: str) -> list[str]:
            value = kwargs.get(key) or []
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                return []
            return [str(item) for item in value]

        try:
            assets = self._client.search_assets(
                query,
                class_names=_string_list("class_names"),
                package_paths=_string_list("package_paths"),
            )
        except UnrealBridgeError as exc:
            return self._fail(str(exc), query=query)

        return ToolResult(ok=True, data={
            "tool": self.name,
            "query": query,
            "count": len(assets),
            "assets": [
                {"name": a.get("Name"), "class": a.get("Class"), "path": a.get("Path")}
                for a in assets[:100] if isinstance(a, Mapping)
            ],
        })


# ========================================================== RC API pura
class UnrealSetPropertyTool(UnrealTool):
    """``PUT /remote/object/property`` — a rota documentada, sem Python."""

    name = "unreal_set_property"
    description = (
        "Define o valor de uma propriedade de um objeto do Unreal Editor. "
        "Funciona pela Remote Control API pura (não precisa de Python). "
        "Requisitos do editor: a propriedade deve ser pública, SEM "
        "BlueprintGetter/BlueprintSetter, e 'EditAnywhere' (no editor) ou "
        "'BlueprintVisible' (em PIE). Use unreal_describe_object antes para "
        "confirmar o nome exato."
    )
    validation_status = VALIDATED_AGAINST_DOC

    def parameters(self) -> tuple[ParameterDefinition, ...]:
        return (
            ParameterDefinition(
                "object_path", "string", True, "Caminho do UObject alvo.",
            ),
            ParameterDefinition(
                "property_name", "string", True, "Nome da propriedade (nome C++).",
            ),
            ParameterDefinition(
                "value", "string", True,
                "Novo valor. Envie texto: números e booleanos são convertidos "
                "('2', 'true', 'false'); use JSON para vetores/estruturas "
                "('{\"X\":1,\"Y\":0,\"Z\":0}').",
            ),
        )

    def run(self, **kwargs: Any) -> ToolResult:
        object_path, failure = self._require_text(kwargs, "object_path")
        if failure:
            return failure
        property_name, failure = self._require_text(kwargs, "property_name")
        if failure:
            return failure
        value, failure = self._require_text(kwargs, "value")
        if failure:
            return failure

        converted, note = _coerce_value(value)
        try:
            self._client.set_property(object_path, property_name, converted)
        except UnrealBridgeError as exc:
            return self._fail(
                str(exc), object_path=object_path, property_name=property_name,
                hint=(
                    "Confirme o nome com unreal_describe_object. Propriedades com "
                    "BlueprintGetter/BlueprintSetter NÃO são acessíveis por esta "
                    "rota — nesse caso use unreal_call_function com o getter/setter."
                ),
            )
        return ToolResult(ok=True, data={
            "tool": self.name,
            "object_path": object_path,
            "property_name": property_name,
            "value": converted,
            "coercion": note,
            "transaction": True,
        })


class UnrealCallFunctionTool(UnrealTool):
    """``PUT /remote/object/call`` — a rota documentada, sem Python."""

    name = "unreal_call_function"
    description = (
        "Chama uma função de um objeto do Unreal Editor. Funciona pela Remote "
        "Control API pura. A função precisa ser CHAMÁVEL POR BLUEPRINT "
        "(BlueprintCallable em C++, ou definida em Blueprint). Parâmetros vão "
        "em um objeto JSON; omitir um parâmetro faz o editor construir o "
        "default do tipo."
    )
    validation_status = VALIDATED_AGAINST_DOC

    def parameters(self) -> tuple[ParameterDefinition, ...]:
        return (
            ParameterDefinition("object_path", "string", True, "Caminho do UObject alvo."),
            ParameterDefinition("function_name", "string", True, "Nome da função (nome C++)."),
            ParameterDefinition(
                "parameters_json", "string", False,
                "Parâmetros em JSON, ex.: '{\"NewLocation\":{\"X\":100,\"Y\":0,\"Z\":30}}'. "
                "Vazio = nenhum parâmetro.",
            ),
        )

    def run(self, **kwargs: Any) -> ToolResult:
        object_path, failure = self._require_text(kwargs, "object_path")
        if failure:
            return failure
        function_name, failure = self._require_text(kwargs, "function_name")
        if failure:
            return failure

        raw = kwargs.get("parameters_json") or ""
        parameters: dict[str, Any] = {}
        if isinstance(raw, str) and raw.strip():
            import json

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                return self._fail(
                    f"'parameters_json' não é JSON válido: {exc.msg}.",
                    object_path=object_path, function_name=function_name,
                )
            if not isinstance(parsed, dict):
                return self._fail(
                    "'parameters_json' deve ser um OBJETO JSON (chaves = nomes dos "
                    "parâmetros C++).",
                    object_path=object_path, function_name=function_name,
                )
            parameters = parsed

        try:
            response = self._client.call_function(
                object_path, function_name, parameters, generate_transaction=True
            )
        except UnrealBridgeError as exc:
            return self._fail(
                str(exc), object_path=object_path, function_name=function_name,
                hint=(
                    "A função precisa ser BlueprintCallable e o nome deve ser o do "
                    "C++ (não o rótulo do nó). Use unreal_describe_object para ver "
                    "as funções disponíveis."
                ),
            )
        return ToolResult(ok=True, data={
            "tool": self.name,
            "object_path": object_path,
            "function_name": function_name,
            "parameters": parameters,
            "return": response if isinstance(response, Mapping) else {"value": response},
            "transaction": True,
        })


# =============================================== dependem do Python no editor
class UnrealCreateBlueprintClassTool(UnrealTool):
    """Cria uma classe Blueprint — exige Python no editor (ver módulo)."""

    name = "unreal_create_blueprint_class"
    description = (
        "Cria uma classe Blueprint (ex.: BP_Inventario) no Content Browser. "
        "ATENÇÃO: a Remote Control API não tem rota para criar assets — esta "
        "ferramenta executa Python dentro do editor e exige o 'Python Editor "
        "Script Plugin' habilitado MAIS bEnableRemotePythonExecution=True em "
        "Config/DefaultRemoteControl.ini. Sem isso, ela falha e diz o motivo."
    )
    validation_status = NEEDS_MANUAL_VALIDATION

    def parameters(self) -> tuple[ParameterDefinition, ...]:
        return (
            ParameterDefinition(
                "asset_name", "string", True,
                "Nome do asset, ex.: 'BP_Inventario' (letras/números/underscore).",
            ),
            ParameterDefinition(
                "package_path", "string", False,
                "Pasta no Content Browser. Default: '/Game/Blueprints'.",
            ),
            ParameterDefinition(
                "parent_class", "string", False,
                "Classe pai. Default: 'Actor'. Use 'ActorComponent' para um "
                "componente, 'Actor' para um ator colocável no nível.",
            ),
        )

    def run(self, **kwargs: Any) -> ToolResult:
        asset_name, failure = self._require_text(kwargs, "asset_name")
        if failure:
            return failure
        audience = self._client.config.transport
        if audience == "rc":
            return self._fail(
                "Criar Blueprint exige o Python Editor Script Plugin; o "
                "transporte atual é 'rc', que só usa as rotas HTTP da Remote "
                "Control API — e a RC API NÃO tem rota para criar assets. "
                "Rode o servidor com LUMEN_UNREAL_TRANSPORT=auto (ou 'python') "
                "e habilite o plugin no projeto (ver TESTE_LOCAL.md).",
                asset_name=asset_name, transport=audience,
            )
        try:
            script = build_blueprint_creation_script(
                asset_name,
                str(kwargs.get("package_path") or "/Game/Blueprints"),
                parent_class=str(kwargs.get("parent_class") or "Actor"),
            )
        except PythonScriptError as exc:
            return self._fail(str(exc), asset_name=asset_name)

        return self._run_script(script, asset_name=asset_name)

    def _run_script(self, script: Any, **extra: Any) -> ToolResult:
        try:
            payload = self._client.execute_python(script.code)
        except UnrealUnavailableError as exc:
            return self._fail(str(exc), **extra)
        except UnrealBridgeError as exc:
            return self._fail(
                f"{exc} — se a mensagem falar de função não permitida, confira "
                "'CustomAllowedRemoteFunctionCalls' para "
                "'/Script/PythonScriptPlugin.PythonScriptLibrary' em "
                "Config/DefaultRemoteControl.ini (ver TESTE_LOCAL.md).",
                **extra,
            )
        result = parse_execution_result(payload)
        data = {
            "tool": self.name,
            **extra,
            "purpose": script.purpose,
            "validation": NEEDS_MANUAL_VALIDATION,
            "needs_manual_validation": True,
            "notes": list(script.notes),
            "ok": result["ok"],
            "output": result["output"],
            "logs": result["logs"],
            "raw_response": result["raw"],
        }
        if not result["ok"]:
            detail = "; ".join(
                entry["text"] for entry in result.get("errors", []) if entry.get("text")
            ) or result["output"] or "o editor não confirmou a execução"
            return ToolResult(ok=False, data=data, error=(
                f"O editor não confirmou sucesso: {detail}. "
                "A chamada executou Python no editor — verifique o Output Log "
                "do Unreal. Esta ferramenta AINDA NÃO foi validada contra um "
                "Unreal real (ver TESTE_LOCAL.md)."
            ))
        return ToolResult(ok=True, data=data)


class UnrealAddComponentTool(UnrealCreateBlueprintClassTool):
    """Adiciona um componente a um Blueprint — exige Python no editor."""

    name = "unreal_add_component"
    description = (
        "Adiciona um componente (ex.: StaticMeshComponent, SphereComponent) a "
        "um Blueprint existente. ATENÇÃO: exige Python Editor Script Plugin + "
        "bEnableRemotePythonExecution=True — a Remote Control API não edita "
        "grafos de Blueprint. Informe o caminho do asset "
        "('/Game/Blueprints/BP_Ator.BP_Ator')."
    )
    validation_status = NEEDS_MANUAL_VALIDATION

    def parameters(self) -> tuple[ParameterDefinition, ...]:
        return (
            ParameterDefinition(
                "blueprint_path", "string", True,
                "Caminho do asset Blueprint, ex.: '/Game/Blueprints/BP_Ator.BP_Ator'.",
            ),
            ParameterDefinition(
                "component_class", "string", True,
                "Classe do componente, ex.: 'StaticMeshComponent'.",
            ),
            ParameterDefinition(
                "component_name", "string", False,
                "Nome do componente no Blueprint. Vazio = o editor escolhe.",
            ),
        )

    def run(self, **kwargs: Any) -> ToolResult:
        blueprint_path, failure = self._require_text(kwargs, "blueprint_path")
        if failure:
            return failure
        component_class, failure = self._require_text(kwargs, "component_class")
        if failure:
            return failure
        if self._client.config.transport == "rc":
            return self._fail(
                "Adicionar componente exige o Python Editor Script Plugin; o "
                "transporte atual é 'rc'. A RC API não edita grafos de Blueprint.",
                blueprint_path=blueprint_path, component_class=component_class,
            )
        try:
            script = build_add_component_script(
                blueprint_path,
                component_class,
                str(kwargs.get("component_name") or ""),
            )
        except PythonScriptError as exc:
            return self._fail(
                str(exc), blueprint_path=blueprint_path, component_class=component_class
            )
        return self._run_script(
            script, blueprint_path=blueprint_path, component_class=component_class
        )


def _coerce_value(raw: str) -> tuple[Any, str]:
    """Converte o texto recebido do MCP no tipo que o editor espera.

    O LLM manda string (é o que o protocolo oferece); a RC API espera
    número/booleano/objeto. Sem isso, ``"2"`` viraria a string ``"2"`` e o
    editor recusaria por tipo. Quando não há conversão óbvia, envia texto e
    diz isso no campo ``coercion`` em vez de adivinhar.
    """
    text = raw.strip()
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true", "booleano"
    try:
        return int(text), "inteiro"
    except ValueError:
        pass
    try:
        return float(text), "decimal"
    except ValueError:
        pass
    if text[:1] in "{[" and text[-1:] in "}]":
        import json

        try:
            return json.loads(text), "json"
        except json.JSONDecodeError:
            pass
    return raw, "texto"


#: Ferramentas da ponte, na ordem em que devem aparecer.
UNREAL_TOOL_CLASSES: tuple[type[UnrealTool], ...] = (
    UnrealGetInfoTool,
    UnrealDescribeObjectTool,
    UnrealSearchAssetsTool,
    UnrealSetPropertyTool,
    UnrealCallFunctionTool,
    UnrealCreateBlueprintClassTool,
    UnrealAddComponentTool,
)

#: Nomes de todas as ferramentas da ponte.
UNREAL_TOOLS: tuple[str, ...] = tuple(cls.name for cls in UNREAL_TOOL_CLASSES)
#: Subconjunto que apenas consulta o estado do editor/projeto.
UNREAL_READ_ONLY_TOOLS: tuple[str, ...] = tuple(
    cls.name for cls in UNREAL_TOOL_CLASSES if not cls.mutates_state
)


def build_unreal_registry(
    client: RemoteControlClient, *, read_only_only: bool = False
) -> list[UnrealTool]:
    """Instancia ferramentas para o cliente.

    ``read_only_only=True`` retira do registry toda classe que altera o
    projeto. É usado pela UI na ativação inicial segura; o default mantém
    o comportamento completo para consumidores que já habilitam a ponte.
    """
    return [
        cls(client) for cls in UNREAL_TOOL_CLASSES
        if not read_only_only or not cls.mutates_state
    ]


def unreal_definitions(
    client: RemoteControlClient, *, read_only_only: bool = False
) -> tuple[ToolDefinition, ...]:
    """``ToolDefinition`` das ferramentas expostas pela ponte."""
    return tuple(
        tool.definition()
        for tool in build_unreal_registry(client, read_only_only=read_only_only)
    )


__all__ = [
    "NEEDS_MANUAL_VALIDATION",
    "READ_ONLY_PERMISSION",
    "REQUIRED_PERMISSION",
    "UNREAL_READ_ONLY_TOOLS",
    "UNREAL_TOOL_CLASSES",
    "UNREAL_TOOLS",
    "VALIDATED_AGAINST_DOC",
    "UnrealAddComponentTool",
    "UnrealCallFunctionTool",
    "UnrealCreateBlueprintClassTool",
    "UnrealDescribeObjectTool",
    "UnrealGetInfoTool",
    "UnrealSearchAssetsTool",
    "UnrealSetPropertyTool",
    "UnrealTool",
    "build_unreal_registry",
    "unreal_definitions",
]
