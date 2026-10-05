# Runtime Universal da Lúmen

## Auditoria arquitetural

A auditoria do branch `feature/web-research-agent` mostrou que a Lúmen já possui:

- Agent Core e memória persistente;
- Planner com catálogo/allowlist;
- ToolsController com permissões, workspaces, checkpoints, auditoria e verificação;
- Web Research;
- MCP/Unreal;
- Computer Control;
- OperationalBrain/CognitiveFusion;
- Autonomous Mission e Autonomous Evolution Loop.

O gargalo estava na fronteira **chat → capacidade**. O Planner nativo só consegue executar ferramentas presentes no catálogo. Pedidos legítimos que exigem uma capacidade externa ou ainda não catalogada acabam classificados como conversa ou plano inválido, em vez de serem entregues a um agente especializado.

## Componentes reutilizados

### OpenAI Agents SDK

Usado como orquestrador do Runtime Universal. Ele fornece o loop de agente, ferramentas, handoffs/roteamento e suporte a modelos compatíveis com OpenAI. Para a Lúmen, o SDK pode usar o endpoint compatível do Ollama local.

### OpenHands SDK

Usado como especialista de engenharia. Recebe tarefas de código no workspace real da Lúmen e dispõe de ferramentas de terminal/editor. A execução é permitida somente quando WRITE e TERMINAL já estão concedidos pela política da Lúmen.

### Browser Use

Usado como especialista de navegador para pesquisa Web e automação de navegador. Pesquisa exige WEB_ACCESS. Interações que aparentam alterar uma conta/aplicação exigem também COMPUTER_CONTROL.

## Fluxo novo

```
Usuário
  ↓
Planner/Tools nativos da Lúmen
  ├── capacidade conhecida → execução nativa com segurança
  └── conversa/capacidade fora do catálogo
            ↓
       Runtime Universal
            ↓
    OpenAI Agents SDK
       ├── resposta direta
       ├── Browser Use
       └── OpenHands
```

O Runtime Universal é **fallback**, não substituto da cadeia de segurança existente.

## Dependências

As dependências ficam em `requirements-agent-runtime.txt`, separadas do `requirements.txt` principal porque a versão atual do OpenAI Agents SDK requer `openai>=3`, enquanto os providers nativos atuais da Lúmen ainda usam `openai<2`.

Isso evita quebrar o runtime existente antes da validação da nova camada.

## Critério de validação

Depois da instalação, os testes devem verificar:

1. runtime opcional detectável;
2. bloqueio de automação de navegador sem COMPUTER_CONTROL;
3. bloqueio de evolução de código sem WRITE + TERMINAL;
4. execução do runtime com Ollama;
5. pesquisa via Browser Use;
6. tarefa de código via OpenHands;
7. fallback do chat para o Runtime Universal;
8. preservação da cadeia nativa de permissões/checkpoints.

Nenhuma integração é considerada concluída apenas porque a dependência instalou: a validação real precisa demonstrar uma tarefa executada e verificada.
