# Lúmen — UI Operacional

## Estado

A interface desktop da Lúmen possui uma janela principal de conversa e um **Painel Operacional** acessível pela própria aplicação.

O painel é dividido nas seguintes abas:

1. Runtime
2. Computer Control
3. Web Research
4. Unreal Integration
5. Ollama
6. Unreal MCP
7. Ferramentas / Aprovações
8. Configurações

## Responsabilidades

- **Runtime:** diagnóstico dos componentes descobertos no processo.
- **Computer Control:** estado da capacidade e das permissões/sessões relevantes.
- **Web Research:** estado do acesso web; a política de segurança de rede continua ativa.
- **Unreal Integration:** estado da integração e do plano Unreal pendente.
- **Ollama:** estado detectado do provider/runtime local.
- **Unreal MCP:** estado detectado do endpoint MCP.
- **Ferramentas / Aprovações:** acesso à superfície completa de workspaces, permissões, checkpoints, terminal, automação e auditoria.
- **Configurações:** acesso à configuração do provider/modelo e credenciais.

## Segurança

O Painel Operacional é uma camada de apresentação. Diagnóstico não concede permissão, não cria escopo, não arma o driver e não executa ações físicas.

As ações operacionais continuam subordinadas à cadeia existente:

**Permissão → Policy → Scope → Checkpoint → ToolRegistry → Plano → ComputerControlService → Driver → Auditoria → Verificação.**

O acesso web geral não remove as validações de segurança da política de rede.

## Inicialização

Lumen.pyw continua sendo a entrada gráfica para Windows. O runtime é descoberto durante a inicialização e os estados são apresentados no painel.
O painel não inicia automaticamente Ollama, MCP ou outros processos externos.
