# F20 — Self-Optimizing Intelligence

## Objetivo

F20 cria a camada de otimização estratégica da inteligência da Lumen. Ela usa sinais
fornecidos pelas fases F16-F19 para comparar variantes isoladas de estratégia e
produzir uma recomendação determinística, sem alterar o runtime estável.

## Fluxo

```
F16 MONITORING
      ↓
F17 STACK EVIDENCE
      ↓
F18 ADAPTATION EVIDENCE
      ↓
F19 INTELLIGENCE RESEARCH
      ↓
OBJECTIVE → VARIANTS → EVIDENCE → ASSESSMENT
                         ↓
                  DETERMINISTIC SELECTION
                         ↓
                  HUMAN APPROVAL GATE
```

## Contratos

- `OptimizationObjective`
- `StrategyVariant`
- `OptimizationEvidence`
- `OptimizationAssessment`
- `OptimizationRecommendation`
- `OptimizationPolicy`
- `SelfOptimizingIntelligence`

A avaliação é ponderada por tamanho de amostra. A seleção é determinística e
limitada por política. Variantes precisam permanecer isoladas.

## Segurança

F20 não executa modelos, ferramentas, código, browser ou drivers.
Não treina, faz inferência, deploy, download, concede permissões, altera
Policy/Sandbox/Checkpoint/Audit, amplia Scope ou promove candidatos.
A recomendação exige evidência e mantém aprovação humana explícita.

## Integração conceitual

F20 é consumidor de evidência das fases anteriores. A execução ou promoção,
quando futuramente necessária, continua pertencendo aos componentes autorizados
F7/F12-F16. F20 não cria uma nova autoridade paralela.

## Critério de conclusão

A fase é concluída somente com contratos, limites, seleção determinística,
evidência, testes de segurança, documentação e CI verdes.
