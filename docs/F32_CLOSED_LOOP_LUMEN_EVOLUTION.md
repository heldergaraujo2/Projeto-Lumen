# F32 — Closed-Loop Lumen Evolution

## Objetivo

F32 conecta o monitoramento pós-promoção F16, o ciclo de inteligência F22 e os gates de evolução F24 em um único ciclo operacional bounded:

`MONITOR → OBSERVE → ASSESS → TRIGGER → PLAN → EVOLUTION GATES → APPROVAL → PROMOTION → MONITOR → NEW CYCLE`.

## Entregas

- `app/evolution/closed_loop.py`
  - `ClosedLoopEvolution`;
  - `ClosedLoopRecord`;
  - `ClosedLoopPlan`;
  - `PersistentClosedLoopEvolution`;
  - identidade explícita do ciclo F22;
  - estados bounded;
  - deduplicação herdada do F22;
  - planos vinculados exatamente às evidências do trigger;
  - abertura explícita do gate F24;
  - transições explícitas de aprovação/promoção/monitoramento;
  - digest determinístico;
  - histórico bounded;
  - persistência atômica de metadados.
- `tests/test_closed_loop_evolution.py`
  - estabilidade;
  - degradação/regressão;
  - planejamento;
  - evidência incompatível;
  - atomicidade;
  - approval gate;
  - persistência;
  - limites;
  - ausência de superfície de execução.

## Segurança

F32 é coordenadora, não executora. Ela não:
- executa providers/modelos;
- executa ferramentas, browser, código, processos ou drivers;
- constrói artefatos;
- faz deploy;
- concede permissões;
- altera Policy, Scope, Sandbox, Checkpoint ou Audit;
- promove sem uma etapa explícita de aprovação;
- registra screenshot, secrets ou conteúdo sensível no estado persistido.

Toda mudança real continua passando pelos gates existentes F12–F24.

## Critérios de conclusão

1. implementação;
2. testes unitários/negativos;
3. integração com F22/F24;
4. persistência e digest;
5. segurança;
6. documentação e continuidade;
7. CI verde antes do merge.
