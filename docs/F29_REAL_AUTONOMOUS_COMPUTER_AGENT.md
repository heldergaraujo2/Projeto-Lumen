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
