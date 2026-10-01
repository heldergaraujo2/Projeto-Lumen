# LUMEN — ROADMAP E CONTINUIDADE OFICIAL

**Atualização:** 2026-09-30  
**Branch de trabalho oficial:** `feature/web-research-agent`  
**Fonte de verdade:** este documento + código/testes do repositório GitHub.

> Este é o único documento canônico de roadmap e continuidade. Os antigos `docs/ROADMAP.md` e `docs/LUMEN_CONTINUITY_PHASES.md` foram consolidados aqui e serão removidos após esta migração.

## 1. ESTADO CANÔNICO

| Fase | Nome | Estado |
|---|---|---|
| F0–F18 | Fundamentos, Agent, Computer Intelligence e Evolution | 🟩 CONCLUÍDAS |
| F19 | Lumen Intelligence Lab | 🟩 CONCLUÍDA — revisão sem defeito estrutural |
| F20 | Self-Optimizing Intelligence | 🟩 CORRIGIDA E VALIDADA |
| F21 | Provider Independence | 🟩 CORRIGIDA E VALIDADA |
| F22 | Continuous Intelligence Evolution | 🟩 CORRIGIDA E VALIDADA |
| F23 | Runtime Integration & State Machine Hardening | 🟩 CONCLUÍDA |
| F24 | Evolution Runtime Orchestrator | 🟩 CONCLUÍDA |
| F25 | Provider Runtime Independence | 🟩 CONCLUÍDA |
| F26 | Learning Runtime & Continuous Knowledge | 🟩 CONCLUÍDA |
| F27 | Real Windows Computer Validation | 🟩 VALIDADA EM MÁQUINA REAL |
| F28 | Real Vision + Grounding | 🟩 VALIDADA EM MÁQUINA REAL |
| F29 | Real Autonomous Computer Agent | 🟩 VALIDADA EM MÁQUINA REAL |
| F30 | Unreal Real Integration | 🟩 VALIDADA EM AMBIENTE REAL — clique físico controlado + verificação MCP/Slate |
| F31 | Experience & Workflow Intelligence | 🟩 IMPLEMENTAÇÃO + E2E CONCLUÍDOS |
| F32 | Closed-Loop Lumen Evolution | 🟩 IMPLEMENTAÇÃO/CI CONCLUÍDAS — E2E recomendado pendente |

## F32 — CLOSED-LOOP LUMEN EVOLUTION

Implementada em `app/evolution/closed_loop.py`.

Ciclo oficial:
`MONITOR → OBSERVE → ASSESS → TRIGGER → PLAN → EVOLUTION GATES → APPROVAL → PROMOTION → MONITOR → NEW CYCLE`.

Entregas:
- ClosedLoopEvolution e estados bounded;
- vínculo explícito com o ciclo F22;
- planos vinculados exatamente às evidências do trigger;
- abertura explícita do gate F24;
- estados explícitos de WAITING_EVIDENCE, WAITING_APPROVAL, PROMOTED e MONITORED;
- PersistentClosedLoopEvolution;
- digest determinístico;
- histórico bounded;
- testes dedicados em `tests/test_closed_loop_evolution.py`;
- documentação em `docs/F32_CLOSED_LOOP_LUMEN_EVOLUTION.md`.

A camada permanece deliberativa/evidencial. Não executa providers, ferramentas, código, processos, browser, drivers, builds ou deploy; não concede permissões; não bypassa Policy/Scope/Sandbox/Checkpoint/Audit; promoção continua dependente de aprovação humana explícita.

## 2. F23 — RUNTIME INTEGRATION & STATE MACHINE HARDENING

F23 é a fase oficial que corrige e integra as lacunas encontradas na auditoria de F19–F22.

### F20
- maximização/minimização agora têm semântica consistente em delta e threshold;
- `OptimizationObjective.weight` participa explicitamente da avaliação;
- seleção continua determinística;
- nenhuma execução ou promoção é realizada;
- devem existir testes de fronteira para maximize/minimize.

### F21
- requisitos declarados têm resultado explícito por compatibilidade;
- CAPABILITY, RELIABILITY, CONTEXT e COST são avaliados;
- LOCAL_AVAILABILITY só é obrigatório quando declarado;
- FAILOVER exige pelo menos dois provedores compatíveis quando declarado;
- fallback continua sendo plano declarativo, não failover runtime;
- digest registra requisitos e resultados;
- nenhuma chamada real a provider ocorre nesta camada.

### F22
- identidade de observação é imutável;
- mesmo `observation_id` com conteúdo diferente é rejeitado;
- observações arquivadas continuam resolvíveis mesmo após o limite de histórico ativo;
- ciclos não aceitam nova observação depois de sair de OBSERVED;
- transições são restritas;
- trigger e plan são one-shot;
- ciclo pode ser fechado explicitamente.

### F19
A auditoria não encontrou defeito estrutural que exigisse alteração de código. A camada permanece deliberativa/evidencial e sem autoridade de execução.

### Gate de ambiente
O detector de `app/validation/environment.py` permanece como artefato fail-closed. Detectar Windows/display/sessão não significa que mouse, teclado, UI Automation ou Unreal foram fisicamente validados.

### Critérios de conclusão
- testes F19–F23 verdes;
- regressão completa verde;
- negative/security tests verdes;
- documentação atualizada;
- CI registrada;
- nenhum PASS físico Windows/Unreal inferido de CI Linux.

## 3. EVIDÊNCIA FINAL F23

- Suíte completa: **1342 passed / 1 skipped / 0 failed**.
- Lumen F0 Validation: **success**.
- Lumen F23 Validation: **success**.
- Compile: **success**.
- Correções verificadas em F20, F21 e F22.
- Validação física Windows/Unreal continua separada e não é declarada por esta CI.

## 4. EVIDÊNCIA FINAL F24

- Implementação: `app/evolution/orchestrator.py`.
- Testes dedicados: `tests/test_evolution_runtime_orchestrator.py`.
- Documentação: `docs/F24_EVOLUTION_RUNTIME_ORCHESTRATOR.md`.
- Suíte completa: **1347 passed / 1 skipped / 0 failed**.
- Lumen Tests: **success**.
- Lumen F0 Validation: **success**.
- Lumen F23 Validation: **success**.
- Compile: **success**.
- O F24 não executa providers, ferramentas, processos, builds, drivers, browser, deploy ou promoção automática.
- Aprovação humana continua obrigatória antes de promoção.
- Validação física Windows/Unreal permanece separada.

## 5. F25–F32

### F24 — Evolution Runtime Orchestrator
Coordenar `detect → investigate → research → hypothesis → experiment request → benchmark → security → approval → promotion request → monitoring`, sem bypass de gates.

### F25 — Provider Runtime Independence
Fallback real, falha de provider, normalização de contexto, verificação, custo, auditoria e recuperação.

### F27 — Real Windows Computer Validation
UIA/Win32, foco, janelas, controles, menus, diálogos, mouse, teclado e cadeia Permission → Policy → Scope → Checkpoint → Driver → Audit → Observation → Verification.

### F28 — Real Vision + Grounding
`Screenshot → Vision Provider → Elements → Target → Confidence → Grounding → Action Candidate`, priorizando structured-first.

### F29 — Real Autonomous Computer Agent
`Goal → Plan → Observe → Target → Action → Verify → Recover → Replan → Success`.

### F30 — Unreal Real Integration
Descoberta do projeto, Editor, Content Browser/Slate, grounding e execução física controlada pelo ComputerControlService. **Validação real aprovada em 2026-09-30** com AgeOfAether, UE 5.8, MCP/Slate, checkpoint, clique físico e verificação pós-ação. Não reabrir F30.

### F31 — Experience & Workflow Intelligence
`observe → understand → record → generalize → store → reuse → adapt → verify`.

Implementado em `app/experience/intelligence.py`:
- ExperienceTrace/Event e store persistente bounded;
- generalização determinística somente de experiências verificadas;
- abstração de parâmetros divergentes em variáveis;
- PersistentWorkflowRegistry para definições + evidências;
- reuse somente após evidência verificada;
- adaptação somente com bindings declarados;
- redaction de segredos antes da persistência;
- integração direta com F10 WorkflowLearner/Matcher e F26 Learning Runtime;
- testes dedicados em `tests/test_experience_workflow_intelligence.py`;
- documentação em `docs/F31_EXPERIENCE_WORKFLOW_INTELLIGENCE.md`.

A camada permanece sem autoridade de execução e preserva Permission/Policy/Scope/Checkpoint/Sandbox/Driver/Audit/Human Approval.

### F32 — Closed-Loop Lumen Evolution
`real computer → observation → experience → metrics → diagnosis → research → hypothesis → experiment → build → benchmark → security → approval → promotion → runtime → monitoring → new observation`.

## 5.1 F26 — LEARNING RUNTIME & CONTINUOUS KNOWLEDGE — 🟩 CONCLUÍDA

Implementado:
- `app/learning/runtime.py`: LearningStore, LearningGoal, KnowledgeItem, Experience, Strategy e LearningRuntime;
- aprendizagem explícita por objetivo;
- pipeline pesquisa → candidato → prática → verificação → consolidação;
- aprendizagem automática a partir de resultados de uso;
- memória persistente JSON atômica e bounded;
- recall determinístico de conhecimento verificado;
- redaction de segredos antes da persistência;
- conhecimento não verificado fica fora do recall padrão;
- callbacks explícitos para integrar provider local, pesquisa, prática e verificação sem bypass de segurança;
- testes dedicados em `tests/test_learning_runtime.py`;
- documentação em `docs/F26_LEARNING_RUNTIME.md`.

Arquitetura: Ollama continua sendo provider local; o aprendizado pertence à Lumen e persiste entre sessões. O runtime não executa código, ferramentas, browser, drivers, rede nem concede permissões.

Validação física não se aplica ao núcleo persistente. A integração real com Windows/Computer Control permanece na F27.

## 5.2 F27 — REAL WINDOWS COMPUTER VALIDATION — 🟩 VALIDADA EM MÁQUINA REAL

Entregas:
- driver nativo em app/computer_control/windows_driver.py;
- mouse, teclado, foco de janela e screenshot no Windows;
- arming explícito e fail-closed;
- testes dedicados em tests/test_f27_windows_driver.py;
- smoke runner em scripts/f27_windows_smoke.py;
- CI Windows em .github/workflows/windows-validation.yml;
- exportação pública do driver;
- documentação em docs/F27_REAL_WINDOWS_VALIDATION.md.

Critérios:
- SPEC: documentação da fase;
- IMPLEMENTATION: driver nativo entregue;
- INTEGRATION: driver compatível com o contrato ComputerControlDriver;
- NEGATIVE/SECURITY: input bloqueado sem arming e Windows obrigatório;
- REGRESSION: suíte existente deve permanecer verde;
- CI: Windows deve executar compileall + pytest.

Evidência real:
- screenshot real: PASS (3840x1125);
- movimento real do mouse: PASS;
- digitação real de marcador: PASS;
- entrada física só foi armada explicitamente durante o smoke e o teste não executou clique destrutivo.
- evidência detalhada registrada no fluxo de validação F27.

## 5.3 F28 — REAL VISION + GROUNDING — 🟩 VALIDADA EM MÁQUINA REAL

Entregas:
- `VisionGroundingPipeline`;
- screenshot/request → vision observation → grounding → target candidate;
- reutilização do `OllamaVisionProvider` multimodal;
- validação de limites, confiança, bounding boxes e região autorizada;
- resolução structured-first;
- nenhuma execução física pela pipeline;
- testes dedicados e documentação.

Evidência real:
- screenshot real: PASS (3840x1125);
- provider real local: `ollama:qwen3-vl:2b-instruct`;
- elementos retornados: 1;
- target grounded: PASS (`PowerShell`, confidence=0.990);
- entrada física: DISARMED;
- testes automatizados do provider: 17 passed;
- testes automatizados de grounding: 5 passed;
- regressão integrada Computer Control + Vision: 50 passed.


## 5.2 F25 — PROVIDER RUNTIME INDEPENDENCE — 🟩 CONCLUÍDA

F25 transforma a independência declarativa de F21 em execução runtime real.

Entregas:
- ProviderRuntime em app/ai/provider_runtime.py;
- integração com o contrato AIProvider existente;
- reutilização do OllamaProvider existente como provider local oficial;
- seleção determinística por preferência, custo, confiabilidade e contexto;
- filtro de capabilities, reliability, custo, contexto e enabled;
- fallback real entre providers compatíveis;
- retry bounded somente para RETRYABLE_ERRORS;
- falha de autenticação não repete o mesmo provider;
- provider incompatível/desabilitado não é chamado;
- autorização explícita antes de executar;
- hook de autorização por provider;
- registro de todas as tentativas;
- resposta normalizada em AIResponse;
- falha fail-closed sem provider compatível;
- testes negativos e de segurança em tests/test_provider_runtime.py;
- documentação em docs/F25_PROVIDER_RUNTIME_INDEPENDENCE.md.

Validação final:
- compileall: SUCCESS;
- Lumen Tests: **1366 passed / 1 skipped / 0 failed**;
- Lumen F0 Validation: SUCCESS;
- Lumen F23 Validation: SUCCESS;
- implementação e testes dedicados adicionados ao repositório;
- F25 não duplica nem substitui o OllamaProvider;
- F25 não concede Permission, altera Policy/Sandbox/Checkpoint/Audit, executa tools/drivers/browser/processos ou promove automaticamente;
- validação física do daemon Ollama/Windows continua separada e não é inferida da CI Linux.

## 5.4 F29 — REAL AUTONOMOUS COMPUTER AGENT — 🟩 VALIDADA EM MÁQUINA REAL

Implementado:
- Goal → Plan → Observe → Target → Action → Verify → Recover → Replan;
- VisionComputerAgent;
- budgets bounded;
- integração com VisionGroundingPipeline e ComputerControlService;
- pausa segura em checkpoint;
- testes dedicados e documentação.

Evidência real:
- screenshot real: PASS (3840x1125);
- provider local real: `ollama:qwen3-vl:2b-instruct`;
- checkpoint criado: `CC-CP-000001`;
- retomada do checkpoint: PASS;
- estado final: `completed`;
- ciclos: 1; replans: 0; recoveries: 0;
- ação física: `MOUSE_MOVE` somente;
- clique, digitação, scroll e foco: não executados;
- fluxo comprovado: Goal → Plan → Observe → Target → Checkpoint → Action → Verify → Success.\n\n## PRÓXIMA CONTINUIDADE — APÓS F30

F30 está encerrada. A próxima sequência de validação é:
1. F31 E2E recomendado: workflow real → registro → persistência → reinício → recall → reuse/adaptação controlada;
2. F32 E2E recomendado: evidência real → trigger → plan → gates → approval → promotion/monitoring, sem execução direta;
3. teste integrado final;
4. auditoria final e fechamento documental.

Não criar novo gate físico artificial para F31/F32 e não repetir F30.

## 6. CRITÉRIO UNIVERSAL DE CONCLUSÃO

Uma fase só pode ser 🟩 com:
1. SPEC;
2. IMPLEMENTATION;
3. INTEGRATION;
4. NEGATIVE TESTS;
5. SECURITY TESTS;
6. REGRESSION;
7. REAL ENVIRONMENT VALIDATION quando aplicável;
8. DOCUMENTATION;
9. EVIDENCE.

CI verde não prova Windows físico, mouse, teclado, UI Automation ou Unreal.

## 7. SEGURANÇA

A evolução nunca pode remover ou enfraquecer sem aprovação humana explícita:
- PermissionManager;
- Policy Engine;
- Sandbox;
- Checkpoint;
- Audit;
- Rollback;
- Promotion Rules;
- secrets handling;
- authority limits;
- Evolution Laboratory isolation;
- Human Approval Gates.

Cadeia operacional:
`Goal → Planner/Agent → Tool/Computer Action → Permission → Policy → Scope → Checkpoint → Sandbox/Driver → Audit → Verification → Recovery/Regression`

## 8. CONTINUIDADE

Antes de implementar:
1. atualizar clone;
2. ler este documento e `LUMEN_STATE.md`;
3. verificar branch/commit;
4. verificar testes/CI;
5. localizar a próxima fase;
6. não inventar fases;
7. alterar sempre a Lumen existente;
8. preservar segurança;
9. registrar evidência antes de declarar conclusão.

**Regra obrigatória:** NÃO CRIE OUTRA LUMEN. ALTERE SEMPRE A LUMEN EXISTENTE.

## 10. ARQUIVO HISTÓRICO CONSOLIDADO — CONTINUIDADE ANTERIOR

# LUMEN — CONTINUIDADE OFICIAL DO PROJETO

**Data de atualização:** 2026-09-27  
**Branch oficial:** `master`  
**Fonte de verdade:** GitHub + `LUMEN_STATE.md` + este documento  
**Estado global:** 🟩 **F0–F22 CONCLUÍDAS**

> Este arquivo é o estado operacional consolidado. Snapshots históricos antigos não devem ser mantidos aqui quando contradizem o estado atual. Evidências históricas detalhadas permanecem no GitHub, changelog e documentação específica de cada fase.

---

# 1. ESTADO OFICIAL ATUAL

| Fase | Nome | Estado |
|---|---|---|
| F0 | Baseline / Auditoria / Contratos | 🟩 CONCLUÍDA |
| F1 | Local Provider / Ollama | 🟩 CONCLUÍDA |
| F2 | Tool / Agent Protocol | 🟩 CONCLUÍDA |
| F3 | Computer Intelligence | 🟩 CONCLUÍDA |
| F4 | Windows Native Intelligence | 🟩 CONCLUÍDA |
| F5 | Vision Provider | 🟩 CONCLUÍDA |
| F6 | Grounding Engine | 🟩 CONCLUÍDA |
| F7 | Secure Computer Control | 🟩 CONCLUÍDA |
| F8 | Verification + Recovery + Regression | 🟩 CONCLUÍDA |
| F9 | Unreal Engine Agent | 🟩 CONCLUÍDA |
| F10 | Workflow Learning | 🟩 CONCLUÍDA |
| F11 | Autonomous Multi-Step Agent | 🟩 CONCLUÍDA |
| F12 | Evolution Foundation | 🟩 CONCLUÍDA |
| F13 | Evolution Laboratory | 🟩 CONCLUÍDA |
| F14 | Self-Diagnostics + Research | 🟩 CONCLUÍDA |
| F15 | Candidate Build + Benchmark + Promotion | 🟩 CONCLUÍDA |
| F16 | Continuous Evolution | 🟩 CONCLUÍDA |
| F17 | Intelligence Stack Evolution | 🟩 CONCLUÍDA |
| F18 | Model Adaptation Laboratory | 🟩 CONCLUÍDA |
| F19 | Lumen Intelligence Lab | 🟩 CONCLUÍDA |
| F20 | Self-Optimizing Intelligence | 🟩 CONCLUÍDA |
| F21 | Provider Independence | 🟩 CONCLUÍDA |
| F22 | Continuous Intelligence Evolution | 🟩 CONCLUÍDA |

**Não existe fase F23 definida neste roadmap.**  
A próxima evolução do projeto deve ser definida por uma nova decisão arquitetural antes de qualquer implementação.

---

# 2. EVIDÊNCIA FINAL POR BLOCO

## F0–F11 — COMPUTER INTELLIGENCE / AGENT

As fases F0–F11 estabeleceram a fundação de Agent, Computer Intelligence, execução segura, Unreal, aprendizado de workflows e autonomia multi-etapas.

Principais capacidades acumuladas:

- percepção e representação determinística de estado;
- grounding structured-first;
- Windows Native/UI Automation;
- Vision Provider desacoplado;
- Computer Control protegido;
- Permission / Policy / Scope / Checkpoint / Driver / Audit;
- Verification / Recovery / Regression;
- Unreal Engine Agent;
- Workflow Learning;
- Autonomous Multi-Step Agent.

Validações históricas relevantes incluem:

- F3: **1065 passed / 1 skipped / 0 failed**;
- F4: **1073 passed / 1 skipped / 0 failed**;
- F5: **1084 passed / 1 skipped / 0 failed**;
- F6: **1094 passed / 1 skipped / 0 failed**;
- F7: **1104 passed / 1 skipped / 0 failed**;
- F9: **1132 passed / 1 skipped / 0 failed**;
- F11: **1160 passed / 1 skipped / 0 failed**.

---

# 3. EVOLUTION SYSTEM — F12–F16

## F12 — Evolution Foundation 🟩

Fundação do sistema de evolução:

- Capability Registry / Measurement;
- Self-Diagnostics / Improvement Planner;
- Hypothesis Manager;
- bounded Experiment Manager;
- Candidate Registry;
- Benchmark / Regression Detection;
- Safety Validator;
- Promotion Manager;
- Human Approval Gate;
- Rollback Manager;
- Evolution Memory.

Validação final:

**1177 passed / 1 skipped / 0 failed**

Merge:

`cb4f3610efb0ab57c61fe3aa6f1059a81e84029c`

## F13 — Evolution Laboratory 🟩

- laboratório isolado;
- workspaces em `evolution-lab/`;
- proteção contra path traversal;
- bloqueio de alteração do runtime estável;
- registro de experimentos/mudanças/candidatos sem execução.

Validação:

**1191 passed / 1 skipped / 0 failed**

Merge:

`5f2f89d9e49f9839a93e79a867b227d83dbf4bbd`

## F14 — Self-Diagnostics + Research 🟩

- diagnóstico determinístico;
- pesquisa baseada em evidências;
- oportunidades de melhoria;
- Improvement Planner;
- rastreabilidade entre diagnóstico, evidência, baseline, risco e plano.

Validação:

**1205 passed / 1 skipped / 0 failed**

Merge:

`09ec80b500bf4b63efcc085dda2fce5cfeb8b132`

## F15 — Candidate Build + Benchmark + Promotion 🟩

- Build Evidence;
- Benchmark;
- Regression Gate;
- Safety Review;
- Human Approval;
- Promotion metadata-only;
- integração com Candidate Registry.

Validação:

**1222 passed / 1 skipped / 0 failed**

## F16 — Continuous Evolution 🟩

- pós-promotion monitoring;
- estabilidade;
- degradação/regressão;
- histórico bounded;
- Evolution Trigger;
- novo ciclo baseado em evidências;
- integração com Evolution Memory.

Validação:

**1236 passed / 1 skipped / 0 failed**

Merge:

`01a2d08881a3537ab3ddf96491b0c64a0998ec0d`

---

# 4. INTELLIGENCE EVOLUTION — F17–F22

## F17 — Intelligence Stack Evolution 🟩

- ProviderProfile;
- ModelProfile;
- roteamento determinístico;
- StackEvidence;
- StackEvaluator;
- propostas isoladas de adaptação;
- Provider ≠ Model ≠ Lumen.

Validação:

**1244 passed / 1 skipped / 0 failed**

## F18 — Model Adaptation Laboratory 🟩

- DatasetSpec;
- AdaptationSpec;
- AdaptationExperiment;
- seed e reprodutibilidade;
- laboratório isolado;
- AdaptationEvidence;
- AdaptationCandidate;
- benchmark;
- regression detection;
- SafetyValidator;
- Human Approval;
- invariantes provider/model/base/target/métrica.

Validação:

**1259 passed / 1 skipped / 0 failed**

Merge:

`deef5888ccb97e9039c55ba30acb18d570d9ed43`

## F19 — Lumen Intelligence Lab 🟩

Camada permanente de pesquisa e coordenação de inteligência:

- IntelligenceCapability;
- IntelligenceTrack;
- baselines com proveniência;
- IntelligenceResearch;
- hipóteses;
- bounded IntelligenceEvidenceLedger;
- integração com F17 StackEvidence;
- integração com F18 AdaptationEvidence;
- findings;
- delta/confiança/regressão;
- oportunidades;
- digest determinístico;
- workspace isolado.

Validação:

**1278 passed / 1 skipped / 0 failed**

## F20 — Self-Optimizing Intelligence 🟩

- otimização baseada em evidências;
- avaliação e seleção bounded;
- isolamento experimental;
- benchmark/regressão;
- proteção dos gates existentes.

Validação registrada:

**1292 passed / 1 skipped / 0 failed**

Merge:

`8c19f7644896c9382ded9af799a262c53eccdbb5`

## F21 — Provider Independence 🟩

- Provider ≠ Model ≠ Lumen;
- contratos de capacidade;
- compatibilidade;
- fallback;
- migração reversível;
- redução de dependência de Provider específico.

Validação:

**1312 passed / 1 skipped / 0 failed**

Lumen Tests:

`36359332055`

F0 Validation:

`36359332009`

Merge:

`afcfd3cc2ac97471a043a1fdaeb4a74e9d253583`

## F22 — Continuous Intelligence Evolution 🟩

F22 fecha o ciclo contínuo:

```
OBSERVE
   ↓
ASSESS
   ↓
DETECT
   ↓
TRIGGER
   ↓
PLAN
   ↓
RESEARCH / ADAPT / STACK
   ↓
BENCHMARK
   ↓
SECURITY
   ↓
HUMAN APPROVAL
   ↓
PROMOTION
   ↓
MONITORING
   ↓
NEW BASELINE
   ↺
```

Correções finais incluíram:

- assessment atômico;
- trigger one-shot;
- plan one-shot;
- limiar de degradação numericamente estável;
- testes de atomicidade;
- testes de limites;
- testes de repetição.

Validação final:

**1329 passed / 1 skipped / 0 failed**

Lumen Tests:

`36360593948`

F0 Validation:

`36360593944`

Merge:

`3c862af35ca1cf152051b1a20f1bf686db14f2e9`

---

# 5. ESTADO GLOBAL DO SISTEMA

A arquitetura oficial agora representa:

```
USER
 ↓
LUMEN AGENT
 ↓
REASONING / PLANNING / MEMORY / RESEARCH
 ↓
INTELLIGENCE STACK
 ↓
COMPUTER INTELLIGENCE
 ↓
SECURE EXECUTION
 ↓
VERIFICATION / RECOVERY
 ↓
EXPERIENCE
 ↓
EVOLUTION SYSTEM
 ↓
INTELLIGENCE EVOLUTION
 ↓
CONTINUOUS INTELLIGENCE EVOLUTION
 ↺
```

A Lumen possui hoje uma trilha completa de:

**percepção → raciocínio → planejamento → execução segura → verificação → aprendizado → evolução → monitoramento → nova evolução.**

---

# 6. BOUNDARY DE SEGURANÇA — NÃO NEGOCIÁVEL

O sistema de evolução pode evoluir capacidades, mas não pode unilateralmente remover ou enfraquecer:

- PermissionManager;
- Policy Engine;
- Sandbox;
- Checkpoint;
- Audit;
- Rollback;
- Promotion Rules;
- proteção de secrets;
- limites de autoridade;
- isolamento do Evolution Laboratory;
- Human Approval Gates.

Mudanças nesses mecanismos exigem **aprovação humana explícita**.

Nenhuma fase F12–F22 cria autoridade paralela de execução.

---

# 7. REGRA DE EXECUÇÃO

A cadeia oficial de execução continua:

```
Goal
 ↓
Planner / Agent
 ↓
Tool / Computer Action
 ↓
Permission
 ↓
Policy
 ↓
Scope
 ↓
Checkpoint
 ↓
Sandbox / Driver
 ↓
Audit
 ↓
Verification
 ↓
Recovery / Regression
```

A evolução não pode bypassar essa cadeia.

---

# 8. LIMITAÇÃO DE AMBIENTE

As validações de CI são executadas em ambiente Linux.

Portanto:

- CI verde ≠ smoke test físico de Windows;
- CI verde ≠ smoke test físico de Unreal Engine;
- CI verde ≠ validação física de mouse/teclado/UI Automation;
- testes reais de Windows/Unreal continuam sendo uma validação de ambiente separada.

Nenhuma fase deve ser considerada como tendo passado por smoke test físico Windows/Unreal apenas por causa da CI Linux.

---

# 9. REGRA DE CONTINUIDADE

Ao alterar a Lumen:

1. alterar a Lumen existente;
2. preservar o GitHub como source of truth;
3. implementar em branch quando a mudança for significativa;
4. criar testes;
5. executar testes possíveis;
6. corrigir falhas;
7. executar CI;
8. revisar segurança;
9. atualizar `LUMEN_STATE.md`;
10. atualizar este arquivo;
11. atualizar roadmap/documentação específica;
12. commit;
13. merge somente com validação verde;
14. registrar evidência final;
15. somente então marcar a fase como 🟩.

---

# 10. ESTADO PARA O PRÓXIMO CHAT / AGENTE

**Projeto:** Lumen  
**Estado:** 🟩 F0–F22 concluídas  
**Última fase:** F22 — Continuous Intelligence Evolution  
**Última validação:** 1329 passed / 1 skipped / 0 failed  
**Último merge conhecido:** `3c862af35ca1cf152051b1a20f1bf686db14f2e9`  
**Branch oficial:** `master`

### Instrução de continuidade

Antes de qualquer nova implementação:

1. atualizar o clone local;
2. ler `LUMEN_STATE.md`;
3. ler este arquivo;
4. ler `docs/LUMEN_COMPUTER_INTELLIGENCE_ROADMAP.md`;
5. identificar se existe uma nova fase oficialmente aprovada;
6. não inventar F23;
7. não marcar trabalho como concluído sem evidência;
8. preservar todas as barreiras de segurança existentes.

**A próxima fase só existe após uma decisão arquitetural explícita e documentação correspondente.**

---

# 11. NORTH STAR OPERACIONAL

A Lumen deve evoluir de:

`Agent + Tools`

para:

`Agent + Research + Knowledge + Experience + Computer Intelligence + Secure Execution + Verification + Evolution System`

e continuar evoluindo para uma inteligência capaz de:

**descobrir limitações → pesquisar soluções → formular hipóteses → experimentar com segurança → medir resultados → validar regressões → obter aprovação quando necessário → promover mudanças → monitorar resultados → estabelecer novos baselines → repetir o ciclo.**

**Estado final atual: 🟩 F0–F22 CONCLUÍDAS.**


## 11. ARQUIVO HISTÓRICO CONSOLIDADO — ROADMAP ANTERIOR


## F23 — Real Environment Validation & Integration Readiness 🟩

Concluída como fase de prontidão: detector determinístico de ambiente, contrato fail-closed de evidência, testes dedicados e CI Ubuntu/Windows. A fase não declara validação física de mouse/teclado/UI Automation nem Unreal; esses gates permanecem NOT_EXECUTED até execução em ambiente real.

Documento: docs/F23_REAL_ENVIRONMENT_VALIDATION.md.

# Roadmap da Lumen

**Status atual: `0.6.8` (base oficial) + fases internas 9A×2, 9B, 10A, 10B, 11A,
11B, 11C, 11D, 11E, 11F, 11G, 11H, 11I, 11J e 11K concluídas sem bump de
versão — ver "Estado real" abaixo.**

Cada versão entrega um incremento fechado e testado. Regra de ouro do
projeto: **nenhuma capacidade sensível entra sem que a camada de
permissões e o fluxo de confirmação do usuário estejam prontos antes**.

---

## Estado real (2026-09-01) — base 0.6.8 + fases internas 9A–11K

Concluído sobre a 0.6.8, **sem bump de versão** (engenharia interna;
detalhes em `LUMEN_STATE.md`):

- **9A×2** — auditorias read-only da cadeia de execução.
- **9B** — persistência opt-in do execution state (bundles
  sanitizados em `data/executions`; default OFF).
- **10A/10B** — Advanced Planning MVP: guardrails do Planner
  (12 tarefas, profundidade 6, 16 KiB/campo, 4 refs/parâmetro),
  refinador conservador em 2 estágios (default OFF), data-flow
  `${Tn.data.campo}` validado no planejamento, `success_criteria`
  (metadado). R4 (replanning automático) PROIBIDO/adiado.
- **11A** — auditoria + spec do Coding Agent (read-only).
- **11B** — tool `search_files` (READ-only): 7ª tool de filesystem no
  registry default **e presente no Planner Catalog** (planejamento
  automático OK); 19 testes dedicados; PROBE oficial 22/22.
- **11C** — tool `edit_file` (**WRITE**): edição **literal com
  ocorrência exatamente 1** (0 ⇒ `NO_MATCH`; ≥2 ⇒ `MULTIPLE_MATCHES`;
  nada é escrito em falha); tool **destrutiva ⇒ checkpoint
  obrigatório** antes de escrever (aprovação aplica; recusa mantém o
  arquivo intacto); presente no **Planner Catalog** (planejamento
  automático OK); +7 testes dedicados e +2 de integração de
  checkpoint. Spec: `docs/SPEC-11C-EDIT_FILE.md`.
- **11D** — tool `run_pytest` (**TERMINAL**): runner dedicado que roda
  a suíte pytest do workspace de forma **estruturada** (subprocesso
  controlado, sem shell — `python`/`pytest` seguem na denylist do
  terminal, sem liberar nada no `run_command`); **checkpoint
  obrigatório antes de executar** (aprovação executa; recusa não
  executa); registrada no registry e no **Planner Catalog** somente
  com o terminal habilitado; saída estruturada (`exit_code`,
  `summary_line`, truncamento) sem vazar output completo na
  auditoria; +2 testes de integração de checkpoint e +4 de
  validação de protocolo/catálogo. Spec:
  `docs/SPEC-11D-BUILD_TEST.md`.
- **11E** — **verificação real opt-in**: `enable_verification("pytest_result")`
  no `ToolsController` (default OFF) instala o
  `PytestResultVerifier` — **interpretativo, não executa nada** (a
  execução real é a task `run_pytest` da 11D, com TERMINAL +
  checkpoint); o verifier lê o JSON do `ToolResult`: verde ⇒
  `verified=True`, vermelho ⇒ task `REJECTED` e plano falha
  (fail-fast); `applied=False` para tasks não aplicáveis mantém
  `verified=None`; +4 testes (flag `applied` + e2e verde/vermelho).
  Spec: `docs/SPEC-11E-REAL_VERIFICATION.md`.
- **11F** — **auto-anexo de `run_pytest` após WRITE** (opt-in): em
  `ToolsController.run_plan`, quando terminal habilitado + verificação
  11E habilitada + plano contém WRITE (`write_file`/`create_file`/
  `delete_file`/`edit_file`), é anexada 1 task final `run_pytest`
  (depende de todas as anteriores) antes de executar; idempotente
  (não anexa se `run_pytest` já estiver no plano; default continua sem
  auto-anexo); guardrail: plano em 12/12 tasks + anexo necessário ⇒
  **falha antes de executar** (FAILED, tudo SKIPPED, nada roda); +3
  testes. Spec: `docs/SPEC-11F-AUTO_PYTEST_AFTER_WRITE.md`.
- **11G** — **evidência real em modo corrections** (sem bypass): em
  modo corrections o verifier 11E agora se aplica
  (`verifier_factory` no `CorrectionEngine`) — pytest vermelho ⇒ task
  `REJECTED` (não `DONE`); cada sucessor `#C` passa por hook
  `plan_transform` que reutiliza a regra 11F para manter a evidência
  `run_pytest` ao final quando aplicável (idempotente; respeita o teto
  de 12 tasks — falha controlada se não puder anexar, sem executar o
  sucessor). Sem bypass (pytest sempre via task com checkpoint) e sem
  repair-loop automático/auto-replanning; +2 testes. Spec:
  `docs/SPEC-11G-CORRECTIONS_EVIDENCE.md`.
- **11H** — **toggles persistentes de automação (Settings/UI)**:
  `ToggleStore` (`app/tools/toggles_store.py`) persiste
  `data/agent_toggles.json` (escrita atômica, schema `version: 1`,
  **fail-closed** — arquivo ausente/corrompido ⇒ tudo OFF, sem
  exceção) com `corrections_enabled`/`verification_enabled`; o
  `ToolsController` restaura/aplica no startup via `toggles_file`
  (`main.py` passa `settings.data_dir / "agent_toggles.json"`) e os
  setters persistem na hora (auditados); `ToolsDialog` ganhou a seção
  **AUTOMAÇÃO (11H)** (ligar/desligar Correções e Verificação real —
  reflete o controller ao abrir; persiste ao clicar). **Os toggles
  nunca concedem permissão** — TERMINAL continua concessão explícita
  por sessão (regra 0.6.x); +5 testes (3 persistência no controller +
  2 UI headless). Spec:
  `docs/SPEC-11H-SETTINGS_UI_TOGGLES.md`.
- **11I** — **export de relatório de evidências (opt-in)**: flag
  `LUMEN_EXPORT_EXECUTION_REPORTS` (Settings, **default OFF** — bit-a-bit
  atual); em estado terminal (COMPLETED/FAILED), o funil `_final`
  exporta (best-effort — **falha não quebra a execução**) um JSON
  **sanitizado** em `data_dir/reports/<plan_id_sanitizado>.json`
  contendo `plan` + `execution_report` + `correction_history` +
  auditoria **filtrada por `plan_id`** (módulo puro
  `app/tools/report_export.py`; sanitização reutilizada do 9B —
  segredos redigidos, strings truncadas, sem stdout). **Sem execução,
  sem permissões**; +2 testes (export ON sanitizado / OFF bit-a-bit).
  Spec: `docs/SPEC-11I-REPORT_EXPORT.md`.
- **11J** — **correções com evidência (advice-only)**: a estratégia
  **default** de `enable_corrections` agora é
  `EvidenceCorrectionStrategy` sobre a conservadora
  `ToolCorrectionStrategy` (strategy custom nunca é sobrescrita); para
  falhas de `run_pytest` (REJECTED/FAILED), ela extrai a evidência real
  (`exit_code`/`summary_line`/`timed_out`/`truncated`) do JSON do
  `ToolResult` em `run.result` (somente parse — **sem execução
  escondida**) e produz **conselho** (`corrected_task=None`) registrado
  no ciclo de correção (JSONL) e no relatório 11I — o ciclo encerra
  **sem pausa** (nada é aplicado, sem card; não aplica task
  automaticamente). Sem auto-replanning (R4 continua proíbido);
  correções **com tarefa** continuam exigindo aprovação explícita; +1
  teste. Spec: `docs/SPEC-11J-EVIDENCE_CORRECTIONS.md`.
- **11K** — **snapshot "before" + restore (opt-in)**: com
  `enable_snapshots` (**default OFF** — bit-a-bit; store sem efeitos
  colaterais no startup), cada tool destrutiva de filesystem guarda uma
  cópia do alvo **antes** de executar (depois do checkpoint aprovado;
  best-effort — falha nunca interrompe) em
  `data_dir/snapshots/<safe_plan_id>/<task_id>/{manifest.json,before.bin}`
  (alvo inexistente ⇒ `existed_before=False`; acima do teto ⇒ manifest
  sem cópia); auditoria registra **somente metadados** (nunca
  conteúdo). Tool `restore_snapshot` (WRITE) para **rollback manual
  mínimo**: restaura os bytes originais (`existed_before=True`) ou
  desfaz o create (`existed_before=False` — delete idempotente);
  manifest ausente/inválido ⇒ falha honesta (sem restore especulativo).
  **Checkpoint pré-validado**: só pausa quando o restore é viável
  (WRITE + parâmetros + manifest + sandbox/policy); inviável ⇒ a task
  falha direto com o motivo (sem aprovação decorativa). Registrada no
  registry independentemente do terminal. +5 testes focados (084/087).
  Spec: `docs/SPEC-11K-SNAPSHOT_ROLLBACK.md`.

**Suíte completa: 995 passed / 5 skipped / 0 failed (1000 coletados).**

**Próximos tópicos da trilha Coding Agent (0.7) — NÃO AUTORIZADOS /
NÃO IMPLEMENTADOS:** verificação real completa, repair-loop (reparo
via CorrectionEngine), wiring Settings→Planner, rollback robusto
automático/contínuo (a 11K entrega apenas snapshot "before" + restore
manual mínimo). O runner dedicado de build/test estruturado
(`run_pytest`) foi entregue na 11D, a verificação real (opt-in) na
11E, o auto-anexo após WRITE na 11F, a evidência em modo corrections
na 11G, os toggles persistentes (Settings/UI) na 11H, o export de
relatório de evidências (opt-in) na 11I, o conselho com evidência nas
correções (advice-only) na 11J e o snapshot "before" + restore manual
(opt-in) na 11K.
Restrições vigentes preservadas: R4 (sem replanning automático) e F17
(sem Computer Control / vision / Unreal / Blueprint / C++).

## Lumen 0.1 — Fundação ✅

- Arquitetura modular em camadas (UI → Agent Core → AI Provider →
  Memory → Task System → Tools → Permissions).
- Interface Tkinter (conversa, entrada, envio, indicador de estado).
- `AIProvider` (abstração) + `MockProvider` — funciona sem API externa.
- Memória de conversa local (JSON, escrita atômica).
- Task Manager inicial (`id`, `title`, `status`, `created_at`; sem execução).
- Contrato de ferramentas (`Tool` + `ToolRegistry`) — nenhuma tool concreta.
- Permissões (`CHAT`, `READ`, `WRITE`, `TERMINAL`, `COMPUTER_CONTROL`);
  apenas `CHAT` por padrão.
- Configuração `.env`, logging com redação de segredos, testes pytest.

## Lumen 0.2 — Cérebro Real ✅

- **`OpenAIProvider`** (SDK oficial, import lazy) selecionável via
  `LUMEN_PROVIDER=openai`; `mock` continua como modo offline padrão.
- **`GeminiProvider`** (complemento) — Google Gemini via SDK oficial
  `google-genai`, modelo padrão GA `gemini-2.5-flash`, no mesmo sistema
  de cofre/troca de provider/TESTAR CONEXÃO da tela ⚙ Configurações.
- Configuração validada na inicialização: API key/modelo ausentes geram
  mensagens claras explicando como configurar o `.env`.
- **Persona central** (`app/config/persona.py`): nome Lumen, assistente
  feminina, papel de desenvolvimento, idioma português — e **system
  prompt** único, organizado em seções (identidade, papel, idioma,
  estilo, honestidade/limitações, futuro).
- **Contexto**: o Agent envia system prompt + histórico limitado
  (`LUMEN_MAX_CONTEXT_MESSAGES`) + mensagem atual; timestamps são
  removidos do payload.
- **Streaming**: resposta exibida progressivamente na UI via callback
  `on_delta` (fila + `after`); sem retry após deltas emitidos (evita
  duplicação visível).
- **Timeout** (`LUMEN_REQUEST_TIMEOUT`) e **retry limitado**
  (`LUMEN_MAX_RETRIES`) apenas para erros temporários (rate limit,
  timeout, rede, 5xx); nunca para autenticação/configuração.
- **Taxonomia de erros**: key ausente, autenticação inválida, modelo
  inválido, rate limit, timeout, rede, 5xx, dependência ausente,
  inesperado — todos com mensagem amigável e detalhes técnicos no log.
- **`AIResponse` normalizada** (content, model, usage de tokens,
  finish_reason) + `ResponseType` (FINAL_RESPONSE | TOOL_CALL | PLAN)
  preparando o futuro de agente sem reescrever o Agent Core.
- UI: cabeçalho com provedor/modelo, status ● Pensando…, erros amigáveis,
  resposta progressiva.
- Testes: 104 (todos offline; chamadas OpenAI simuladas por client fake).

## Lumen 0.3 — Memória avançada ✅ *(fundação entregue)*

Escopo real entregue nesta etapa (fundação da memória inteligente,
conforme a spec: *"apenas a parte de memória"*):

- **Memória estruturada em 6 domínios** — projetos, tarefas,
  conhecimento, decisões, erros e soluções (`MemoryKind` +
  `RecordStore` por domínio, JSON local com escrita atômica) — separada
  da conversa cotidiana (que continua linear como na 0.1).
- **Registros completos**: id sequencial por domínio (`PRJ-`, `TASK-`,
  `KN-`, `DEC-`, `ERR-`, `SOL-0001`), timestamps, origem, tags,
  `project_id`, relacionamentos (`related_ids`, bidirecionais via
  `relate()`), `supersedes` e `content_hash`.
- **Ciclo de vida**: deduplicação por hash entre ACTIVE; `update`
  imutável (recalcula hash, rejeita colisão); `mark_obsolete`;
  `supersede` cria o sucessor e preserva a trilha do antecessor.
- **Busca por relevância**: título 3 > tag 2 > conteúdo 1, +1 quando
  todos os termos casam; acento-insensível; obsoletos penalizados (×0,2)
  e excluídos por padrão.
- **Contexto para a IA**: `MemorySystem.build_context(query)` monta o
  pacote (registros estruturados primeiro, conversa completa a cota,
  excertos ≤400 chars) limitado por `LUMEN_MAX_MEMORY_RECORDS` — o ganho
  pronto para o fluxo futuro do Agent (0.4+).
- **Segurança**: `redact_secrets` roda **antes** de persistir em
  qualquer domínio; arquivo corrompido/inválido → erro claro
  (`RecordStoreError`); memória 100% local, nunca enviada a provedores.

**Ainda NÃO entregue (adiei de propósito — ver 0.3.x):** a integração
da memória ao fluxo do Agent (o Agent ainda não consulta
`build_context()` ao responder), sumarização, busca semântica, múltiplas
sessões e SQLite — os quatro primeiros itens abaixo vieram do ROADMAP
original da 0.3 e foram re-escalonados para não inflar esta etapa:

## Lumen 0.3.x — Provider Expansion ✅ *(complemento entregue 2026-08-28)*

Expansão da camada de providers, sem tocar Agent/UI/memória além da
integração já existente (escopo fechado; detalhes em `LUMEN_STATE.md`):

- **`GroqProvider`** (`app/ai/groq_provider.py`, SDK oficial `groq`) —
  padrão `openai/gpt-oss-120b`; também serve os Llama
  `llama-3.3-70b-versatile`/`llama-3.1-8b-instant`.
- **`TogetherProvider`** (`app/ai/together_provider.py`, SDK oficial
  `together`) — **Llama 4 real**: padrão
  `meta-llama/Llama-4-Scout-17B-16E-Instruct`; alternativa Maverick.
  Escolhido após a Meta **encerrar a Llama API em 06/07/2026** e a
  Cerebras remover os Llama do catálogo público (decisão documentada em
  `docs/ARCHITECTURE.md` §3.7).
- Ambos no registro da fábrica (`mock | openai | gemini | groq |
  together`), na tela ⚙ (descoberta dinâmica), no cofre de credenciais,
  TESTAR CONEXÃO, timeout/retry/streaming e troca em runtime — mesma
  taxonomia de erros e contratos do `AIProvider`.

## Lumen 0.3.x — Memória avançada (continuação, futura)

> **Entregue nesta linha em 2026-08-28:** o complemento **Provider
> Expansion** (Groq + Together AI/Llama 4) — ver `LUMEN_STATE.md`.
> Os itens abaixo seguem pendentes.

- Integrar a memória estruturada ao fluxo do Agent (consultar
  `build_context()` antes de responder; armazenar conhecimento após a
  resposta) — pré-requisito natural da 0.4.
- Sumarização de conversas longas; memória de longo prazo por projeto.
- Múltiplas conversas/sessões; busca semântica (embeddings locais ou API).
- Migração do armazenamento (ex.: SQLite) sem mudar os contratos.
- Controle de uso de tokens acumulado (a partir do `Usage` já preservado).

## Lumen 0.4 — Planner ✅ *(fundação entregue)*

Escopo real entregue (somente planejamento; **nada é executado**):

- **`app/planner/`** — `Planner.create_plan(pedido)`: prompt de
  planejador com protocolo JSON strict → provedor de IA via abstração
  `AIProvider` (agnóstico: mock/openai/gemini/groq/together) →
  validação (tarefas ≥1, descrições, dependências existentes, sem
  ciclos via ordenação topológica) → `Plan`.
- **Estruturas**: `Plan` (id `PLN-0001`…, objetivo, status, análise
  prévia, timestamps) e `PlannedTask` (id `T1…Tn`, descrição, ordem,
  dependências, estado, resultado, erro) — dados imutáveis.
- **Estados do plano**: `PLANNING` (transitório), `READY` (válido),
  `BLOCKED` (pré-condição do ambiente ausente, ex.: provider sem
  chave), `FAILED` (plano inválido/erro do provedor — motivo claro em
  `error`, nunca traceback) e `COMPLETED` (reservado ao executor
  futuro).
- **Integração com o Agent**: `Agent.request_plan(pedido)` — usa o
  provider vigente (troca em runtime) e o histórico como contexto; o
  fluxo de conversa (`send_message`) permanece intocado.
- **Memória 0.3**: consultada em **somente leitura** (`recall`) para
  enriquecer o planejamento — nunca gravada nem duplicada.
- **Segurança**: nenhuma execução — sem terminal/arquivos/mouse/teclado/
  Unreal/tool calling (garantido por testes estáticos).

**Ainda NÃO entregue (adiei de propósito — ver 0.4.x):** os itens do
ROADMAP original da 0.4 que dependem de execução:

## Lumen 0.4.x — Executor de Planos — fundação ✅

Entregue (simulado/in-memory, sem nenhuma ferramenta real):

- **`app/executor/`** — `PlanExecutor` executa um plano `READY`
  respeitando ordem e dependências (tarefa só roda com dependências
  `DONE`); avanço tarefa por tarefa (`step()`) ou até o fim
  (`run_all()`); **fail-fast** (falha → restantes `SKIPPED`, plano
  `FAILED`); `TaskRun` (resultado/erro/tentativas por tarefa) e
  `ExecutionReport` imutável (eventos, timestamps, `to_dict()`).
- **`TaskHandler` (ABC) + `SimulatedHandler`** — a ação de cada tarefa
  vive no handler; futuramente ferramentas reais (0.5+) entram como
  handlers sobre o `ToolRegistry` (que segue vazio) sem mudar o núcleo:
  `Planner → Executor → TaskHandler → ToolRegistry → Tools`.
- **`ExecutionObserver` (no-op)** + campos `attempts`/`result`/`error`:
  abstrações mínimas preparadas para checkpoints, retry, verificação e
  correção — **não implementados**.
- **`Agent.execute_plan(plan, handler?)`** — gate `CHAT`; não altera
  conversa, memória 0.3 nem providers.
- Estados: plano `RUNNING → COMPLETED|FAILED`; tarefas
  `PENDING → DONE|FAILED|SKIPPED`.

## Lumen 0.4.x — Checkpoints + Retry + Verificação ✅

Entregue (tudo simulado/in-memory; sem UI e sem ferramentas reais):

- **Checkpoints** (`app/executor/checkpoints.py`): `CheckpointPolicy`
  (ABC · `NeverCheckpoints` padrão · `EveryTaskCheckpoints`) — pausa a
  execução antes de ações importantes com `CheckpointRequest`/
  `CheckpointStatus` (`PENDING_APPROVAL` = necessário/execução pausada
  aguardando confirmação · `APPROVED` = aprovado/retoma · `REFUSED` =
  recusado ⇒ plano `FAILED` controlado, tarefa não executada).
  Aprovação/recusa via `executor.approve_checkpoint()`/`refuse_checkpoint()`.
- **Retry controlado** (`app/executor/retry.py`): `RetryPolicy`
  (`max_attempts ≥ 1` validado — **impossível retry infinito**;
  backoff linear injetável) + `AttemptRecord` por tentativa (número,
  resultado, erro) no `TaskRun.attempt_log`; erros inesperados do
  handler não são repetidos.
- **Verificação de resultado** (`app/executor/verification.py`):
  `TaskVerifier` (ABC) + `SimulatedVerifier`; `EXECUTOU → VERIFICOU →
  SUCESSO` (`DONE`/`verified=True`) ou `… → FALHOU` (`REJECTED`/
  `verified=False` com resultado preservado; fail-fast; não consome
  retry).
- **Preparação para correção automática** (`app/executor/correction.py`):
  `CorrectionStrategy` (ABC) + `CorrectionProposal` +
  `NoopCorrectionStrategy` — **abstrações apenas**: o Executor não
  importa/chama o módulo (auditoria AST); o loop
  `falha → análise → correção → nova tentativa → verificação` é futuro.
- `Agent.execute_plan(plan, handler?, verifier?, retry?, checkpoints?)`;
  `ExecutionReport` ganha `checkpoints` (histórico) e
  `pending_checkpoint` (pausa ativa).

## Lumen 0.4.x — Planner/Executor (continuação, futura)

- **Correção automática real**: ligar `CorrectionStrategy` ao fluxo
  (análise da falha — via provider — → proposta → nova tentativa →
  verificação), com limites claros.
- Conectar ferramentas reais ao Executor via handlers sobre o
  `ToolRegistry` (exige as tools da 0.5+ e o porteiro de permissões).
- `TaskStatus`/`TaskManager` integrados à execução e UI para
  exibir/aprovar planos e checkpoints (hoje: aprovação via API interna).
- Respostas do modelo representando `PLAN`/`TOOL_CALL`
  (`ResponseType` já preparado).

## Lumen 0.5 — Filesystem Tools ✅ *(fundação segura)*

Escopo real entregue (somente filesystem; **tudo confinado, permitido e
auditado**):

- **Ferramentas** (`app/tools/filesystem.py`): `list_directory`,
  `read_file` (UTF-8, limite de tamanho), `write_file`
  (cria/sobrescreve), `create_file` (não sobrescreve), `delete_file`
  (opt-in duplo) e `file_exists` — contratos claros, entradas validadas
  e **resultados estruturados** (`ToolResult` em JSON: operação, caminho
  solicitado/resolvido, dados, erro amigável).
- **Sandbox/workspace** (`WorkspaceSandbox`): acesso apenas a diretórios
  **explicitamente autorizados** (raízes absolutas, resolvidas);
  bloqueia `..`/traversal (sempre, até internamente), caminhos fora das
  raízes, caminhos inválidos (vazios, caracteres de controle, tipo
  errado), symlinks que escapam, **escrita em modo somente leitura**
  (default) e exclusão sem `allow_delete=True` + `writable=True`.
- **Permissões**: leitura exige `READ`; escrita/criação/exclusão exigem
  `WRITE` — porteio pelo `ToolRegistry` (o código da ferramenta nem
  roda sem permissão). Concessões continuam explícitas (default: só
  `CHAT`); `main.py`/startup sem efeitos colaterais e **sem permissão
  global nova** (nada de "acesso a todo o Windows").
- **Ponte com o Executor** (`app/tools/handler.py`): `ToolTaskHandler`
  despacha tarefas com `tool`/`parameters` (campos novos e opcionais em
  `PlannedTask`; o protocolo do Planner **não** emite ferramentas —
  planos com tools são montados programaticamente) via `ToolRegistry`;
  tarefa sem ferramenta falha honestamente (nada simulado);
  `ToolCheckpoints` pausa antes de ferramentas destrutivas
  (`write_file`/`create_file`/`delete_file`) — aprovar executa, recusar
  bloqueia (consentimento sem UI obrigatória).
- **Auditoria** (`FilesystemAudit`): toda tentativa (sucesso, bloqueio
  de política/gate de permissão ou erro) registra ferramenta, operação,
  caminho solicitado, caminho resolvido, desfecho, erro, timestamp e
  tarefa/plano de origem — **sem conteúdo de arquivos** (apenas
  metadados: tamanhos/contagens/flags).

**Ainda NÃO entregue na 0.5 (base):** protocolo do Planner emitindo
chamadas de ferramenta; níveis granulares de acesso além da política
atual (ex.: `EXECUTE` — que continua proibido até a 0.6).
*(UI de workspaces/permissões/checkpoints e persistência de auditoria
foram entregues na 0.5.x — seção seguinte.)*

## Lumen 0.5.x — UI de Workspaces, Permissões, Checkpoints e Auditoria ✅

Camada **visual e de controle** para usar as ferramentas com segurança
(toda a lógica no `ToolsController`, testável sem UI; os diálogos são
apenas apresentação):

- **Workspaces** (`app/tools/workspaces.py`): diretórios
  **explicitamente autorizados** com política própria
  (`WorkspaceEntry`: somente leitura · escrita · escrita+exclusão);
  `WorkspaceStore` persiste em `data/workspaces.json` (atômico; arquivo
  só nasce na 1ª autorização) com **validação e normalização**
  (absoluto, existente, diretório, resolvido, sem duplicatas, **raiz de
  disco/Windows inteiro rejeitada**); `MultiWorkspaceSandbox` aplica a
  política **por raiz** (workspace somente-leitura bloqueia escrita
  nele mesmo que outro permita); conjunto vazio ⇒ tudo bloqueado.
  Pela UI (🛡): visualizar/adicionar/remover e ver o modo claramente.
- **Permissões** (`ToolsController`): visualizar/conceder/revogar
  `CHAT`/`READ`/`WRITE` (CHAT segue padrão; READ/WRITE exigem
  concessão explícita); `DELETE` **não** é nível — é o opt-in por
  workspace (escrita + permitir excluir), exibido como tal;
  `TERMINAL`/`COMPUTER_CONTROL` são **rejeitados** pela camada
  (nenhuma concessão silenciosa de níveis futuros).
- **Checkpoints** (`PrevalidatedCheckpoints` + UI): operações
  destrutivas viáveis **pausam** para aprovação; a tela mostra **o
  que** (descrição), **onde** (caminho solicitado → resolvido +
  workspace), **qual ferramenta**, **qual operação/permissão** e
  botões **APROVAR/RECUSAR** — recusa garante que **nada roda**
  (testado); operações inviáveis (sem permissão/fora da política) nem
  chegam a pedir aprovação: falham controladas com o motivo real
  (bloqueio honesto, sem aprovação decorativa).
- **Auditoria** (`app/tools/audit_log.py`): persistência **JSONL**
  (`data/audit/audit.jsonl`, append thread-safe, diretório criado na
  1ª escrita) via sink da 0.5; visualização na UI com ferramenta,
  operação, caminho solicitado/resolvido, ✓/✗, erro, timestamp e
  tarefa/plano — **sem conteúdo de arquivos** (separado do conteúdo
  dos arquivos por construção); leitor tolera linhas corrompidas.
- **Integração**: tela **🛡 Ferramentas** na janela principal
  (`app/ui/tools_dialog.py`); `main.py` compõe o `ToolsController`
  **sem efeitos colaterais** (nenhum arquivo/permissão no startup);
  chat, memória, providers (5), Executor e sandbox da 0.5 intocados
  (suíte 0.5 preservada).

## Lumen 0.6 — Terminal Tools ✅ *(fundação controlada)*

> **Entregue em 2026-08-28 (0.6.0)** — com uma decisão **mais rígida**
> que o item original abaixo: comando fora da allowlist é
> **bloqueado antes de qualquer execução** (não "confirmado e
> executado"). Detalhes em `docs/ARCHITECTURE.md` §17 e
> `LUMEN_STATE.md`.

- **`run_command`** (`app/tools/terminal.py` — `subprocess` controlado
  (2º módulo autorizado na 11D: `run_pytest.py`), garantido por testes
  AST): executa **argv lista sem
  shell**, captura `stdout`/`stderr` separadas com teto, `exit_code`,
  `timed_out` e `truncated`, tudo em `ToolResult` estruturado.
- **Allowlist explícita** (`TerminalPolicy.allow`/
  `ToolsController.enable_terminal`) — nada executa sem estar na lista;
  cada `AllowedCommand` define se exige aprovação (default **sim**),
  timeout próprio e argumentos fixos opcionais; `full_path` exige match
  exato (`/tmp/evil/git` nunca casa com `git`).
- **Denylist permanente** (137 nomes normalizados): shells
  (`sh`/`powershell`/`cmd`…), interpretadores (`python`/`node`…),
  builders (`make`/`dotnet`/`docker`…), escalonamento (`sudo`/`runas`),
  destrutivos/administrativos (`rm`/`shutdown`/`reg`/`chmod`…) e
  **rede** (`curl`/`ssh`…) — jamais allowlistáveis; normalização mata
  aliases (`python.exe`, `POWERSHELL`, `/bin/sh`).
- **Argumentos blindados**: operadores de shell/redirecionamento
  (`&&`, `|`, `;`, `>`, `$(`…), argumentos-perigo (`-exec`, `/c`,
  `-EncodedCommand`), `..` e caminhos absolutos fora dos workspaces —
  todos bloqueados (salvo `allow_operators` explícito).
- **cwd confinado** aos workspaces autorizados (mesmo contrato do
  filesystem 0.5); **timeout obrigatório** (default 10 s, teto 60 s,
  mata o processo); **limite de saída** (64 KiB — trunca e falha
  honesto); **ambiente filho sanitizado** (sem `*KEY*`/`*TOKEN*`/
  `*SECRET*`/`*PASSWORD*` — `printenv` nunca vaza credenciais).
- **Permissão `TERMINAL`** exigida pelo `ToolRegistry` antes de
  qualquer código da ferramenta (concessão programática explícita; a UI
  segue concedendo apenas CHAT/READ/WRITE).
- **Checkpoint** antes de cada comando `requires_approval`
  (`PrevalidatedTerminalCheckpoints` — mesma lógica 0.5.1: só operações
  viáveis pausam; inviáveis falham direto com o motivo real). O card
  mostra **argv completo, permissão e timeout**; recusa ⇒ nada roda.
- **Auditoria JSONL**: comando sanitizado (argv truncado p/ trilha),
  cwd, `exit_code`, `timed_out`/`truncated`, duração, desfecho, erro,
  tarefa/plano — **nunca stdout/stderr/conteúdo**.
- **Plano Executor/Planner intactos** (agnósticos); registro só via
  `enable_terminal` — **nada habilitado no startup**.
- Itens originais cumpridos: allowlist ✔ timeout ✔ captura de saída ✔
  sandbox (cwd) ✔ permissão `TERMINAL` ✔.

## Lumen 0.6.x — UI de Terminal, Allowlist e Concessão TERMINAL ✅

Fechamento do **ciclo humano** do terminal (como a 0.5.x foi para a
0.5): quem concede, cadastra e remove é o usuário, pela tela 🛡 — a UI
fala **somente** com o `ToolsController` (nenhuma lógica de segurança na
interface; testes garantem por AST/inspeção):

- **Concessão `TERMINAL` explícita e auditada**: ver estado, conceder e
  revogar por botão dedicado (`grant_terminal`/`revoke_terminal`); o
  caminho **genérico** de permissões segue **rejeitando** TERMINAL
  (nenhuma concessão silenciosa ou "por engano"); `COMPUTER_CONTROL`
  permanece inconcedível por qualquer via; a concessão **vale só na
  sessão** — nunca é persistida nem restaurada do disco. A UI deixa
  claro o que TERMINAL permite: **apenas comandos da allowlist**, dentro
  dos workspaces, com timeout, limite de saída, ambiente sem segredos e
  checkpoint por comando (shells/interpretadores/rede proibidos).
- **Allowlist gerenciável pela UI**: cadastrar comando (com aprovação
  obrigatória — default — ou execução direto), remover, e desabilitar o
  terminal (esvazia a lista). Persistência em `data/terminal.json`
  (`TerminalStore`: escrita atômica; arquivo só nasce no primeiro
  cadastro; **fail closed** — arquivo ilegível ⇒ terminal desabilitado,
  entrada inválida/denylistada ⇒ descartada com aviso; defaults da
  política restaurados). O primeiro cadastro habilita a allowlist (o
  ato explícito de habilitar) — **sem conceder permissão**.
- **Card de aprovação completo**: comando, **argumentos**, **diretório
  de trabalho** e **timeout** em linhas separadas (além de
  ferramenta/operação/permissão); checkpoints da 0.6 intactos (recusa ⇒
  nada roda; só operações viáveis pausam).
- **Auditoria administrativa** em JSONL (`tool=terminal_admin`):
  `terminal_grant`, `terminal_revoke`, `allowlist_add`,
  `allowlist_remove`, `terminal_enable`, `terminal_disable` — inclusive
  tentativas rejeitadas (denylist), sem conteúdo sensível.
- **Startup sem efeitos colaterais preservado**: nenhum
  `terminal.json`/concessão nasce sem ação do usuário; `main.py` apenas
  aponta o caminho do arquivo (leitura).

## Lumen 0.4.x — Correção Automática Controlada ✅ *(0.6.2)*

O mecanismo adiado desde a 0.4.x, agora **real e controlado** — não é
uma autorização para a Lumen fazer qualquer coisa: é o ciclo
**EXECUTAR → VERIFICAR → SUCESSO continua / FALHA → ANALISAR → GERAR
PROPOSTA → CHECKPOINT/APROVAÇÃO quando necessário → APLICAR → RETRY →
VERIFICAR**, limitado ao sistema de ferramentas **já autorizado**.

- **`app/executor/correction.py`** (novo, genérico): `CorrectionEngine`
  + `CorrectionStrategy`/`CorrectionProposal` reais, com estados
  claramente separados (`PROPOSED`, `INVALID`, `REFUSED`, `APPROVED`,
  `APPLIED`, `RETRIED`, `SUCCEEDED`, `FAILED`, `NO_PROPOSAL`,
  `EXHAUSTED`); **planos sucessores imutáveis** (`PLN-…#C1`, `#C2`…;
  tarefa corrigida mantém id/ordem, dependências filtradas; plano
  original intocado — testado); **limites rígidos**: `max_cycles`
  (aplicadas) e `max_total_attempts` (acumuladas) — **nunca retry
  infinito**; `max_cycles=0` desabilita o loop; correção sem
  validação **não executa** (INVALID, nada aplicado, nem pausa);
  recusa ⇒ nada executado depois; falha definitiva ⇒ `FAILED`/
  `EXHAUSTED` + plano `FAILED`. **Não importa `app.tools`**
  (garantido por AST).
- **`app/tools/correction.py`** (novo): `ToolCorrectionStrategy`
  **conservadora** — propõe apenas `create_file → write_file` quando o
  erro é "arquivo já existe"; erros com marcadores de segurança
  (permissão negada, allowlist, fora do workspace, traversal, somente
  leitura, operador de shell…) **nunca** geram proposta (sem bypass);
  `build_proposal_validator` exige tool registrada + permissão
  concedida + sandbox/`TerminalPolicy` aprovando antes de qualquer
  aplicação.
- **`ToolsController`**: `enable_corrections(strategy?, max_cycles=2,
  max_total_attempts=8)` / `disable_corrections` (opt-in do integrador;
  validação dos limites); pendências roteiam transparentemente
  correção × checkpoint de operação (`approve`/`refuse`/`has_pending`/
  `pending_approval`); auditoria JSONL de **todo** ciclo
  (`tool=correction`, `correction_<status>`, sucesso=False para
  desfechos negativos, sem conteúdo sensível).
- **UI 🛡**: card **CORREÇÃO PROPOSTA** (ferramenta de→para, falha de
  execução/verificação, parâmetros original/corrigido); Aprovar aplica
  e segue para o checkpoint da operação; Recusar mantém a falha —
  nada executado depois.
- **Nada além disso**: sem execução arbitrária, shell livre, mouse,
  teclado, screenshot, vision, computer control, Unreal, coding agent,
  acesso fora dos workspaces, bypass de permissões/checkpoints.
  Planner segue sem lógica de execução.

**Validação (2 ambientes):** 771 testes (766 passam + 5 pulam) no
sandbox e na venv limpa; `pyflakes` 0; `pip check` ok; `import main`
ok; harness headless de UI 55/55; auditoria AST/anti-futuro verde.

## Lumen 0.6.3 — Tool Calling / Planner Bridge ✅

A ponte que faltava entre o chat e as ferramentas (diagnóstico 0.6.2:
o chat era puramente conversacional e nenhum pedido chegava ao
Planner/ferramentas). Agora uma solicitação em linguagem natural pode
virar tarefa estruturada — **sem criar nenhum poder novo**:

**CHAT → INTENÇÃO → PLANNER → PLANO (`tool`/`parameters`) → VALIDAÇÃO →
TOOLS CONTROLLER → PERMISSÕES → WORKSPACE → CHECKPOINT → EXECUÇÃO →
VERIFICAÇÃO.**

- **`app/planner/catalog.py`** (novo): allowlist de **protocolo** com as
  ferramentas já existentes (6 filesystem; `run_command` **somente**
  com terminal habilitado). Validação estrita: tool vazia/inventada,
  parâmetros ausentes/desconhecidos/tipos errados, paths absolutos/`..`
  → falha controlada (nada executa, nunca parcialmente).
- **`app/planner/planner.py`**: modo planejamento com ferramentas
  (`create_tool_plan` → `ToolPlanResult` `plan`/`conversation`/
  `invalid`); prompt com a allowlist embutida; tarefas ganham
  `tool`/`parameters` validados.
- **`app/core/bridge.py`** (novo): `ToolCallingBridge` +
  `RequestState` (10 estados: `CONVERSATIONAL`, `PLANNING`,
  `PLAN_READY`, `PLAN_INVALID`, `WAITING_APPROVAL`, `EXECUTING`,
  `VERIFYING`, `COMPLETED`, `FAILED`, `REJECTED`). Conversa segue o
  fluxo clássico (streaming); ação vai ao `ToolsController.run_plan`.
- **`Agent`**: `process_message` (decide conversa × ação via bridge),
  `request_tool_plan`, `set_tools_controller` (injetado pelo `main.py`;
  sem ela o comportamento 0.6.2 é preservado).
- **`MockProvider`**: modo planejador determinístico (offline) — o
  pedido canônico "Crie um arquivo chamado teste_lumen.txt … contendo:
  TESTE LUMEN 0.6.3" gera exatamente `create_file` +
  `{"path": …, "content": …}`; pedidos vagos/destrutivos/injection são
  conversa.
- **Autoridade inalterada**: LLM não é autorização. Permissões (nada
  concedido automaticamente), workspace/sandbox, checkpoints
  (create_file continua pausando para aprovação — agora com o
  **conteúdo** no card), auditoria JSONL e correção 0.6.2 (funciona
  via chat) intactos. Providers 5 preservados; Executor segue sem
  importar `app.tools`; Planner segue sem executar nada.

**Validação (2 ambientes):** 868 testes (863 passam + 5 pulam) no
sandbox E na venv limpa; `pyflakes` 0; `pip check` ok; `import main`
ok; harness headless 55/55; auditoria AST/anti-futuro verde
(`subprocess` só em `terminal.py`; planner/core sem `app.tools`).

## Lumen 0.6.6 — Desfecho pós-aprovação no chat ✅

Correção de UX do fluxo 0.6.3 (diagnóstico: a aprovação do checkpoint
acontecia fora do ciclo do bridge e a janela principal nunca ficava
sabendo do resultado). Agora, depois de APROVAR/RECUSAR na tela 🛡, o
chat exibe a mensagem final (✔ concluído / ✖ falhou / recusa):

- **`app/core/bridge.py`**: `outcome_for_report(request, plan_id,
  report)` público (mesma lógica; `request=None` registra só o desfecho
  na memória linear).
- **`app/ui/tools_dialog.py`**: callback opcional
  `on_plan_finished(report)` (default `None` = comportamento anterior);
  invocado após APROVAR e RECUSAR; falhas do callback não afetam o
  diálogo.
- **`app/ui/main_window.py`**: `_open_tools` fornece
  `_on_plan_finished`, que formata via bridge, injeta `("reply", …)` na
  fila existente e registra na memória linear.
- **Nenhum** sistema novo de eventos/memória; nenhuma mudança em
  permissões/sandbox/registry/executor/checkpoints/ferramentas.

**Validação (2 ambientes):** 880 testes (875 passam + 5 pulam) no
sandbox E na venv limpa; +8 testes de UI pós-aprovação; pyflakes 0;
pip check ok; import main ok; harness 55/55; AST/anti-futuro verde.

## Lumen 0.7 — Coding Agent

> Status (2026-09-01): 11B (`search_files`), 11C (`edit_file`), 11D
> (`run_pytest` — runner estruturado de build/test), 11E (verificação
> real opt-in), 11F (auto-anexo `run_pytest` após WRITE), 11G
> (evidência real em modo corrections), 11H (toggles persistentes de
> automação + UI), 11I (export de relatório de evidências), 11J
> (conselho com evidência nas correções — advice-only) e 11K (snapshot
> "before" + restore manual) entregues.
> Próximos tópicos da trilha (verificação real completa, reparo) —
> **NÃO AUTORIZADOS / NÃO IMPLEMENTADOS**.

- Criar e modificar código; rodar testes; iterar sobre erros.
- Fluxos para projetos de desenvolvimento (git, ambientes, builds).

## Lumen 0.8 — Vision

- Captura de tela e análise por visão computacional.
- Compreensão de janelas, diálogos e estados de aplicações.

## Lumen 0.9 — Mouse + Keyboard

- Controle de mouse e teclado (permissão `COMPUTER_CONTROL`).
- Ações visíveis, limitadas e confirmadas; modo de segurança/kill-switch.

## Lumen 1.0 — Computer Agent

- Autonomia completa com planejamento → execução → verificação.
- Abrir e operar aplicações do dia a dia com checkpoints do usuário.

## Lumen 1.x — Unreal Engine Agent

- Ferramentas específicas para Unreal: criar/abrir projetos, manipular
  Blueprints e assets, disparar builds/cook, ler logs do editor.
- Suporte a fluxos de desenvolvimento de jogos end-to-end.

---

### Princípios valem para todas as fases

1. Permissão antes de poder: sem grant explícito, a ferramenta não roda.
2. Confirmação antes de qualquer ação potencialmente destrutiva.
3. Erros nunca silenciosos: log completo + mensagem clara ao usuário.
4. Testes automatizados acompanham cada incremento.
5. A arquitetura em camadas permanece intocada — só se estende.


## 12. REGRA FINAL

O conteúdo das seções 1–6 deste documento é canônico. As seções 7–8 preservam histórico e evidências antigas para não perder contexto, mas não podem contradizer o estado canônico atual.

**Próxima fase:** F23 — Runtime Integration & State Machine Hardening.
