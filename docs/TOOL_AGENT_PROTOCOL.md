# Lumen — F2 Tool / Agent Protocol

## Objetivo

Separar **intenção do Agent**, **contrato da ferramenta** e **execução**.

O modelo/Agent produz um ToolCall; ele não recebe acesso direto ao driver
nem à implementação da ferramenta.

## Contrato

    Agent / LLM
       |
       v
    ToolCall { tool, parameters, call_id, reason }
       |
       v
    ToolProtocol
       |- allowlist/definition
       |- campos desconhecidos
       |- parâmetros obrigatórios
       |- tipos
       '- ferramenta realmente registrada
       |
       v
    ToolRegistry
       |- PermissionManager
       |- Workspace/Sandbox
       |- Checkpoint
       '- Tool
       |
       v
    ToolExecutionResult
       { call_id, tool, ok, data, error }

## Regra de autoridade

O protocolo não concede nenhuma permissão e não substitui os gates
existentes. Uma chamada válida continua sujeita à cadeia de segurança.

A validação ocorre antes da execução; chamada desconhecida ou malformada
falha sem alcançar a Tool.

## Limites

O protocolo não permite ao modelo criar ou registrar Tools. Registro
continua sendo responsabilidade do código confiável.

## Validação

A suíte específica cobre round-trip, allowlist, parâmetros, tipos,
resultado, falha e autoridade de permissão. A suíte global deve continuar
sendo executada antes de marcar F2 como concluída.
