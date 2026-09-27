# F22 — Continuous Intelligence Evolution

## Objetivo

Fechar o ciclo contínuo de evolução da inteligência da Lumen, conectando observação,
baseline, detecção de degradação, trigger, plano de pesquisa/benchmark e retorno aos
gates F12–F21.

## Fluxo

OBSERVE → BASELINE → ASSESS → DETECT → TRIGGER → PLAN → RESEARCH/ADAPT/STACK →
BENCHMARK → SECURITY → HUMAN APPROVAL → PROMOTION/MONITORING → NEW BASELINE

## Contratos

- IntelligenceObservation
- IntelligenceCycle
- IntelligenceTrigger
- ContinuousIntelligencePlan
- ContinuousIntelligenceEvolution

Os IDs são determinísticos dentro da instância e o digest do estado usa SHA-256.

## Segurança

F22 é uma camada de coordenação e planejamento. Ela não executa modelos, código,
processos, browser, rede, ferramentas ou drivers. Não concede permissões, altera
Policy/Sandbox/Checkpoint/Audit, amplia Scope, faz deploy ou promove automaticamente.

Triggers apenas abrem um novo ciclo. Plans permanecem isolados e exigem aprovação
humana. A execução real continua nos gates existentes.

## Limites

Observações têm sample mínimo e histórico bounded. Um ciclo só entra em TRIGGERED
quando a métrica cai abaixo do baseline além da tolerância declarada. Evidência de
outro capability ou baseline é rejeitada.

## Critério de conclusão

Implementação, testes de invariantes, regressão, limites, digest, isolamento,
ausência de superfície de execução, CI e documentação devem estar verdes.
