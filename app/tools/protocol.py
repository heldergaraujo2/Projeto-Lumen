"""Tool / Agent Protocol da Lumen (F2).

Contrato independente entre intenção do Agent/LLM e execução de Tools.
O protocolo valida envelope, ferramenta, parâmetros e tipos antes da
execução. Ele não concede permissões e não conhece filesystem/Windows:
a autoridade de execução continua no ToolRegistry + PermissionManager +
sandbox/checkpoint.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.tools.base import ToolRegistry


class ToolProtocolError(ValueError):
    """Violação do contrato Tool / Agent."""


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    type: str
    required: bool = False
    description: str = ""

    def validate(self, value: Any) -> str | None:
        if self.type == "string":
            if not isinstance(value, str) or not value.strip():
                return f"parâmetro '{self.name}' deve ser texto não vazio"
        elif self.type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return f"parâmetro '{self.name}' deve ser inteiro"
        elif self.type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return f"parâmetro '{self.name}' deve ser número"
        elif self.type == "boolean":
            if not isinstance(value, bool):
                return f"parâmetro '{self.name}' deve ser booleano"
        elif self.type == "array":
            if not isinstance(value, list):
                return f"parâmetro '{self.name}' deve ser lista"
        elif self.type == "object":
            if not isinstance(value, dict):
                return f"parâmetro '{self.name}' deve ser objeto"
        else:
            return f"tipo de parâmetro não suportado: {self.type!r}"
        return None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: tuple[ParameterDefinition, ...] = ()
    destructive: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ToolProtocolError("ToolDefinition exige nome não vazio.")
        if not self.description.strip():
            raise ToolProtocolError(f"ToolDefinition '{self.name}' exige descrição.")
        names = [p.name for p in self.parameters]
        if len(names) != len(set(names)):
            raise ToolProtocolError(f"ToolDefinition '{self.name}' possui parâmetros duplicados.")

    def validate_parameters(self, parameters: Mapping[str, Any]) -> None:
        if not isinstance(parameters, Mapping):
            raise ToolProtocolError(f"parâmetros de '{self.name}' devem ser um objeto.")
        specs = {p.name: p for p in self.parameters}
        unknown = sorted(set(parameters) - set(specs))
        if unknown:
            raise ToolProtocolError(f"parâmetros desconhecidos para '{self.name}': {', '.join(unknown)}")
        for spec in self.parameters:
            if spec.required and spec.name not in parameters:
                raise ToolProtocolError(f"parâmetro obrigatório ausente em '{self.name}': '{spec.name}'")
            if spec.name in parameters:
                error = spec.validate(parameters[spec.name])
                if error:
                    raise ToolProtocolError(error)


@dataclass(frozen=True)
class ToolCall:
    """Intenção estruturada, nunca uma instrução executável por si só."""
    tool: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    call_id: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.tool, str) or not self.tool.strip():
            raise ToolProtocolError("ToolCall exige tool não vazio.")
        if not isinstance(self.parameters, Mapping):
            raise ToolProtocolError("ToolCall.parameters deve ser um objeto.")
        if self.call_id and not isinstance(self.call_id, str):
            raise ToolProtocolError("ToolCall.call_id deve ser texto.")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToolCall":
        if not isinstance(payload, Mapping):
            raise ToolProtocolError("ToolCall deve ser um objeto.")
        allowed = {"tool", "parameters", "call_id", "reason"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ToolProtocolError(f"campos desconhecidos no ToolCall: {', '.join(unknown)}")
        return cls(tool=payload.get("tool", ""), parameters=payload.get("parameters") or {},
                   call_id=payload.get("call_id", ""), reason=payload.get("reason", ""))

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "parameters": dict(self.parameters),
                "call_id": self.call_id, "reason": self.reason}


@dataclass(frozen=True)
class ToolExecutionResult:
    """Envelope estável devolvido ao Agent após a tentativa de execução."""
    call_id: str
    tool: str
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"call_id": self.call_id, "tool": self.tool, "ok": self.ok,
                "data": dict(self.data), "error": self.error}


class ToolProtocol:
    """Validador + executor de ToolCalls através de uma ToolRegistry."""
    def __init__(self, registry: ToolRegistry, definitions: Mapping[str, ToolDefinition]):
        self._registry = registry
        self._definitions = dict(definitions)

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._definitions.values())

    def validate(self, call: ToolCall) -> ToolDefinition:
        definition = self._definitions.get(call.tool)
        if definition is None:
            raise ToolProtocolError(f"ferramenta '{call.tool}' não está no contrato permitido.")
        definition.validate_parameters(call.parameters)
        self._registry.get(call.tool)
        return definition

    def execute(self, call: ToolCall) -> ToolExecutionResult:
        self.validate(call)
        try:
            raw = self._registry.execute(call.tool, **dict(call.parameters))
        except Exception as exc:
            return ToolExecutionResult(call_id=call.call_id, tool=call.tool, ok=False, error=str(exc))
        try:
            import json
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            return ToolExecutionResult(call_id=call.call_id, tool=call.tool, ok=True, data={"result": raw})
        if isinstance(decoded, dict) and "ok" in decoded:
            return ToolExecutionResult(call_id=call.call_id, tool=call.tool, ok=bool(decoded.get("ok")),
                                       data=dict(decoded.get("data") or {}), error=decoded.get("error"))
        return ToolExecutionResult(call_id=call.call_id, tool=call.tool, ok=True, data={"result": decoded})