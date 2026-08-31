"""Contrato de ferramentas (tools) da Lumen.

A partir da 0.5 existem ferramentas concretas (filesystem — ver
:mod:`app.tools.filesystem`), sempre registradas explicitamente em um
:class:`ToolRegistry`, que **bloqueia a execução** caso a permissão
correspondente não tenha sido concedida. Ferramentas devem:

1. herdar de :class:`Tool` (resultado textual) ou de
   :class:`StructuredTool` (resultado estruturado — recomendado);
2. declarar ``name``, ``description`` e ``required_permission``;
3. ser registradas em um :class:`ToolRegistry` construído com o
   :class:`~app.security.permissions.PermissionManager`.

Nada aqui executa comandos, controla mouse/teclado ou acessa a rede —
essas capacidades continuam inexistentes.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.security.permissions import PermissionLevel, PermissionManager


class ToolError(RuntimeError):
    """Falha relacionada a uma ferramenta."""


class ToolNotFoundError(ToolError):
    """Ferramenta não registrada."""


@dataclass(frozen=True)
class ToolResult:
    """Resultado estruturado de uma ferramenta (0.5).

    - ``ok``: ``True`` quando a operação foi executada com sucesso;
      ``False`` quando foi bloqueada ou falhou (``error`` explica).
    - ``data``: metadados e dados da operação (caminhos, contagens,
      conteúdo lido, flags…). Nunca deve carregar segredos além do
      estritamente necessário ao propósito da ferramenta.
    - ``error``: mensagem amigável quando ``ok`` é ``False``.
    """

    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error}


class Tool(ABC):
    """Ferramenta executável da Lumen.

    Atributos de classe obrigatórios em cada subclasse concreta:

    - ``name``: identificador único (ex.: ``"read_file"``);
    - ``description``: descrição legível (usada em listagens e ajuda);
    - ``required_permission``: permissão mínima para executar.
    """

    # Padrão conservador: sem permissão declarada, exige o nível máximo.
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    required_permission: ClassVar[PermissionLevel] = PermissionLevel.COMPUTER_CONTROL
    #: Bases intermediárias (ex.: ``StructuredTool``) marcam ``True`` para
    #: pular a validação de metadados — só ferramentas concretas validam.
    _abstract_base: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("_abstract_base"):
            return  # base intermediária declarada como abstrata
        # Falha rápido na definição da classe: tool sem metadados é bug.
        if not cls.name or not cls.name.strip():
            raise ToolError(f"Tool {cls.__name__} precisa declarar 'name' não vazio.")
        if not cls.description or not cls.description.strip():
            raise ToolError(f"Tool {cls.__name__} precisa declarar 'description' não vazia.")
        if not isinstance(cls.required_permission, PermissionLevel):
            raise ToolError(
                f"Tool {cls.__name__}: 'required_permission' deve ser um PermissionLevel."
            )

    @abstractmethod
    def execute(self, **kwargs: Any) -> str:
        """Executa a ferramenta e devolve o resultado textual."""
        raise ToolError("Tool.execute não implementado")  # pragma: no cover


class StructuredTool(Tool):
    """Ferramenta com resultado estruturado (:class:`ToolResult`).

    Subclasses implementam :meth:`run` (devolve ``ToolResult``);
    :meth:`execute` (contrato textual da 0.1, usado pelo
    :class:`ToolRegistry`) serializa o resultado em JSON — consumidores
    podem decodificar com ``json.loads``. Falhas NÃO são lançadas como
    exceção: viram ``ToolResult(ok=False, error=...)`` estruturado.
    """

    _abstract_base = True  # base intermediária: metadados nas concretas

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        """Executa a operação e devolve o resultado estruturado."""
        raise ToolError("StructuredTool.run não implementado")  # pragma: no cover

    def execute(self, **kwargs: Any) -> str:
        return json.dumps(self.run(**kwargs).to_dict(), ensure_ascii=False)


class ToolRegistry:
    """Registro de ferramentas + porteiro de permissões.

    Toda execução passa por :meth:`execute`, que consulta o
    :class:`~app.security.permissions.PermissionManager` antes de rodar
    qualquer código da ferramenta.
    """

    def __init__(self, permissions: PermissionManager | None = None) -> None:
        self._permissions = permissions
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Registra uma ferramenta (nome duplicado é erro)."""
        if tool.name in self._tools:
            raise ToolError(f"Já existe uma ferramenta registrada com o nome {tool.name!r}.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """Retorna a ferramenta pelo nome.

        Raises:
            ToolNotFoundError: se não estiver registrada.
        """
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"Ferramenta não registrada: {name!r}") from exc

    def list_tools(self) -> list[dict[str, str]]:
        """Metadados de todas as ferramentas registradas."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "required_permission": tool.required_permission.name,
            }
            for tool in self._tools.values()
        ]

    def execute(self, name: str, **kwargs: Any) -> str:
        """Executa uma ferramenta, se houver permissão.

        Raises:
            ToolNotFoundError: ferramenta inexistente.
            PermissionDeniedError: permissão insuficiente.
        """
        tool = self.get(name)
        if self._permissions is not None:
            self._permissions.require(tool.required_permission)
        return tool.execute(**kwargs)
