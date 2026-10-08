"""Ponte com o Unreal Editor pela Remote Control API (Fase 4).

Fecha o ciclo do objetivo: o agente planeja (Fase 2), o plano é aprovado
(Fase 2), os arquivos são escritos no PC do usuário (Fases 1–3) e o
resultado é aplicado dentro do **Unreal Editor aberto** — criar Blueprint,
adicionar componente, mudar propriedade, chamar função.

::

    app/research/      →  descobre COMO fazer
    app/planning/      →  decide O QUE fazer, com aprovação
    app/mcp_server/    →  expõe ao LLM
    app/unreal_bridge/ →  executa no editor          (este pacote)

Duas portas de entrada, e a diferença entre elas é o achado central da
Fase -1:

- **Remote Control API pura** (HTTP na porta 30010) — ``/remote/info``,
  ``object/call``, ``object/property``, ``object/describe``,
  ``search/assets``, ``object/thumbnail``, ``batch``, ``object/event``.
  Alcança qualquer função **chamável por Blueprint** e propriedades
  públicas/EditAnywhere. **Não cria assets** — não existe rota para isso.
- **Python Editor Script Plugin** — necessário para criar Blueprint e
  editar grafo. Exige habilitar o plugin no ``.uproject`` **e**
  ``bEnableRemotePythonExecution=True`` em
  ``Config/DefaultRemoteControl.ini``.

Transparência sobre validação: o que usa a RC API pura foi escrito contra a
referência HTTP oficial da Epic. O que executa Python **não pôde ser
validado** num Unreal real neste ambiente (não há Unreal aqui) — cada
ferramenta diz isso na própria descrição e na saída, e ``TESTE_LOCAL.md``
traz o roteiro de validação.
"""
from __future__ import annotations

from app.unreal_bridge.client import (
    ACCESS_READ,
    ACCESS_VALUES,
    ACCESS_WRITE,
    ACCESS_WRITE_TRANSACTION,
    RemoteControlClient,
    urllib_transport,
)
from app.unreal_bridge.config import (
    DEFAULT_RC_HOST,
    DEFAULT_RC_PORT,
    UnrealBridgeConfig,
    UnrealBridgeError,
    UnrealUnavailableError,
)
from app.unreal_bridge.python_script import (
    GeneratedScript,
    PythonScriptError,
    build_add_component_script,
    build_blueprint_creation_script,
    build_compile_script,
    build_save_script,
    parse_execution_result,
)
from app.unreal_bridge.tools import (
    NEEDS_MANUAL_VALIDATION,
    UNREAL_TOOLS,
    VALIDATED_AGAINST_DOC,
    UnrealCallFunctionTool,
    UnrealCreateBlueprintClassTool,
    UnrealSetPropertyTool,
    build_unreal_registry,
    unreal_definitions,
)

__all__ = [
    "ACCESS_READ",
    "ACCESS_VALUES",
    "ACCESS_WRITE",
    "ACCESS_WRITE_TRANSACTION",
    "DEFAULT_RC_HOST",
    "DEFAULT_RC_PORT",
    "GeneratedScript",
    "NEEDS_MANUAL_VALIDATION",
    "PythonScriptError",
    "RemoteControlClient",
    "UNREAL_TOOLS",
    "UnrealBridgeConfig",
    "UnrealBridgeError",
    "UnrealCallFunctionTool",
    "UnrealCreateBlueprintClassTool",
    "UnrealSetPropertyTool",
    "UnrealUnavailableError",
    "VALIDATED_AGAINST_DOC",
    "build_add_component_script",
    "build_blueprint_creation_script",
    "build_compile_script",
    "build_save_script",
    "build_unreal_registry",
    "parse_execution_result",
    "unreal_definitions",
    "urllib_transport",
]
