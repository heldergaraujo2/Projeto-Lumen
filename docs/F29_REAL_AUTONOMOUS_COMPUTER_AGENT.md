# F29 — Real Autonomous Computer Agent

## Objetivo

Fechar o ciclo controlado:

Goal → Plan → Observe → Target → Action → Verify → Recover → Replan → Success.

F29 transforma as fundações F11/F23/F25/F27/F28 em um orquestrador único, sem
criar uma nova autoridade de execução.

## Implementação

\`app/computer_control/autonomous_agent.py\` fornece:

- \`VisionComputerAgent\`;
- estados explícitos de execução;
- budgets de ciclos, recoveries e replans;
- planner estruturado que retorna \`ComputerPlan\`;
- observação via \`VisionGroundingPipeline\`;
- grounding antes da ação;
- execução exclusivamente via \`ComputerControlService\`;
- verificação pós-ação via contrato explícito;
- recovery/replan bounded;
- pausa imediata quando o serviço exige checkpoint;
- nenhum acesso direto ao driver.

## Segurança

O agente não:

- concede \`COMPUTER_CONTROL\`;
- aprova checkpoint;
- altera Policy, Scope ou Checkpoint;
- chama \`WindowsComputerControlDriver\` diretamente;
- executa uma ação sem passar pelo \`ComputerControlService\`;
- transforma confiança visual em autorização;
- amplia orçamento durante a execução;
- executa loops infinitos.

A aprovação humana permanece autoridade externa. Com \`require_checkpoint=True\`,
uma ação física produz \`WAITING_APPROVAL\` e o checkpoint pode ser decidido pelo
fluxo oficial do serviço.

## Critérios

- SPEC: este documento;
- IMPLEMENTATION: pipeline integrada;
- INTEGRATION: ComputerControlService + VisionGroundingPipeline;
- NEGATIVE/SECURITY: testes de checkpoint e budgets;
- REGRESSION: suíte completa;
- REAL ENVIRONMENT: smoke físico continua separado e somente evidência real
  pode marcar F27/F28 como validadas;
- DOCUMENTATION: este documento + estado/roadmap canônicos.


## Smoke real

O repositório fornece `scripts/f29_autonomous_computer_smoke.py` para validação
em Windows com Ollama multimodal real. O smoke exige duas confirmações explícitas:
`LUMEN_F29_PHYSICAL_CONFIRM=YES` para armar o teste e
`LUMEN_F29_APPROVE=YES` para aprovar o checkpoint de ação.

A única ação física do smoke é `MOUSE_MOVE` para o alvo grounded. Não há
clique, digitação, scroll, foco ou fechamento de janela. O checkpoint continua
sendo criado pelo `ComputerControlService` e a retomada usa o ID do checkpoint
aprovado; um mismatch de escopo ou fingerprint permanece bloqueado pelo serviço.


### Retomada de checkpoint

Quando uma ação entra em `WAITING_APPROVAL`, o agente mantém o plano associado
ao checkpoint. Uma retomada com o ID do checkpoint reutiliza exatamente a mesma
ação e expectativa antes de chamar o `ComputerControlService`; não há nova
inferência visual ou novo planejamento entre a aprovação e a execução. O serviço
continua validando permissão, política, escopo e fingerprint, portanto a
retomada não cria autoridade adicional.
