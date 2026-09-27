# F16 — Continuous Evolution

## Objetivo

Fechar o ciclo entre promoção e evolução contínua por observação pós-promoção,
medição de estabilidade, detecção de degradação/regressão e geração de novas
oportunidades de melhoria.

## Fluxo

PROMOTED
  -> MONITORED
  -> POST-PROMOTION OBSERVATION
  -> MEASURE
  -> STABILITY ASSESSMENT
  -> STABLE: continuar monitorando
  -> DEGRADED / REGRESSED
  -> EVOLUTION TRIGGER
  -> RESEARCH EVIDENCE
  -> IMPROVEMENT OPPORTUNITY
  -> ciclo F12-F15
  -> BENCHMARK -> SECURITY -> HUMAN APPROVAL -> PROMOTION
  -> novo ciclo

## Componentes

- MonitoringPolicy: limites de amostra, tolerância, recorrência e histórico.
- PostPromotionObservation: evidência estruturada pós-promoção.
- ContinuousEvolutionMonitor: monitora candidatos promovidos e mede estabilidade.
- StabilityAssessment: STABLE, DEGRADED, REGRESSED ou INCONCLUSIVE.
- EvolutionTrigger: proposta bounded para iniciar nova investigação.
- ContinuousEvolutionPlanner: conecta trigger a evidência de pesquisa.
- EvolutionMemory permanece como memória histórica do LES.

## Segurança

F16 é observacional/propositiva:
- não executa código ou processos;
- não faz deploy;
- não chama drivers;
- não concede permissões;
- não altera Policy, Sandbox, Checkpoint ou Audit;
- não faz rollback físico;
- não transforma degradação em promoção automática;
- triggers exigem novo ciclo F12-F15;
- pesquisas são fornecidas pelo chamador;
- mudanças de alto risco continuam exigindo aprovação humana;
- histórico possui limite configurável.

## Critério de conclusão

F16 exige contrato de monitoramento, detecção determinística, gatilho de novo
ciclo, testes de segurança/limites, suíte completa, validação F0 e continuidade
atualizada.
