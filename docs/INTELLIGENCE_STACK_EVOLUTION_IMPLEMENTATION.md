# F17 — Intelligence Stack Evolution

## Objetivo

Evoluir a pilha de inteligência da Lumen sem confundir Provider, Model e Lumen.

## Contratos

- ProviderProfile representa o fornecedor/adaptador.
- ModelProfile declara capacidades, contexto, custo e confiabilidade.
- StackRequest declara a necessidade de inteligência.
- IntelligenceStack mantém registro e roteamento determinístico.
- StackEvidence representa evidência fornecida externamente.
- StackEvaluator compara evidências compatíveis.
- StackAdaptation representa uma proposta isolada.
- IntelligenceStackEvolution é a fronteira de proposta e evidência.

## Roteamento

StackRequest é filtrado por capacidade declarada, confiabilidade, custo e contexto.
O desempate é determinístico. O router apenas escolhe uma declaração compatível:
ele não chama o provider e não executa o modelo.

## Evolução

MEASURE -> EVIDENCE -> PROPOSE ADAPTATION -> ISOLATE -> F12-F16.

Nenhuma adaptação altera a pilha estável diretamente.

## Segurança

F17 não:
- executa providers;
- chama rede;
- executa ferramentas;
- altera Permission, Policy, Sandbox, Checkpoint ou Audit;
- faz deploy;
- promove automaticamente;
- aceita adaptação sem evidência;
- aceita adaptação fora de isolamento.

Provider != Model != Lumen permanece um contrato arquitetural explícito.
