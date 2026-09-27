# F12 — Evolution Foundation

## Status

**Implementação: concluída na branch F12. Validação CI: pendente até o pipeline finalizar.**

F12 estabelece os contratos mínimos do **Lumen Evolution System (LES)**. Esta fase não executa experimentos nem altera o runtime estável.

## Componentes

- **Capability Registry** — registra capacidades e suas medições.
- **Capability Measurement** — baseline quantitativo com métrica, amostra e evidência.
- **Self-Diagnostics** — diagnóstico estruturado a partir da capacidade e baseline atual.
- **Improvement Planner** — transforma uma limitação mensurada em plano de melhoria.
- **Hypothesis Manager** — registra hipótese, racional e métrica esperada.
- **Experiment Manager** — máquina de estados bounded para experimentos.
- **Candidate Registry** — identidade e estado de candidatos.
- **Benchmark Engine** — comparação candidato versus baseline.
- **Regression Detector** — detecta regressões além da tolerância declarada.
- **Safety Validator** — bloqueia componentes protegidos e exige aprovação humana para alto risco.
- **Promotion Manager** — gate explícito; aprovação não é inferida por benchmark.
- **Rollback Manager** — registra referência da versão anterior e motivo.
- **Evolution Memory** — preserva sucessos e falhas como memória de engenharia.

## Identidade

Cada evolução recebe ID monotônico por instância:

`EVOLUTION-000001`, `EVOLUTION-000002`, ...

O registro de evolução suporta:

- problema;
- hipótese;
- baseline;
- fontes;
- alterações;
- testes;
- métricas;
- regressões;
- decisão;
- evidências;
- resultado;
- estado.

## Pipeline fundacional

```text
CAPABILITY
   ↓
MEASURE BASELINE
   ↓
DIAGNOSE
   ↓
IMPROVEMENT PLAN
   ↓
HYPOTHESIS
   ↓
EXPERIMENT
   ↓
CANDIDATE
   ↓
BENCHMARK
   ↓
REGRESSION CHECK
   ↓
SECURITY REVIEW
   ↓
PROMOTION GATE
   ↓
PROMOTE / REJECT
   ↓
MONITOR / ROLLBACK
   ↓
EVOLUTION MEMORY
```

F12 define os contratos; a execução efetiva do laboratório pertence às fases posteriores.

## Segurança

Os seguintes componentes são tratados como fronteira protegida:

- PermissionManager;
- Policy Engine;
- Sandbox;
- Checkpoint;
- Audit;
- Promotion Rules;
- Rollback;
- Secrets;
- Security Core.

Alterações de alto risco exigem aprovação humana explícita. O F12 não concede autoridade, não chama drivers, não amplia escopo e não altera políticas de segurança.

## Estados de evolução

`PROPOSED → RESEARCHING → HYPOTHESIS → PLANNED → EXPERIMENTAL → BUILDING → TESTING → BENCHMARKING → SECURITY_REVIEW → PROMOTION_PENDING → APPROVED → PROMOTED → MONITORED`

Falhas podem seguir para `REJECTED`; uma evolução promovida pode seguir para `ROLLED_BACK`.

## Limites desta fase

F12 não promete:

- execução automática de experimentos;
- criação de workspaces reais;
- alteração automática de código;
- benchmark de modelos reais;
- promoção automática;
- rollback físico automático.

Essas capacidades dependem das fases seguintes e continuam sujeitas à arquitetura de segurança da Lumen.
