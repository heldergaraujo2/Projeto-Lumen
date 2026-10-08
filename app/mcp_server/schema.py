"""Serializer ``ToolDefinition`` → schema oficial de tool MCP (Fase 3).

Converte o contrato interno do LUMEN (``app/tools/protocol.py``) para o
formato exigido pelo MCP em ``tools/list``::

    {
      "name": "read_file",
      "title": "Ler arquivo",
      "description": "...",
      "inputSchema": {"type": "object", "properties": {...}, "required": [...]},
      "annotations": {"readOnlyHint": true, "destructiveHint": false,
                      "idempotentHint": false, "openWorldHint": false}
    }

Referência: https://modelcontextprotocol.io/specification/2025-06-18/server/tools

Decisões:

- ``inputSchema`` é JSON Schema; o MCP exige ``type: "object"`` na raiz.
- ``additionalProperties: false`` é explícito porque o LUMEN **rejeita**
  parâmetros desconhecidos (``ToolDefinition.validate_parameters``). O schema
  precisa dizer a verdade sobre a fronteira, senão o LLM inventa campos e
  recebe erro em vez de orientação.
- ``annotations`` só traz hints: elas **não** concedem nada. A autoridade
  continua no ``ToolRegistry`` + permissões + sandbox/checkpoint. Um
  ``readOnlyHint: true`` afirma que a tool não muta dados, nada mais.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.tools.protocol import ParameterDefinition, ToolDefinition

#: Tipos do protocolo LUMEN → tipos JSON Schema.
_TYPE_MAP: Mapping[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}

#: Metadado opcional no ``ToolDefinition`` que dá um título legível.
TITLE_METADATA_KEY = "title"


class UnsupportedParameterTypeError(ValueError):
    """O protocolo do LUMEN ganhou um tipo que este serializer desconhece."""


def parameter_to_json_schema(parameter: ParameterDefinition) -> dict[str, Any]:
    """Converte um :class:`ParameterDefinition` em sub-schema JSON Schema."""
    json_type = _TYPE_MAP.get(parameter.type)
    if json_type is None:
        raise UnsupportedParameterTypeError(
            f"Parâmetro '{parameter.name}': tipo {parameter.type!r} não tem "
            "equivalente JSON Schema mapeado. Atualize _TYPE_MAP junto com "
            "ParameterDefinition.validate()."
        )
    schema: dict[str, Any] = {"type": json_type}
    if parameter.description:
        schema["description"] = parameter.description
    if json_type == "array":
        # O LUMEN valida apenas "é lista" (itens livres) — declarar o item
        # como aberto evita prometer ao LLM uma validação que não existe.
        schema["items"] = {}
    return schema


def tool_definition_to_mcp_schema(definition: ToolDefinition) -> dict[str, Any]:
    """Converte um :class:`ToolDefinition` no objeto tool do MCP."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in definition.parameters:
        properties[parameter.name] = parameter_to_json_schema(parameter)
        if parameter.required:
            required.append(parameter.name)

    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        input_schema["required"] = required

    # `destructive` vem do ToolDefinition (preenchido a partir de
    # FILESYSTEM_DESTRUCTIVE_TOOLS em ToolsController.tool_protocol).
    # readOnlyHint e destructiveHint são complementares na spec: uma tool
    # não-destrutiva que escreve (ex.: create_directory idempotente) ainda
    # não é readOnly.
    read_only = not definition.destructive
    annotations = {
        "readOnlyHint": read_only,
        "destructiveHint": definition.destructive,
        "idempotentHint": False,
        "openWorldHint": False,
    }

    tool: dict[str, Any] = {
        "name": definition.name,
        "description": definition.description,
        "inputSchema": input_schema,
        "annotations": annotations,
    }
    title = definition.metadata.get(TITLE_METADATA_KEY)
    if isinstance(title, str) and title.strip():
        tool["title"] = title.strip()
    return tool


def tool_definitions_to_mcp_schemas(
    definitions: tuple[ToolDefinition, ...] | list[ToolDefinition],
    *,
    allowed: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Serializa uma coleção, opcionalmente filtrando por nome.

    ``allowed=None`` **não** significa "tudo": significa "sem filtro
    adicional". Quem decide o que é exposto é o chamador (o gateway do
    servidor MCP), que por default é fail-closed.
    """
    tools = []
    for definition in definitions:
        if allowed is not None and definition.name not in allowed:
            continue
        tools.append(tool_definition_to_mcp_schema(definition))
    tools.sort(key=lambda item: item["name"])
    return tools


__all__ = [
    "TITLE_METADATA_KEY",
    "UnsupportedParameterTypeError",
    "parameter_to_json_schema",
    "tool_definition_to_mcp_schema",
    "tool_definitions_to_mcp_schemas",
]
