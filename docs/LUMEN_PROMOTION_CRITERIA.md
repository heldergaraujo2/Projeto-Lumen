# Critérios de Promoção da Lumen

## Gate A — Integridade

- testes relevantes executados;
- nenhum teste crítico falhou;
- imports/startup válidos;
- dependências verificadas;
- documentação coerente com código.

## Gate B — Capability Evidence

Uma capacidade só pode ser promovida quando contrato, implementação,
testes críticos, benchmark aplicável, análise de regressão e evidência
estiverem presentes.

## Gate C — Segurança

Mudanças em Permission, Policy, Sandbox, Checkpoint, Audit, secrets,
Computer Control ou autoridade do agente exigem Security Review.

Alto risco exige Human Approval Gate.

## Gate D — Performance

Quando desempenho for objetivo, registrar baseline, mesma carga, ambiente,
métricas e comparação. Não promover por opinião.

## Gate E — Reversibilidade

Toda alteração deve ter estratégia de rollback adequada. Rollback de código
não desfaz efeitos externos já produzidos.

## Gate F — Pós-promoção

Monitorar métricas, regressões, incidentes e manter desativação/rollback
quando tecnicamente possível.

## Decisões

Resultados permitidos: REJECTED, PROMOTED ou PROMOTED_WITH_MONITORING.

Nenhuma promoção deve depender somente da opinião do modelo.
