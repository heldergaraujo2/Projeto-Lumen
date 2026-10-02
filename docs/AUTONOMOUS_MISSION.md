# Lumen Autonomous Mission — F34

## Objetivo

A Lumen pode manter uma única missão persistente de alto nível. A missão é
retomada automaticamente pelo processo principal e fica aguardando o Unreal
MCP real quando o Unreal Editor estiver fechado.

O contrato da missão é:

> Receber uma missão de alto nível e desenvolver as capacidades necessárias
> para concluí-la, pesquisando, evoluindo a própria Lumen, testando,
> observando o Unreal e utilizando as ferramentas disponibilizadas pelo
> Unreal MCP.

## Um único comando

Depois de definir o caminho do projeto Unreal:

```powershell
python -m app.evolution.autonomous_mission init --goal "Torne a Lúmen capaz de desenvolver um jogo completo do zero ao produto final no Unreal Engine." --project-root "C:\CAMINHO\DO\PROJETO"
```

O comando cria apenas `data/evolution/mission.json`. A missão não depende de
uma nova conversa ou de uma nova lista de fases.

## Retomada automática

Ao iniciar `main.py`, o supervisor:

1. lê a missão persistente;
2. verifica o endpoint local `http://127.0.0.1:8000/mcp`;
3. permanece em `WAITING_UNREAL` enquanto o editor/MCP estiver indisponível;
4. quando o Unreal voltar, muda para `EVOLVING` e executa um ciclo;
5. persiste o estado após cada ciclo;
6. pausa em `BLOCKED` quando uma capacidade falha, preservando a evidência
   para a próxima tentativa.

O supervisor não cria outro projeto Unreal e não perde a missão quando o
editor é reiniciado.

## Tipos de ciclo

O planejador local pode escolher:

- `research`: pesquisa conhecimento público pela camada Web;
- `list_toolsets`: descobre os toolsets atualmente anunciados pelo Unreal MCP;
- `describe_toolset`: inspeciona as ferramentas e capacidades de um toolset específico antes de utilizá-lo;
- `evolve_code`: usa o Autonomous Evolution Loop existente, com testes,
  rollback e commit;
- `observe_unreal`: lê o Slate/Unreal MCP sem input físico;
- `unreal_call`: chama uma ferramenta anunciada por um toolset real do
  Unreal MCP;
- `done`: encerra somente quando o planejador considera a missão verificada.

## Segurança

- O cliente Unreal aceita somente HTTP loopback por padrão.
- O broker aceita somente toolsets anunciados pelo servidor conectado.
- Há orçamento de chamadas MCP por instância do broker.
- O código da Lumen continua protegido pelo checkpoint/rollback do
  Autonomous Evolution Loop.
- Mouse/teclado continuam pertencendo à camada Computer Control existente.
- O supervisor não arma o Windows driver.
- Nenhuma credencial é colocada no arquivo da missão.

## Estado persistente

`data/evolution/mission.json` contém somente identidade, objetivo, estado,
contador e mensagens de diagnóstico. Conteúdo de screenshots, secrets e
arquivos do projeto não é armazenado ali.

## Critério de conclusão

F34 não declara que um jogo completo já foi desenvolvido. Ela fecha a
infraestrutura necessária para manter uma missão única viva entre reinícios
do Unreal e para entregar ao planejador local as capacidades de pesquisa,
evolução do código e operação do Unreal MCP. A conclusão do objetivo do jogo
continua dependendo da execução real da missão no ambiente do operador.
