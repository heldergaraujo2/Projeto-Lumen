# F19 — Lumen Intelligence Lab

## Objetivo

F19 cria a camada permanente de pesquisa e coordenação de inteligência da Lumen.
Ela conecta capacidades, baselines, pesquisa, hipóteses, Intelligence Stack F17,
Model Adaptation Laboratory F18, Evolution Laboratory F13 e memória F12.

## Fluxo

CAPABILITY -> BASELINE -> RESEARCH -> HYPOTHESIS -> STACK/ADAPTATION EVIDENCE
-> FINDING -> OPPORTUNITY -> F12-F18 EXPERIMENT/CANDIDATE/BENCHMARK
-> PROMOTION -> F16 MONITORING -> NEW BASELINE

F19 é uma camada de research state e evidence coordination, não uma camada de execução.

## Contratos

- IntelligenceCapability
- IntelligenceBaseline
- IntelligenceResearch
- IntelligenceHypothesis
- IntelligenceFinding
- IntelligenceOpportunity
- IntelligenceAssessment
- IntelligenceEvidenceLedger
- LumenIntelligenceLab

## Integração

F19 registra ResearchEvidence/ResearchReport, StackEvidence F17 e AdaptationEvidence F18.
O workspace é delegado ao EvolutionLab/ModelAdaptationLab e permanece em evolution-lab/.
O ledger é bounded, rejeita evidência sem validate() e rejeita duplicatas.

## Segurança

F19 não executa modelos, ferramentas, código, browser, rede, drivers ou processos.
Não treina, não faz inferência, download ou deploy; não concede Permission, altera
Policy/Sandbox/Checkpoint/Audit, amplia Scope ou promove automaticamente.
F19 apenas cria, valida e registra estado/evidência para os gates existentes.

## Critério de conclusão

Contratos, integração F17/F18/F13, ledger, pesquisa, hipóteses, findings, oportunidades,
segurança, testes e CI devem estar verdes e documentados.