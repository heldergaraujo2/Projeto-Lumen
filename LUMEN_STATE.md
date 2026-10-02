# LUMEN — ESTADO OFICIAL ATUAL

**Atualização:** 2026-09-30  
**Roadmap/continuidade canônicos:** `docs/LUMEN_MASTER_ROADMAP.md`  
**Estado:** 🟩 F0–F32 com implementação, gates reais aplicáveis e validações correspondentes concluídos; F30 possui validação física real aprovada; F31, F32 e o E2E integrado final estão validados em execução local segura. A validação física não é inferida da CI.

> O roadmap e a continuidade foram consolidados em um único documento. Não usar `docs/ROADMAP.md` ou `docs/LUMEN_CONTINUITY_PHASES.md` como fontes independentes.

## F19–F32 — Auditoria, integração e fechamento

- **F19:** revisão concluída; nenhum defeito estrutural adicional identificado.
- **F20:** corrigidas semântica de maximize/minimize, delta de target e exposição do weight; validada na suíte completa.
- **F21:** corrigida avaliação dirigida por requisitos; FAILOVER e LOCAL_AVAILABILITY agora possuem semântica explícita; validada na suíte completa.
- **F22:** corrigidas identidade imutável de observações, ciclo de vida, retenção de evidências e fechamento explícito; validada na suíte completa.
- **F23:** concluída como **Runtime Integration & State Machine Hardening**. Suíte completa: **1342 passed / 1 skipped / 0 failed**; F0 Validation e F23 Validation verdes. O detector de ambiente permanece fail-closed e não prova validação física.
- **F24:** Evolution Runtime Orchestrator concluída. Suíte completa: **1347 passed / 1 skipped / 0 failed**; Lumen Tests, F0 Validation e F23 Validation verdes.
- **F25:** Provider Runtime Independence concluída. Implementado ProviderRuntime com fallback real, retries bounded, compatibilidade, custo, contexto normalizado, verificação, auditoria, autorização explícita e evidência de tentativas. O OllamaProvider existente continua sendo o provider local oficial e foi integrado sem duplicação. Validação final: **1366 passed / 1 skipped / 0 failed**, compileall SUCCESS, F0 Validation SUCCESS e F23 Validation SUCCESS.
- **F26:** Learning Runtime & Continuous Knowledge concluída. Implementada aprendizagem explícita e contínua por uso, memória persistente, knowledge/experience/strategy, verificação, consolidação, recall seguro e redaction de segredos. Testes dedicados em `tests/test_learning_runtime.py`; documentação em `docs/F26_LEARNING_RUNTIME.md`.
- **Sequência F31/F32 encerrada:** F31 E2E, F32 E2E e teste integrado final passaram. A auditoria final e a consolidação documental foram concluídas. Não criar novo F30, não repetir F31/F32 e não inventar F33 sem decisão arquitetural explícita.

# F32 — CLOSED-LOOP LUMEN EVOLUTION — CURRENT OFFICIAL STATUS

🟩 IMPLEMENTAÇÃO CONCLUÍDA

Entregas:
- ClosedLoopEvolution em app/evolution/closed_loop.py;
- integração deliberativa com F22 ContinuousIntelligenceEvolution;
- abertura explícita do gate F24 EvolutionRuntimeOrchestrator;
- estados bounded: OBSERVING, STABLE, TRIGGERED, PLANNED, WAITING_EVIDENCE, WAITING_APPROVAL, PROMOTED, MONITORED, CLOSED, REJECTED;
- planos vinculados exatamente às evidências que causaram o trigger;
- persistência atômica de metadados e identidade do ciclo;
- digest determinístico;
- histórico bounded;
- testes dedicados em tests/test_closed_loop_evolution.py;
- documentação em docs/F32_CLOSED_LOOP_LUMEN_EVOLUTION.md.

Segurança:
- não executa provider/modelo, ferramenta, código, processo, browser ou driver;
- não concede permissões;
- não altera Policy, Scope, Sandbox, Checkpoint ou Audit;
- não promove sem etapa explícita de aprovação;
- não persiste screenshots, secrets ou conteúdo sensível.

Validação:
- F32 possui testes unitários, negativos, atomicidade, persistência, limites e superfície de segurança;
- F32 E2E local: **PASS — 1 passed**;
- teste integrado final F30→F31→F32: **PASS — 1 passed**;
- validação física Windows/Unreal continua separada.

# F31 — EXPERIENCE & WORKFLOW INTELLIGENCE — CURRENT OFFICIAL STATUS

🟩 IMPLEMENTAÇÃO CONCLUÍDA

Entregas:
- ExperienceTrace/Event e armazenamento persistente bounded;
- compreensão determinística da sequência observada;
- generalização de experiências somente quando todos os eventos são sucesso + verificados;
- abstração de parâmetros divergentes em variáveis declaradas;
- PersistentWorkflowRegistry para persistir workflows e evidências;
- reuse somente após evidência de sucesso verificada;
- adaptação estritamente limitada às variáveis declaradas;
- redaction de segredos antes da persistência;
- integração com WorkflowLearner/Matcher F10 e Learning Runtime F26;
- testes dedicados em tests/test_experience_workflow_intelligence.py;
- documentação em docs/F31_EXPERIENCE_WORKFLOW_INTELLIGENCE.md.

Segurança:
- não executa driver, browser, processo, ferramenta ou workflow;
- não concede Permission;
- não altera Policy, Scope, Sandbox, Checkpoint ou Audit;
- high-risk continua exigindo Human Approval;
- nenhum screenshot ou conteúdo sensível é persistido.

Validação:
- implementação e testes adicionados ao PR F31;
- F31 E2E local: **PASS — 1 passed**;
- teste integrado final F30→F31→F32: **PASS — 1 passed**;
- validação física Windows/Unreal continua separada e não é inferida.

# F30 — UNREAL REAL INTEGRATION — CURRENT OFFICIAL STATUS

🟩 IMPLEMENTAÇÃO CONCLUÍDA / VALIDAÇÃO REAL APROVADA

Entregas:
- descoberta read-only de um único .uproject existente;
- validação do descriptor e estrutura Content/Source/Config/Plugins/Saved;
- descoberta do Unreal Editor por Windows Native;
- inspeção de Content Browser, Blueprint, Output Log e estado PIE;
- operações bounded para Content Browser, Blueprint, C++, build, compile, PIE, logs e recovery;
- operações mutáveis marcadas para aprovação;
- testes dedicados em tests/test_f30_unreal_integration.py;
- documentação em docs/F30_UNREAL_REAL_INTEGRATION.md.

Validação real concluída em 2026-09-30:
- Unreal 5.8 + AgeOfAether + UnrealEditor.exe;
- MCP/Slate real, Snapshot/Observe/WaitFor/Screenshot;
- grounding Slate → Computer Control;
- checkpoint, aprovação e clique físico controlado;
- verificação pós-ação read-only confirmou o estado do Content Browser;
- correção de coordenadas virtuais validada e integrada;
- nenhuma entrada física fora da cadeia oficial.

F30 está encerrada. Não repetir F30 como gate pendente.

# F29 — REAL AUTONOMOUS COMPUTER AGENT — CURRENT OFFICIAL STATUS

🟩 IMPLEMENTAÇÃO CONCLUÍDA / VALIDAÇÃO FÍSICA APROVADA

Entregas:
- VisionComputerAgent em app/computer_control/autonomous_agent.py;
- Goal → Plan → Observe → Target → Action → Verify → Recover → Replan;
- budgets bounded de ciclos, replans e recoveries;
- execução somente pelo ComputerControlService;
- checkpoint obrigatório pausa o loop antes da ação física;
- testes dedicados em tests/test_f29_autonomous_computer_agent.py;
- documentação em docs/F29_REAL_AUTONOMOUS_COMPUTER_AGENT.md.

Nota de evidência: o smoke específico de F29 não deve ser confundido com a validação física de F30. A integração real exercitada em F30 é evidência do caminho compartilhado, mas não substitui um registro específico do smoke F29.

# F28 — REAL VISION + GROUNDING — CURRENT OFFICIAL STATUS

🟩 IMPLEMENTAÇÃO CONCLUÍDA / VALIDAÇÃO REAL APROVADA

Entregas:
- VisionGroundingPipeline em app/computer_control/vision_grounding.py;
- integração screenshot/request → VisionObservation → GroundingEngine → TargetResolver;
- VisionProviderManager e OllamaVisionProvider existentes reutilizados;
- grounding structured-first com threshold, bounds e scope;
- pipeline não executa ações;
- testes dedicados em tests/test_vision_grounding.py;
- documentação em docs/F28_REAL_VISION_GROUNDING.md.

Nota de evidência: a documentação específica de F28 descreve um smoke de provider multimodal real separado. Não tratar esse smoke específico como executado apenas por causa da validação física F30.

# F27 — REAL WINDOWS COMPUTER VALIDATION — CURRENT OFFICIAL STATUS

🟩 IMPLEMENTAÇÃO CONCLUÍDA / GATE FÍSICO APROVADO

Entregas:
- driver nativo real em app/computer_control/windows_driver.py;
- mouse, teclado, foco de janela e screenshot no Windows;
- driver desarmado por padrão;
- testes fail-closed em tests/test_f27_windows_driver.py;
- smoke runner explícito em scripts/f27_windows_smoke.py;
- CI Windows em .github/workflows/windows-validation.yml;
- exportação do driver no pacote app.computer_control;
- documentação em docs/F27_REAL_WINDOWS_VALIDATION.md.

Invariantes:
- o driver não concede Permission;
- o driver não altera Policy, Scope ou Checkpoint;
- input físico exige arming explícito;
- CI Windows não é aceita como prova de desktop físico;
- screenshot é evidência por referência, não conteúdo de auditoria.

Validação automatizada prevista:
- compileall;
- suíte pytest completa em Ubuntu;
- suíte pytest completa em Windows;
- import do driver nativo no Windows;
- testes negativos de driver desarmado e execução fora do Windows.

Nota de evidência: a documentação específica de F27 define um smoke físico separado. A validação física posterior de F30 comprova a cadeia compartilhada e uma ação controlada, mas não deve ser usada para inventar um registro do smoke F27 que não esteja documentado.

## Regra de continuidade

**NÃO CRIE OUTRA LUMEN. ALTERE SEMPRE A LUMEN EXISTENTE.**

---

# F23 — REAL ENVIRONMENT VALIDATION & INTEGRATION READINESS — CURRENT OFFICIAL STATUS

🟩 CONCLUÍDA — GATE DE PRONTIDÃO

Validação de implementação:
- PR #19 mergeada em master;
- merge commit: 35bb3119de4b92beacfee01562a78fd13f021512;
- detector determinístico de ambiente em app/validation/environment.py;
- testes dedicados em tests/test_f23_environment_validation.py;
- CI F23 configurada para Ubuntu + Windows;
- documentação: docs/F23_REAL_ENVIRONMENT_VALIDATION.md;
- regra fail-closed preservada: Windows/display/sessão interativa não equivalem a validação física.

Limites explícitos:
- mouse físico: NOT_EXECUTED;
- teclado físico: NOT_EXECUTED;
- UI Automation físico: NOT_EXECUTED;
- Unreal Engine real: NOT_EXECUTED.

F23 conclui o contrato de prontidão e evidência para ambiente real; não declara hardware ou Unreal testados. A execução física permanece um gate operacional externo e só poderá ser marcada executada mediante evidência real.

F23 não altera PermissionManager, Policy, Sandbox, Checkpoint, Audit ou Scope; não executa drivers, mouse, teclado, browser ou Unreal e não cria bypass.

# F22 — CONTINUOUS INTELLIGENCE EVOLUTION — CURRENT OFFICIAL STATUS

🟩 CONCLUÍDA

Validação final:
- Lumen Tests run 36360593948: **1329 passed / 1 skipped / 0 failed**;
- Lumen F0 Validation run 36360593944: **1329 passed / 1 skipped / 0 failed**;
- compile: SUCCESS;
- PR #18 mergeado;
- merge commit: 3c862af35ca1cf152051b1a20f1bf686db14f2e9.

Correções finais: assessment atômico; trigger/plan one-shot; limiar de degradação numericamente estável; testes de atomicidade, limites e repetição.

F22 fecha o ciclo OBSERVE → ASSESS → DETECT → TRIGGER → PLAN → RESEARCH/ADAPT/STACK → BENCHMARK → SECURITY → HUMAN APPROVAL → PROMOTION/MONITORING → NEW BASELINE.

F22 não executa modelos, ferramentas, código, processos, browser, rede ou drivers; não concede permissões, altera Policy/Sandbox/Checkpoint/Audit, amplia Scope, faz deploy ou promove automaticamente.

**Todas as fases F0–F22 estão concluídas.**


🟨 IMPLEMENTAÇÃO CONCLUÍDA / VALIDAÇÃO CI PENDENTE

Implementação mergeada no PR #17 (`b081f5d1463260eda765b61945f62835c60a1352`).
A CI deste commit ainda não foi exposta pelo conector; a fase só será marcada 🟩 após validação automatizada.

# F21 — PROVIDER INDEPENDENCE — CURRENT OFFICIAL STATUS

🟩 CONCLUÍDA

Validação final:
- Lumen Tests run 36359332055: **1312 passed / 1 skipped / 0 failed**;
- Lumen F0 Validation run 36359332009: SUCCESS;
- compile: SUCCESS;
- PR #16 mergeado;
- merge commit: afcfd3cc2ac97471a043a1fdaeb4a74e9d253583.

**Próxima fase oficial: F22 — Continuous Intelligence Evolution.**

# CURRENT OFFICIAL TRACK — 2026-09-27

**F19 — LUMEN INTELLIGENCE LAB: 🟩 CONCLUÍDA.

**F20 — SELF-OPTIMIZING INTELLIGENCE: 🟩 CONCLUÍDA.****

Entregas:
- IntelligenceCapability + IntelligenceTrack;
- baselines versionados com proveniência;
- IntelligenceResearch e integração ResearchReport;
- hipóteses de evolução de inteligência;
- IntelligenceEvidenceLedger bounded e determinístico;
- integração de evidências do Intelligence Stack F17;
- integração de evidências do Model Adaptation Laboratory F18;
- findings com delta, confiança e detecção explícita de regressão;
- oportunidades de melhoria ligadas a pesquisa;
- workspace delegado ao Evolution/Adaptation Lab em evolution-lab/;
- digest SHA-256 determinístico do estado de inteligência;
- testes de invariantes, isolamento e ausência de superfície de execução.

Validação F19:
- compileall: SUCCESS;
- Lumen Tests: **1278 passed / 1 skipped / 0 failed**;
- Lumen F0 Validation: **1278 passed / 1 skipped / 0 failed**;
- PR #13: validação verde.

F19 não executa modelos, ferramentas, código, browser, rede ou drivers; não treina,
faz inferência, download, deploy, concede permissões, altera Policy/Sandbox/Checkpoint/Audit,
amplia Scope ou promove automaticamente.

**Próxima fase oficial: F20 — Self-Optimizing Intelligence.**

# CURRENT OFFICIAL TRACK — 2026-09-27

**F18 — MODEL ADAPTATION LABORATORY: 🟩 CONCLUÍDA.**

Entregas:
- DatasetSpec com versionamento, splits e limites;
- AdaptationSpec para LoRA, fine-tuning, distillation, pruning, quantization, datasets, curriculum, tool-use, domain adaptation e inference optimization;
- AdaptationExperiment com seed, configuração e limites declarativos;
- workspace experimental isolado sob evolution-lab/;
- AdaptationEvidence com artefatos, testes e chave de reprodutibilidade;
- digest SHA-256 determinístico da evidência;
- AdaptationCandidate compatível com CandidateRegistry/F15;
- benchmark + RegressionDetector;
- SafetyValidator + Human Approval para alto risco;
- invariantes de provider/model/base/target/métrica;
- testes explícitos contra execução, deploy e bypass de segurança.

Validação F18 no PR #12:
- compileall: SUCCESS;
- Lumen Tests: **1259 passed / 1 skipped / 0 failed**;
- Lumen F0 Validation: **1259 passed / 1 skipped / 0 failed**;
- ambos SUCCESS.

O laboratório não treina, executa inferência, baixa modelos, acessa rede, faz deploy, concede permissões, altera Policy, desabilita Audit ou amplia Scope. A promoção continua sob o PromotionGate F15.

**Próxima fase oficial: F19 — Lumen Intelligence Lab.**

# CURRENT OFFICIAL TRACK — 2026-09-27

**F17 — INTELLIGENCE STACK EVOLUTION: 🟩 CONCLUÍDA.**

F16 permanece concluída. F17 adicionou ProviderProfile, ModelProfile, roteamento determinístico, evidência de stack e propostas isoladas de adaptação.

Validação F17: **1244 passed / 1 skipped / 0 failed**; Lumen Tests run 36357083721 SUCCESS; Lumen F0 Validation run 36357083708 SUCCESS; compile SUCCESS.

Validação final da implementação F16:
- primeira CI encontrou 9 falhas na fixture dos testes;
- causa: Candidate é imutável e os testes mantinham a instância PROMOTED após start_monitoring() retornar a instância MONITORED;
- fixture corrigida;
- **1236 passed / 1 skipped / 0 failed**;
- Lumen Tests run **36355972633**: SUCCESS;
- Lumen F0 Validation run **36355972659**: SUCCESS;
- compile: SUCCESS;
- documentação e continuidade atualizadas;
- PR #10 mergeada em master; merge commit 01a2d08881a3537ab3ddf96491b0c64a0998ec0d.

Entregas:
- MonitoringPolicy;
- PostPromotionObservation;
- ContinuousEvolutionMonitor;
- StabilityAssessment;
- detecção determinística de estabilidade/degradação/regressão;
- histórico bounded;
- EvolutionTrigger para iniciar novo ciclo sem executar mudanças;
- ContinuousEvolutionPlanner;
- sincronização de evidências com EvolutionMemory;
- testes de segurança, limites, regressão, recuperação e memória.

Segurança:
- F16 não executa código/processos;
- não faz deploy;
- não chama drivers;
- não concede Permission;
- não altera Policy/Sandbox/Checkpoint/Audit;
- não executa rollback físico;
- não promove automaticamente;
- triggers de melhoria exigem novo ciclo F12–F15;
- alto risco continua exigindo Human Approval.

## O QUE A LUMEN JÁ CONSEGUE FAZER

A trilha oficial já permite à Lumen:
1. representar e observar estado do computador com fingerprint determinístico;
2. identificar alvos por grounding estruturado, priorizando fontes nativas;
3. planejar ações sem entregar o driver diretamente ao modelo;
4. executar Computer Control pela cadeia segura de Permission/Policy/Scope/Checkpoint/Driver/Audit;
5. verificar pós-condições e classificar falhas;
6. realizar recovery bounded sem ampliar permissões ou escopo;
7. detectar regressões;
8. operar objetivos estruturados do Unreal Engine: foco, abrir asset/level, salvar, salvar tudo, Play e Stop;
9. aprender workflows versionados, medir evidências e propor adaptações controladas;
10. orquestrar tarefas multi-etapas dentro de orçamento e aprovação;
11. diagnosticar capacidades, pesquisar evidências fornecidas pelo chamador e gerar planos de melhoria;
12. isolar experimentos em Evolution Laboratory;
13. construir/avaliar candidatos por evidências de build e benchmark;
14. exigir revisão de segurança e aprovação humana antes de promoção;
15. monitorar candidatos promovidos, detectar degradação/regressão pós-promoção e abrir um novo ciclo de melhoria baseado em evidências.

**Limitação física:** CI Linux não é smoke test físico de Windows/Unreal. A validação real de mouse/teclado/UIA/Unreal em uma máquina Windows continua sendo uma etapa de ambiente, não declarada como concluída por esta CI.

# CURRENT OFFICIAL TRACK — 2026-09-27

**F14 — SELF-DIAGNOSTICS + RESEARCH FOR IMPROVEMENT: 🟩 CONCLUÍDA.**

Validação final:
- primeira suíte: 1204 passed / 1 skipped / 1 failed;
- falha corrigida no teste de fronteira de severidade;
- segunda suíte final: **1205 passed / 1 skipped / 0 failed**;
- compile: SUCCESS;
- Lumen F0 Validation run **36354736453**: SUCCESS;
- Lumen Tests run **36354736385**: SUCCESS;
- PR #8 mergeada em master;
- merge commit: `09ec80b500bf4b63efcc085dda2fce5cfeb8b132`.

Entregas:
- SelfDiagnostics determinístico;
- ResearchQuery / ResearchEvidence / ResearchReport;
- ResearchEngine com provider fornecido pelo chamador;
- ImprovementOpportunity;
- ImprovementPlanner;
- vínculo entre diagnóstico, evidência, baseline, risco e plano;
- testes de ausência de superfície de execução;
- documentação em `docs/SELF_DIAGNOSTICS_RESEARCH_IMPLEMENTATION.md`.

Segurança:
- pesquisa é evidência, não autoridade;
- F14 não executa experimentos;
- não acessa drivers;
- não concede Permission;
- não altera Policy/Sandbox/Checkpoint/Audit;
- não promove candidatos;
- runtime estável permanece protegido.

**Próxima fase oficial: F15 — Candidate Build + Benchmark + Promotion.**

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F13 — EVOLUTION LABORATORY: 🟩 CONCLUÍDA.**

Validação final:
- CI `Lumen Tests` run **36354454813**: **1191 passed / 1 skipped / 0 failed**;
- CI `Lumen F0 Validation` run **36354454792**: SUCCESS;
- compile: SUCCESS;
- PR #7 mergeada em `master`;
- merge commit: `5f2f89d9e49f9839a93e79a867b227d83dbf4bbd`.

Entregas:
- Evolution Laboratory isolado;
- workspace por evolução em `evolution-lab/`;
- proteção contra path escape;
- bloqueio de alterações em runtime estável, testes e workflows;
- registro de experimentos sem execução;
- registro de mudanças sem execução;
- Candidate Registry vinculado ao workspace/evolution;
- reutilização do lifecycle F12;
- testes de isolamento e ausência de superfície de execução;
- documentação em `docs/EVOLUTION_LABORATORY_IMPLEMENTATION.md`.

Segurança:
- F13 não executa código/driver;
- não concede Permission;
- não altera Policy/Sandbox/Checkpoint/Audit;
- não promove candidatos;
- não permite workspace apontar para runtime estável.

**Próxima fase oficial: F14 — Self-Diagnostics + Research for Improvement.**

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F12 — EVOLUTION FOUNDATION: 🟩 CONCLUÍDA.**

Validação final:
- primeira CI pós-merge encontrou 1 falha de contrato no validador de IDs;
- suíte dessa primeira execução: **1176 passed / 1 skipped / 1 failed**;
- correção aplicada: regex estrita para `EVOLUTION-000001...`;
- PR #6 adicionou casos de regressão para IDs válidos/inválidos;
- CI final `Lumen Tests` run **36354185197**: **1177 passed / 1 skipped / 0 failed**;
- CI `Lumen F0 Validation` run **36354185342**: SUCCESS;
- PR #6 mergeado em `master`;
- merge commit: `cb4f3610efb0ab57c61fe3aa6f1059a81e84029c`.

Entregas F12:
- Capability Registry + Capability Measurement;
- Self-Diagnostics + Improvement Planner;
- Hypothesis Manager;
- Experiment Manager com máquina de estados bounded;
- Candidate Registry;
- Benchmark Engine + Regression Detector;
- Safety Validator;
- Promotion Manager com Human Approval Gate;
- Rollback Manager;
- Evolution Memory;
- IDs monotônicos `EVOLUTION-000001...`;
- documentação e testes dedicados.

Segurança:
- F12 não executa experimentos;
- não chama drivers;
- não concede Permission;
- não altera Policy/Sandbox/Checkpoint/Audit;
- não enfraquece Security Core;
- aprovação de alto risco permanece humana;
- runtime estável permanece separado da futura camada experimental.

**Próxima fase oficial: F13 — Evolution Laboratory.**

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F12 — EVOLUTION FOUNDATION: 🟨 IMPLEMENTAÇÃO CONCLUÍDA / CI PENDENTE.**

Entregas implementadas:
- Capability Registry + Capability Measurement;
- Self-Diagnostics + Improvement Planner;
- Hypothesis Manager;
- Experiment Manager com máquina de estados bounded;
- Candidate Registry;
- Benchmark Engine + Regression Detector;
- Safety Validator;
- Promotion Manager com aprovação humana explícita;
- Rollback Manager;
- Evolution Memory;
- IDs monotônicos `EVOLUTION-000001...`;
- testes dedicados em `tests/test_evolution_foundation.py`;
- documentação em `docs/EVOLUTION_FOUNDATION_IMPLEMENTATION.md`.

Limite arquitetural: F12 define contratos e gates; não executa experimentos, não modifica runtime estável, não concede Permission, não altera Policy/Sandbox/Checkpoint/Audit e não chama drivers.

A fase só será marcada 🟩 após CI completa e correção de qualquer falha encontrada.

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F11 — AUTONOMOUS MULTI-STEP AGENT: 🟩 CONCLUÍDA.**

Evidência final:
- implementação em app/autonomy/;
- testes dedicados em tests/test_autonomous_multi_step.py;
- primeira CI detectou 7 falhas exclusivamente na fixture dos testes;
- fixture corrigida;
- segunda validação GitHub Actions: **1160 passed / 1 skipped / 0 failed**;
- runs finais: 36353694093 (Lumen F0 Validation) e 36353694099 (Lumen Tests), ambos SUCCESS;
- PR #4 mergeado em master;
- merge commit: fc8b2cfa76edbf69469e26e9ce023fc59f7c5ab9.

Entregas F11:
- AutonomyLimits: orçamento de passos, recoveries e tentativas;
- AutonomyGrant: aprovação humana explícita + scope + orçamento;
- MultiStepTask / MultiStep;
- estado por passo e estado global da execução;
- execução sequencial através de StepExecutor;
- retry/recovery bounded;
- falhas de Permission/Scope terminais;
- bloqueio de passos que exigem aprovação humana adicional;
- descoberta opcional de workflows F10;
- nenhum acesso direto a driver;
- nenhum grant automático de Permission;
- nenhum bypass de Policy, Scope, Checkpoint, Audit ou Verification.

O que a Lumen consegue agora: executar/orquestrar tarefas multi-etapas dentro de um orçamento autorizado, avançar somente após sucesso de cada etapa, interromper em falhas de segurança, aplicar recovery limitado e reutilizar conhecimento de workflows como sugestão.

Limitação: a execução física Windows/Unreal continua sem smoke test no ambiente CI Linux. A F11 valida o orquestrador e seus contratos; não declara hardware Windows testado.

Próxima fase oficial: F12 — Evolution Foundation.

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F10 — WORKFLOW LEARNING: 🟩 IMPLEMENTAÇÃO CONCLUÍDA / VALIDAÇÃO FOCADA CONCLUÍDA.**

Validação desta fase:
- 18 testes focados em tests/test_workflow_learning.py;
- validação comportamental independente dos contratos centrais: OK;
- CI reproduzível adicionada em .github/workflows/tests.yml;
- o conector GitHub disponível nesta sessão não retornou workflow run/status para os commits F10; portanto nenhum número de pytest CI é inventado;
- a última suíte CI comprovada antes da F10 permanece F9: 1132 passed / 1 skipped / 0 failed.

Validação implementada:
- workflow knowledge versionado e com fingerprint determinístico;
- registro de evidências de sucesso/falha/inconclusivo;
- reutilização bloqueada quando a última execução falha;
- matcher determinístico e fail-closed;
- adaptação limitada a variáveis declaradas, sem inserir/remover passos;
- workflows de alto risco marcados para Human Approval;
- F10 não possui acesso a driver, não concede Permission, não cria Checkpoint e não altera Policy/Sandbox/Audit;
- testes dedicados: tests/test_workflow_learning.py;
- documentação: docs/WORKFLOW_LEARNING_IMPLEMENTATION.md;
- CI reproduzível adicionada em .github/workflows/tests.yml;
- última validação anterior preservada: F9 — 1132 passed / 1 skipped / 0 failed.

**Resultado arquitetural:** a Lumen agora consegue aprender workflows como conhecimento/plano reutilizável a partir de sequências observadas, guardar evidências, localizar workflows compatíveis e gerar adaptações controladas. A execução futura continua obrigatoriamente na cadeia F7 e a confirmação do resultado na F8.

**Limitação explícita:** a validação física Windows/Unreal continua pendente; CI Linux não constitui smoke test físico do Windows.

**Próxima fase oficial:** F11 — Autonomous Multi-Step Agent.

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F9 — UNREAL ENGINE AGENT: 🟩 CONCLUÍDA.**

Validação:
- F9 implementada diretamente no master;
- testes dedicados: tests/test_unreal_agent.py;
- CI final F9: run 36352773401 — **1132 passed / 1 skipped / 0 failed**.
- CI Linux não constitui smoke test físico do Unreal Editor no Windows.

Entregues:
- UnrealProject + janela autorizada;
- UnrealAgent/UnrealPlan/UnrealAction;
- foco explícito do editor;
- Open Asset / Open Level / Save / Save All / Play / Stop;
- pós-condições F8;
- conversão não-executora para ActionPlan/CCActionRequest;
- fail-closed para objetivos ambíguos;
- documentação F9.

**Próxima fase oficial:** F10 — Workflow Learning.

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F7 — SECURE COMPUTER CONTROL: 🟩 CONCLUÍDA.**

Validação funcional:
- última CI verde antes da documentação final: run 36351694127
- commit: 7c681946e55a00efe908510c101a476def90c32c
- pip check: OK
- compileall: OK
- suíte completa: **1104 passed / 1 skipped / 0 failed**

Entregues:
- PermissionManager + CC Policy + CCScope;
- checkpoint one-shot CC-CP-XXXXXX;
- fingerprint da requisição;
- aprovação vinculada ao scope e à ação;
- proteção contra replay;
- revalidação de região/target no instante da execução;
- auditoria metadata-only;
- integração com GroundedTarget;
- fail-closed para ações não suportadas;
- testes de aprovação, recusa, replay, mismatch, escopo, orçamento, permissão e falhas;
- docs/SECURE_COMPUTER_CONTROL_IMPLEMENTATION.md.

Observação de validação: a CI é executada em ambiente Linux e, portanto, não constitui smoke test físico de mouse/teclado no Windows. O backend Windows permanece coberto por testes compatíveis/lazy; validação física Windows continua sendo necessária antes de declarar suporte operacional de produção.

**Próxima fase oficial:** F8 — Verification + Recovery + Regression.

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F6 — GROUNDING ENGINE: 🟩 CONCLUÍDA.**

Validação funcional antes da documentação:
- GitHub Actions run: 36351256417
- CI: **1094 passed / 1 skipped / 0 failed**
- pip check: OK
- compileall: OK

Entregues na F6:
- GroundingEngine estruturado-first;
- elegibilidade antes da priorização;
- validação de confiança, screenshot, região e janela;
- normalização determinística de labels;
- adaptação de VisionObservation;
- adaptação de NativeElement;
- deduplicação;
- fallback seguro entre fontes;
- integração com TargetingEngine;
- testes focados;
- docs/GROUNDING_ENGINE_IMPLEMENTATION.md.

A F6 não executa ações. O resultado é somente um GroundedTarget/TargetResolution. Permission, Policy, Checkpoint, Computer Control, Audit e Verification permanecem nas fases posteriores.

**Próxima fase oficial:** F7 — Secure Computer Control.

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F5 — VISION PROVIDER: 🟩 CONCLUÍDA.**

Validação final da F5:
- GitHub Actions run: 36350965147
- commit da documentação final: 78f81f2136d6f0e4b88c285339069f7c831c62f2
- pip check: OK
- compileall: OK
- suíte completa: **1084 passed / 1 skipped / 0 failed**
- documentação: docs/VISION_PROVIDER_IMPLEMENTATION.md

Entregues:
- VisionProvider independente;
- JsonVisionProvider com validação estruturada;
- OllamaVisionProvider configurável, padrão qwen3-vl:8b;
- limites de entrada/saída;
- tratamento de erros de transporte/payload;
- VisionProviderManager para múltiplos modelos;
- testes determinísticos sem depender de Ollama real.

A F5 produz percepção estruturada. Grounding continua separado e pertence à F6.
Computer Control físico continua protegido pelas camadas posteriores.

**Próxima fase oficial:** F6 — Grounding Engine.

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F4 — WINDOWS NATIVE INTELLIGENCE: 🟩 CONCLUÍDA.**

Validação final da F4:
- GitHub Actions run: 36350720539
- commit de implementação/documentação: 8a665b26a493cb7374ed8dd68ac5cc6ab6df19b9
- pip check: OK
- compileall: OK
- suíte completa: **1073 passed / 1 skipped / 0 failed**
- documentação: docs/WINDOWS_NATIVE_INTELLIGENCE.md

Entregues:
- app/computer/windows_native.py
- app/computer/windows_uia.py
- enumeração e correspondência de janelas;
- UI Automation estruturada e traversal limitado;
- NativeElement → GroundedTarget;
- NativeActionRequest sem execução física.

A F4 não cria autoridade paralela: não concede permissões nem executa mouse,
teclado ou Invoke. A execução física permanece na cadeia segura planejada para F7.

**Próxima fase oficial:** F5 — Vision Provider.

---

# CURRENT OFFICIAL TRACK — 2026-09-27

**F3 — COMPUTER INTELLIGENCE: 🟩 CONCLUÍDA.**

Última validação da F3:
- GitHub Actions run: 36350436470
- commit validado: f96c4004f066f9612d2239ba7062a69f81e49dd0
- pip check: OK
- compileall: OK
- suíte completa: **1065 passed / 1 skipped / 0 failed**
- documentação: docs/COMPUTER_INTELLIGENCE_IMPLEMENTATION.md

A F3 adiciona app/computer/ com percepção estruturada, fingerprint de estado,
targeting/grounding, ActionIntent/ActionPlan, resolução para CCActionRequest,
verification e recovery limitado. A camada não possui PermissionManager,
drivers ou autoridade para ampliar escopo; execução permanece fora desta camada.

**Próxima fase oficial:** F4 — Windows Native Intelligence.

> Este bloco é a referência de estado atual desta trilha. O restante deste
> arquivo preserva o histórico técnico legado e registros anteriores.

---

# LUMEN STATE

> **Estado oficial do projeto Lumen.** Este arquivo descreve exatamente onde o
> desenvolvimento está. Deve ser atualizado ao final de cada versão para
> refletir o estado REAL do projeto — nunca o estado desejado.

---

## MARCO ATUAL — F2 TOOL / AGENT PROTOCOL

**Status: 🟩 CONCLUÍDA — 2026-09-27.**

A F2 foi finalizada após correção das falhas encontradas durante a validação. CI final: 1052 passed, 1 skipped, 0 failed; pip check OK; compileall OK. O bridge permanece agnóstico de app.tools e a execução de ToolCall em produção passa pelo gateway que converte a intenção em Plan, preservando permissões, sandbox, checkpoint, auditoria e verificação.

Próxima fase oficial: **F3 — Computer Intelligence**.

A F2 está implementada diretamente no repositório oficial. Foi criado o contrato estruturado ToolCall/ToolDefinition/ToolExecutionResult/ToolProtocol, com validação fail-closed de ferramenta, campos, parâmetros, tipos e obrigatoriedade. A execução de produção não chama ToolRegistry diretamente: o gateway transforma ToolCall em Plan e usa ToolsController.run_plan, preservando PermissionManager, sandbox, checkpoint, auditoria e verificação. O bridge agora aceita ToolCall estruturado e entrega ao gateway seguro.

Arquivos principais: app/tools/protocol.py, app/tools/control.py, app/core/bridge.py, tests/test_tool_protocol.py, tests/test_tool_call_gateway.py, docs/TOOL_AGENT_PROTOCOL.md.

Próximo passo de validação: CI completo. Só após 100% da suíte passar a F2 será marcada 🟩.

## MARCO ATUAL — F1 OLLAMA PROVIDER

**Status: 🟩 CONCLUÍDA** — 2026-09-27.

A F1 foi implementada diretamente no repositório oficial:
- Provider local Ollama registrado no factory de AI Providers;
- API HTTP local via /api/chat com streaming NDJSON;
- histórico + system prompt normalizados para AIResponse;
- uso de tokens e finish_reason quando fornecidos pelo daemon;
- health_check() e list_models();
- timeout e classificação de falhas de rede, timeout, servidor e modelo;
- configuração LUMEN_OLLAMA_BASE_URL e LUMEN_OLLAMA_KEEP_ALIVE;
- modelo padrão qwen2.5-coder:7b-instruct-q8_0;
- nenhum pull automático de modelo e nenhuma API key necessária;
- testes unitários do Provider, streaming, usage, health, erros, registro e configuração;
- documentação em docs/OLLAMA_PROVIDER.md.

**Evidência de validação:** suíte CI do GitHub é a autoridade para o teste completo. A validação do daemon/modelo real continua sendo um teste de ambiente que requer Ollama instalado e o modelo disponível na máquina Windows do projeto.

## VERSION

**0.6.8** *(base oficial da fase atual — Persistência opt-in do
Execution State; inclui todo o histórico: 0.6.7 Planos multi-tarefa
via chat + data-flow `${Tn.data.campo}` (Fases 7/8B), 0.6.6 Desfecho
pós-aprovação no chat, 0.6.3 Tool Calling / Planner Bridge (+2
hotfixes), 0.6.2 Correção Automática Controlada, 0.6.x UI de Terminal,
0.6 Terminal Tools, 0.5.x UI de Workspaces/Permissões/Checkpoints/
Auditoria, 0.5 Filesystem Tools, 0.4.x Planner+Executor, 0.3 Advanced
Memory, 0.3.x Provider Expansion. Sobre a 0.6.8 concluíram-se, SEM
bump de versão, as fases internas 9A×2, 9B, 10A, 10B, 11A, 11B, 11C,
11D, 11E, 11F, 11G, 11H, 11I, 11J e 11K — ver "ESTADO ATUAL" a seguir)*

## STATUS

**CONCLUÍDA ✅ (0.6.8 + fases internas 9A–11K)** *(atualizado em
2026-09-01 — **995 passed + 5 skipped, 0 failed** (1000 coletados; 5
skips ambientais: SDKs google-genai/groq/together ausentes, keyring
ausente, Tkinter sem display). Registros anteriores preservados:
pós-11J (2026-08-31): 990+5/0; pós-11I (2026-08-31): 989+5/0;
pós-11H (2026-08-31): 987+5/0;
pós-11G (2026-08-31): 982+5/0; pós-11F (2026-08-31): 980+5/0;
pós-11E: 977+5/0; pós-11D: 973+5/0; pós-11C (2026-08-30): 967+5/0;
0.6.6 (2026-08-28): 875+5 na dev E na venv limpa — 880 no total)*

## ESTADO ATUAL (2026-09-01 — pós-11K)

- **Versão do código:** `0.6.8` (`app/__init__.py`). As fases 9A–11J
  foram entregues SEM bump de versão (engenharia interna).
- **Suíte completa:** **995 passed / 5 skipped / 0 failed** (1000
  coletados — medida após a 11K: +5 de snapshot-before +
  restore_snapshot, testes focados 084/087). Registros anteriores
  preservados: pós-11J (2026-08-31): 990 passed / 5 skipped / 0 failed
  (995 — +1 de correção com evidência (advice-only)); pós-11I
  (2026-08-31): 989 passed / 5 skipped / 0 failed (994 — +2 de export
  de relatório
  (ON/OFF + sanitização)); pós-11H (2026-08-31): 987 passed / 5
  skipped / 0 failed (992); pós-11G (2026-08-31): 982 passed / 5
  skipped / 0 failed (987); pós-11F (2026-08-31): 980 passed / 5
  skipped / 0 failed (985); pós-11E: 977 passed / 5 skipped / 0 failed
  (982); pós-11D: 973 passed / 5 skipped / 0 failed (978) —
  histórico).
- **Fases internas concluídas sobre a 0.6.8:** 9A×2 (auditorias
  read-only), 9B (persistência opt-in do execution state — default
  OFF), 10A (spec Advanced Planning), 10B (MVP: guardrails R5, Stage 2
  conservador R1, data-flow R3, success_criteria R2; R4 adiado),
  11A (auditoria + spec Coding Agent), 11B (tool `search_files`
  READ-only: 19 testes dedicados; PROBE oficial 22/22), 11C (tool
  `edit_file`: edição cirúrgica com ocorrência exatamente 1; ver
  abaixo), 11D (tool `run_pytest` + checkpoint + catálogo; ver
  abaixo), **11E (verificação real via `run_pytest` + toggle opt-in;
  ver abaixo)**, **11F (auto-anexo de `run_pytest` após WRITE; ver
  abaixo)**, **11G (evidência real em modo corrections; ver
  abaixo)**, **11H (toggles persistentes de automação + UI; ver
  abaixo)**, **11I (export de relatório de evidências; ver abaixo)**,
  **11J (correções com evidência — advice-only; ver abaixo)**,
  **11K (snapshot "before" + restore; ver abaixo)**.
- **`search_files`:** 7ª tool de filesystem no registry default
  (EXECUÇÃO ✅) e **presente no Planner Catalog**
  (`app/planner/catalog.py` — PLANEJAMENTO AUTOMÁTICO ✅). Nenhuma
  mudança de runtime/permissões na tool.
- **`edit_file` (11C — IMPLEMENTADA + TESTADA, concluída):** 8ª tool
  de filesystem (`app/tools/edit_file.py`, permissão **WRITE**),
  substituição literal com **ocorrência exatamente 1** (0 ⇒
  `NO_MATCH`; ≥2 inclusive sobrepostas ⇒ `MULTIPLE_MATCHES`; nada é
  escrito em falha), recusa binários/arquivos grandes (>1 MiB default). É
  **destrutiva** (`FILESYSTEM_DESTRUCTIVE_TOOLS`) ⇒ **checkpoint
  obrigatório antes de escrever** (aprovação aplica a edição; recusa
  mantém o arquivo intacto — provado em testes de integração). Está
  no **Planner Catalog** (PLANEJAMENTO AUTOMÁTICO ✅). Spec:
  `docs/SPEC-11C-EDIT_FILE.md`.
- **`run_pytest` (11D — IMPLEMENTADA + TESTADA, concluída):** tool
  dedicada (`app/tools/run_pytest.py`, permissão **TERMINAL**) que roda
  a suíte pytest do workspace de forma estruturada: subprocesso
  controlado (sem shell, fora da `TerminalPolicy` por design —
  python/pytest seguem em `FORBIDDEN_COMMANDS`), `path` relativo
  confinado no sandbox, `-k` restrito, `maxfail` 1..10, `timeout_s`
  10..600. **Checkpoint obrigatório antes de executar** (aprovação
  executa; recusa ⇒ tarefa SKIPPED sem executar — provado em testes de
  integração). Registrada no registry **somente com terminal
  habilitado** (mesma condição de `run_command`) e **presente no
  Planner Catalog** apenas com `include_terminal=True`. Saída
  estruturada (`exit_code`, `summary_line`, `truncated`, `duration_s`)
  sem vazar output completo no audit. Spec:
  `docs/SPEC-11D-BUILD_TEST.md`.
- **Verificação real (11E — IMPLEMENTADA + TESTADA, concluída):**
  opt-in no `ToolsController` (`enable_verification("pytest_result")`
  / `disable_verification()`; default OFF = sem verificação): o
  `PytestResultVerifier` (`app/executor/verification.py`) é
  **interpretativo — NÃO executa nada** (sem subprocess/shell; spec
  11E §3): a verificação real ocorre via task **`run_pytest`** no
  plano (TERMINAL + checkpoint, 11D) e o verifier apenas lê o JSON do
  `ToolResult` (`exit_code`, `summary_line`, `timed_out`).
  `applied=False` para tasks não aplicáveis mantém `TaskRun.verified=
  None` (sem marca, sem rejeição); `applied=True` + verde ⇒
  `verified=True`, vermelho ⇒ task `REJECTED` + plano `FAILED`
  (fail-fast). Spec: `docs/SPEC-11E-REAL_VERIFICATION.md`.
- **Auto-anexo `run_pytest` após WRITE (11F — IMPLEMENTADA + TESTADA,
  concluída):** `ToolsController.run_plan` anexa automaticamente 1
  task final `run_pytest` (`path="tests"`, depende de **todas** as
  tasks anteriores — executa por último) **antes de executar**, quando
  (a) terminal habilitado, (b) verificação 11E habilitada e (c) o
  plano contém WRITE (`write_file`/`create_file`/`delete_file`/
  `edit_file`). Idempotência: não anexa se `run_pytest` já estiver no
  plano (e sem as condições o plano executa inalterado). Guardrail:
  plano com 12/12 tasks + anexo necessário ⇒ **falha antes de
  executar** (FAILED, tudo SKIPPED, nenhuma tool roda — provado em
  testes). Spec: `docs/SPEC-11F-AUTO_PYTEST_AFTER_WRITE.md`.
- **Evidência em modo corrections (11G — IMPLEMENTADA + TESTADA,
  concluída):** em modo corrections o verifier 11E agora se aplica —
  o branch de `run_plan` passa `verifier_factory` ao
  `CorrectionEngine`, de modo que pytest vermelho vira task
  `REJECTED` (não `DONE`), e cada sucessor `#C` passa por um hook
  `plan_transform` que reutiliza a regra 11F para manter a evidência
  `run_pytest` no final quando aplicável (idempotente — sem
  duplicar; respeita o guardrail de 12 tasks — falha controlada,
  sem executar o sucessor, se não puder anexar). Sem bypass: pytest
  segue somente via task `run_pytest` com checkpoint. Spec:
  `docs/SPEC-11G-CORRECTIONS_EVIDENCE.md`.
- **Toggles persistentes de automação (11H — IMPLEMENTADA + TESTADA,
  concluída):** `ToggleStore` (`app/tools/toggles_store.py`) persiste
  em `data/agent_toggles.json` (escrita atômica, schema `version: 1`,
  **fail-closed**: arquivo ausente/corrompido ⇒ tudo OFF, sem
  exceção) as flags `corrections_enabled`/`verification_enabled` —
  **SÓ capacidade: nunca concede permissão** (TERMINAL segue
  explícito por sessão, regra 0.6.x). O `ToolsController` carrega e
  aplica os toggles no `__init__` (parâmetro `toggles_file`;
  `set_corrections_enabled`/`set_verification_enabled` aplicam na
  hora + persistem + auditam `tool="toggles"`) e a UI 🛡 ganhou a
  seção **AUTOMAÇÃO (11H)** — toggles que refletem o controller ao
  abrir e persistem ao clicar (permissões inalteradas). `main.py`
  passa `toggles_file=settings.data_dir / "agent_toggles.json"`.
  Spec: `docs/SPEC-11H-SETTINGS_UI_TOGGLES.md`.
- **Export de relatório de evidências (11I — IMPLEMENTADA + TESTADA,
  concluída):** opt-in `export_execution_reports` (Settings/env
  `LUMEN_EXPORT_EXECUTION_REPORTS`, **default OFF** — bit-a-bit atual)
  que, em estado terminal (COMPLETED/FAILED), exporta via `_final`
  (best-effort — **falha não quebra a execução**) um JSON **sanitizado**
  em `data_dir/reports/<plan_id_sanitizado>.json` contendo `plan` +
  `execution_report` + `correction_history` + auditoria **filtrada por
  `plan_id`** (módulo puro `app/tools/report_export.py`; reutiliza a
  sanitização do 9B — segredos redigidos, strings truncadas, sem
  stdout). Sem execução, sem permissões. Spec:
  `docs/SPEC-11I-REPORT_EXPORT.md`.
- **Correções com evidência (11J — IMPLEMENTADA + TESTADA,
  concluída):** a estratégia **default** de `enable_corrections` agora
  é `EvidenceCorrectionStrategy` **sobre** `ToolCorrectionStrategy`
  (`app/tools/correction.py`; strategy custom fornecida nunca é
  sobrescrita). Para falhas em `run_pytest` (REJECTED/FAILED), ela
  extrai a evidência real (`exit_code`/`summary_line`/`timed_out`/
  `truncated`) do JSON do `ToolResult` em `run.result` (somente
  parse — **sem execução extra**) e produz **conselho**
  (`corrected_task=None`) registrado no ciclo de correção (JSONL via
  `_audit_cycle`; relatório 11I via `correction_history`) — o ciclo
  encerra **sem pausa** (nada é aplicado, sem card). Sem auto-replanning
  (R4 continua proíbido); correções **com tarefa** continuam exigindo
  aprovação explícita. +1 teste (`test_tools_correction.py`); spec:
  `docs/SPEC-11J-EVIDENCE_CORRECTIONS.md`.
- **Snapshot "before" + restore (11K — IMPLEMENTADA + TESTADA,
  concluída):** feature **opt-in (default OFF — bit-a-bit)** no
  `ToolsController` (`enable_snapshots`/`snapshots_dir`/
  `snapshot_max_bytes`; o `SnapshotStore` tem efeitos colaterais zero no
  construtor — nada nasce em disco no startup). Com ON, para as tools
  **destrutivas** de filesystem (`FILESYSTEM_DESTRUCTIVE_TOOLS`), o
  handler faz snapshot **before** do alvo — **depois do checkpoint
  aprovado** (a pausa é anterior ao handler) e **antes** da tool —
  **best-effort** (falha nunca interrompe a execução), guardado em
  `data_dir/snapshots/<safe_plan_id>/<task_id>/` (`manifest.json` +
  `before.bin`; alvo inexistente ⇒ `existed_before=False`; acima do
  teto ⇒ manifest sem cópia, `skipped_reason`). Auditoria registra
  **somente metadados** (`operation="snapshot_before"` — nunca
  conteúdo). Tool `restore_snapshot` (permissão **WRITE**;
  `app/tools/restore_snapshot.py`) para rollback **manual**:
  `existed_before=True` → restaura os bytes do `before.bin`
  (`bytes_restored` no resultado); `existed_before=False` → desfaz o
  create (delete idempotente — `already_gone` se o arquivo já não
  existe); manifest ausente/inválido ⇒ falha honesta (sem restore
  especulativo). **Checkpoint pré-validado**: pausa somente quando o
  restore é viável (WRITE concedida + parâmetros + manifest existe +
  sandbox/policy permitem a operação no alvo); inviável ⇒ a task falha
  direto com o motivo (sem aprovação decorativa). Registrada no
  registry **independentemente do terminal** (tool não-terminal).
  +5 testes focados (084/087: `test_tools_control.py`/
  `test_tools_correction.py`) + lista de tools em
  `test_terminal_integration.py` atualizada; regressão completa verde
  (1000 coletados). Spec: `docs/SPEC-11K-SNAPSHOT_ROLLBACK.md`.
- **Próximos tópicos da trilha Coding Agent (11A): NÃO AUTORIZADOS**
  (reparo via CorrectionEngine, wiring Settings→Planner). Build/test
  estruturado foi entregue na 11D (`run_pytest`), a verificação real
  (opt-in) na 11E, o auto-anexo após WRITE na 11F, a evidência em
  modo corrections na 11G, os toggles persistentes (Settings/UI) na
  11H, o export de relatório de evidências (opt-in) na 11I, o conselho
  com evidência nas correções (advice-only) na 11J e o snapshot
  "before" + restore (opt-in) na 11K.
- **Proibições vigentes preservadas:** R4 (replanning automático) e
  Computer Control / vision / Unreal / Blueprint / C++ (F17).
- **Docs:** LUMEN_STATE sincronizado com a 11K; README/ROADMAP
  sincronizados com a 11H (987/992) — doc sync de README/ROADMAP
  pós-11I a 11K pendente nos comandos seguintes.

## OBJECTIVE — 0.6.3 (histórico)

Implementar o **Tool Calling / Planner Bridge** (0.6.3, autorização
explícita com 20 fases): a ponte CHAT → INTENÇÃO → PLANNER → PLANO
(`tool`/`parameters`) → VALIDAÇÃO → TOOLS CONTROLLER → PERMISSÕES →
WORKSPACE → CHECKPOINT → EXECUÇÃO → VERIFICAÇÃO. Permitir que
linguagem natural ("Crie um arquivo chamado teste_lumen.txt …
contendo: TESTE LUMEN 0.6.3") gere tarefa estruturada e chegue ao
sistema de ferramentas **já existente** — SEM Coding Agent, SEM novos
poderes, SEM ampliar filesystem/terminal, SEM execução arbitrária;
infraestrutura 0.6.0/0.6.1/0.6.2 como autoridade final. Allowlist
explícita de ferramentas no Planner (só as existentes; `run_command`
apenas com terminal habilitado; JAMAIS `execute_anything`/`run_python`/
`run_shell`/`arbitrary_command`); validação total ANTES de executar
(existir/allowlist/formato/tipos/desconhecidos/vazia/arbitrária/
contornos de Registry/permissões/workspace/checkpoints); saída inválida
= falha controlada, nunca execução parcial; chat distingue conversa ×
ação **via provedor** (sem regex no caminho principal); MockProvider
determinístico (só simula a inteligência do Planner); 5 providers
preservados (lógica de um único LLM jamais no Executor); Agent entrega
plano válido ao controller sem lógica de filesystem; 10 estados
(CONVERSATIONAL…REJECTED); "pediu" ≠ "autorizou" (permissões jamais
automáticas); checkpoints preservados (create_file pausa; recusa não
executa; sem bypass via Planner); verificação pós-execução; correção
somente via CorrectionEngine existente (finita); memória não é
autorização nem comando; testes anti-prompt-injection; imutabilidade
dos planos; teste manual preparado (MockProvider + workspace + WRITE +
mensagem canônica → card CRIAR ARQUIVO com conteúdo + APROVAR/RECUSAR
→ arquivo criado + auditoria + verificação); bateria completa 2 venvs;
docs 4; **PARE COMPLETAMENTE** — nada de 0.7+/Vision/Mouse/Teclado/
Computer Control/Unreal/novas ferramentas.

## OBJECTIVE — 0.6.2 (histórico)

Implementar a **Correção Automática Controlada** (0.4.x, protocolo de
12 itens com autorização explícita): SOMENTE o ciclo `EXECUTAR →
VERIFICAR → SUCESSO continua / FALHA → ANALISAR → GERAR PROPOSTA →
CHECKPOINT/APROVAÇÃO quando necessário → APLICAR → RETRY → VERIFICAR`,
via `CorrectionEngine` genérico em `app/executor/correction.py`
(**sem importar `app.tools**`) + `ToolCorrectionStrategy` conservadora
em `app/tools/correction.py` (única proposta real: `create_file →
write_file` quando o arquivo já existe; erros de segurança **nunca**
geram proposta) + validador (tool registrada + permissão concedida +
sandbox/TerminalPolicy) — **sem bypass**; `CorrectionStrategy` deixa de
ser Noop **limitada ao sistema de ferramentas já autorizado**;
limites rígidos (`max_cycles`, `max_total_attempts`, nunca retry
infinito, `FAILED`/`EXHAUSTED` apropriado, cada correção registrada em
auditoria JSONL, tentativa com resultado verificável); 8+ estados
separados; Planner sem lógica de execução; planos imutáveis
(sucessores `#C1`); opt-in no `ToolsController` + card de correção na
UI 🛡; testes para os 16 cenários exigidos; bateria completa 2 venvs;
docs 4; **PARE COMPLETAMENTE** ao final — sem nada de 0.7+, Planner
inteligente de tools, Coding Agent, Vision, Mouse/Teclado, Computer
Control ou Unreal.

## OBJECTIVE — 0.6.x (histórico)

Implementar a **interface de gerenciamento seguro do Terminal** (0.6.x)
— SOMENTE camada visual/controle sobre a 0.6.0, via fachada
`ToolsController` (nenhuma lógica de segurança na UI): visualizar se
`TERMINAL` está concedida; conceder/revogar TERMINAL **explicitamente**
(métodos dedicados auditados `grant_terminal`/`revoke_terminal`; o
caminho genérico `grant_permission` segue rejeitando TERMINAL;
`COMPUTER_CONTROL` inconcedível por qualquer via; concessão vale só na
sessão — nunca persistida/restaurada); deixar claro na UI o que
TERMINAL permite (apenas comandos da allowlist, dentro dos workspaces,
com timeout/limite de saída/ambiente sem segredos/checkpoint;
shells/interpretadores/rede proibidos permanentemente); visualizar
allowlist; adicionar comando (aprovação obrigatória por default ou
execução direto; denylist rejeita) e remover; desabilitar terminal
(esvazia allowlist); **persistência** `data/terminal.json` (atômica;
arquivo só nasce no 1º cadastro; **fail closed**: ilegível ⇒
desabilitado, entrada inválida/denylistada ⇒ descartada; defaults
restaurados; permissão NUNCA persistida); card de aprovação com
**comando, argumentos, cwd e timeout** explícitos; auditoria JSONL de
todas as ações administrativas (`terminal_grant/revoke`,
`allowlist_add/remove`, `terminal_enable/disable` — inclusive
tentativas rejeitadas); manter TODAS as proteções da 0.6.0 intocadas;
checkpoints intactos; startup sem concessão automática nem arquivo;
nada de 0.7+.

## OBJECTIVE — 0.6 (histórico)

Implementar a **primeira fundação de Terminal Tools** (0.6) — execução
de comandos **controlada, limitada e auditável**, com a mesma filosofia
do Filesystem Tools: `run_command` via `ToolRegistry` com permissão
`TERMINAL` (porteio antes de qualquer código da ferramenta);
**allowlist explícita** de comandos (`AllowedCommand`: nome,
`full_path` opcional com match exato, argumentos fixos opcionais,
`requires_approval`, timeout/limites próprios) — comando fora da lista
é **bloqueado antes da execução** (decisão mais rígida que o ROADMAP
original, que previa confirmação para fora da lista); **denylist
permanente** (shells, interpretadores, executores de subcomando,
builders, escalonamento, destrutivos/administrativos e **rede** —
jamais allowlistáveis; normalização anti-alias `python.exe`/`/bin/sh`);
**sem shell** (argv lista; operadores `&&`/`|`/`;`/`>`/`$(` e
redirecionamentos bloqueados em argumentos salvo permissão explícita;
argumentos-perigo `-exec`/`/c`/`-EncodedCommand` bloqueados);
**sandbox do diretório de trabalho** (cwd confinado aos workspaces;
argumentos com `..` ou caminho absoluto fora bloqueados); **timeout
obrigatório** (default 10 s, teto 60 s, mata o processo);
**limite de saída** stdout/stderr (64 KiB, trunca e falha honesto);
captura de `stdout`/`stderr`/`exit_code`; `ToolResult` estruturado;
erros controlados (comando inexistente, cwd inválido etc.);
**checkpoint antes de comandos sensíveis** (default TODO comando;
`PrevalidatedTerminalCheckpoints` — somente operações viáveis, mesma
lógica 0.5.1; recusa ⇒ nada roda); **auditoria JSONL** (comando
sanitizado, cwd, exit code, desfecho, erro, timestamp, tarefa/plano —
nunca stdout/stderr/segredos); **integração com `ToolsController`**
(`enable_terminal`/`allow_command`/`disable_terminal` — opt-in, nada no
startup); ambiente filho sanitizado (sem `*KEY*`/`*TOKEN*`/`*SECRET*`/
`*PASSWORD*`); Executor/Planner/providers/memória/UI existente
intactos; **nada de 0.7+** (coding agent, edição inteligente, vision,
screenshot, mouse, teclado, computer control, Unreal, controle
irrestrito) e **Planner autônomo avançado**.

---

## COMPLETED

## COMPLETED — 0.6.6 (Desfecho pós-aprovação no chat)

### Lumen 0.6.6 — o chat fica sabendo do resultado ✅

- **Causa corrigida**: a aprovação do checkpoint roda fora do ciclo do
  bridge (`ToolsDialog._approve → ToolsController.approve`) e nenhum
  canal levava o `ExecutionReport` de volta à janela principal — o
  texto final ("✔ Plano … concluído") só existia dentro de
  `bridge.process()`, que já havia retornado no `WAITING_APPROVAL`.
- **`app/core/bridge.py`**: `outcome_for_report()` público (mesma
  lógica; `request=None` registra apenas o desfecho na memória
  linear).
- **`app/ui/tools_dialog.py`**: `on_plan_finished(report)` opcional
  (default `None` ⇒ comportamento anterior); chamado após APROVAR e
  RECUSAR; exceções do callback só geram log.
- **`app/ui/main_window.py`**: `_open_tools` injeta
  `_on_plan_finished` (formata via bridge → fila `("reply", …)`
  existente → memória linear).
- **Versão 0.6.6**; testes novos (8) em `tests/test_post_approval_ui.py`
  (pausa A; callback na montagem; B/E/F aprovar→"concluído" no chat +
  arquivo + conteúdo exato; G auditoria; C recusa→mensagem e nada
  executado; D falha→"falhou" no chat; sem callback = comportamento
  anterior; callback hostil não quebra o diálogo).
- **Preservado**: suíte 0.6.3+hotfixes verde (872 → 880).

## COMPLETED — 0.6.3 (Tool Calling / Planner Bridge)

### Lumen 0.6.3 — a ponte Chat → Ferramentas ✅

- **`app/planner/catalog.py`** (novo): allowlist de protocolo com as 7
  ferramentas já existentes (6 filesystem + `run_command`); specs
  declarativas (nome/tipo/obrigatoriedade); `validate_task_tool`
  rejeita tool vazia/inventada, params ausentes/desconhecidos/tipos
  errados e paths absolutos/`..`/drive/UNC; `build_catalog(include_terminal=…)`
  omite terminal desabilitado; **puro dados** (sem `app.tools`, sem
  execução — AST testado).
- **`app/planner/planner.py`**: `catalog` opcional no construtor;
  `create_tool_plan → ToolPlanResult` (`plan`/`conversation`/
  `invalid`); prompt de planejamento com allowlist embutida
  (`{"type": "conversation" | "plan", …}`); `_parse_plan(tool_mode)`
  exige tool+parameters em TODAS as tarefas; falha controlada com
  motivo (nunca lança, nunca executa parcial).
- **`app/core/bridge.py`** (novo): `ToolCallingBridge.process` —
  conversa → `send_message` clássico (streaming); ação →
  `ToolsController.run_plan`; `RequestState` com os 10 estados;
  `AgentOutcome(state, text, plan_id)`; memória linear registra o
  histórico de ações; sem lógica de filesystem/terminal.
- **`app/core/agent.py`**: `process_message` (UI usa isto agora),
  `request_tool_plan` (gate CHAT, provider vigente, memória como
  leitura), `set_tools_controller` (injetado pelo `main.py`; sem
  controller = comportamento 0.6.2).
- **`app/ai/mock.py`**: `chat` reconhece o prompt de planejamento com
  ferramentas (marcador) e planeja DETERMINÍSTICAMENTE (criar/escrever/
  ler/listar/existir/apagar-alvo-único; terminal só se allowlist no
  prompt; vagos/destrutivos/injection = conversa); caminho clássico
  intacto (`request_plan` sem tools segue FAILED — testes 0.4
  preservados).
- **`app/tools/control.py`**: `planning_catalog()` (6 tools sempre;
  `run_command` só com terminal habilitado); pendência traz
  `content_preview` (truncate 200).
- **UI**: `tools_dialog` mostra **Conteúdo:** no card de aprovação;
  `main_window._worker` usa `process_message`.
- **Versão 0.6.3**; exports `ToolPlanResult` em `app/planner/__init__`.
- **Testes novos (97)**: `test_planner_tools.py` (44: allowlist,
  matriz de validação, escape de path, imutabilidade, prompt),
  `test_mock_tool_planning.py` (16: casos canônicos determinísticos,
  conversa × ação, injection), `test_agent_bridge.py` (37: fluxo
  completo CHAT→…→VERIFICAÇÃO, permissões/checkpoints/recusa/auditoria,
  correção via chat, terminal não ampliado, AST anti-futuro).
- **Preservado**: suíte 0.6.2 verde (771 → 868); harness 55/55.

## COMPLETED — 0.4.x (Correção Automática Controlada — versão 0.6.2)

### Lumen 0.4.x — Correção Automática Controlada ✅

- **`app/executor/correction.py`** (novo; genérico, **não importa
  `app.tools`** — AST): `CorrectionEngine` real em volta do
  `PlanExecutor` (`run()`, `approve_correction`/`refuse_correction`,
  `paused`/`waiting_decision`/`correction_pending`/`current_plan`/
  `plan_ids`/`cycles`); `CorrectionStrategy`/`CorrectionProposal`
  saem do Noop; **estados separados** (`PROPOSED`, `INVALID`,
  `REFUSED`, `APPROVED`, `APPLIED`, `RETRIED`, `SUCCEEDED`, `FAILED`,
  `NO_PROPOSAL`, `EXHAUSTED`); **planos sucessores imutáveis**
  (`<plano>#C<n>`, tarefa corrigida mantém id/ordem, dependências
  filtradas, plano original intocado — testado); **limites rígidos**:
  ciclos aplicados ≤ `max_cycles`, tentativas acumuladas ≤
  `max_total_attempts`, `max_cycles=0` desliga, **nunca infinito**;
  `_handle_failure` **tri-state** (segue/pausa aguardando decisão/
  falha definitiva) preservando a retomada; numeração por análise
  (`_analysis_counter`); `FAILED` emitido quando correção aplicada
  não resolve e não há nova proposta.
- **`app/tools/correction.py`** (novo): `ToolCorrectionStrategy`
  (conservadora: `create_file → write_file` somente para "arquivo já
  existe"; `_SECURITY_MARKERS` — permissão negada/allowlist/fora do
  workspace/traversal/somente leitura/operador de shell/… — ⇒ **nunca
  propõe**) + `build_proposal_validator` (tool registrada + permissão
  concedida + sandbox `resolve`/`check_operation`; `run_command`
  valida `TerminalPolicy`).
- **`app/tools/control.py`**: `enable_corrections(strategy=None,
  max_cycles=2, max_total_attempts=8)`/`disable_corrections`/
  `corrections_enabled`/`correction_history()` (validação dos limites
  ⇒ `ToolsControlError`); `run_plan` cria o engine quando habilitado;
  `pending_approval`/`approve`/`refuse`/`has_pending` roteiam correção
  (`kind="correction"`, `checkpoint_id="COR-%04d"`, de→para,
  `failure_kind`) × checkpoint de operação (sem `kind`);
  `_task_view` extraído; `_audit_cycle` registra **todo** ciclo no
  JSONL (`tool="correction"`, `correction_<status>`,
  sucesso=False para INVALID/REFUSED/FAILED/NO_PROPOSAL/EXHAUSTED,
  `suggestion`/`note` truncados em 160).
- **`app/ui/tools_dialog.py`**: card **CORREÇÃO PROPOSTA** (falha de
  execução/verificação, ferramenta de→para, parâmetros de→para);
  Aprovar aplica e segue para o checkpoint da operação; Recusar
  mantém a falha (nada executa depois).
- **Versão 0.6.2** (`app/__init__.py`); exports
  `ToolCorrectionStrategy`/`build_proposal_validator` em
  `app/tools/__init__.py`.
- **Testes novos (45)**: `tests/test_correction.py` (20 — motor:
  sucesso após correção, recusa, inválida, advice-only, limites de
  ciclos/tentativas, auto-apply, checkpoint de tarefa corrigida,
  imutabilidade, `FAILED` pós-aplicação, kinds de falha) e
  `tests/test_tools_correction.py` (25 — camada real: ciclo completo
  pelo controller com checkpoint da operação original, legacy sem
  correções, recusa/inválida/ghost/evil-path, sem bypass de WRITE,
  `max_cycles=0`, loop finito (aprovações < 12), auditoria JSONL,
  disable/enable, imutabilidade, 2 testes de UI via FakeTkModule).
- **Preservado**: Executor/Planner intocados (exceto wiring do
  controller); suíte 0.6.1 verde (726 → 771).

## COMPLETED — 0.6.x (UI de Terminal, Allowlist e Concessão TERMINAL)

### Lumen 0.6.x — Camada visual de administração do Terminal ✅

- **`app/tools/terminal.py`** (estendido): `TerminalPolicy.entries()/
  remove()` (remoção explícita, normalização na busca), propriedades
  públicas dos defaults e `make_entry` aceita `full_path` explícito
  (restauração da persistência); **`TerminalStore`** — persistência
  `data/terminal.json` (escrita atômica tmp+replace; só nasce no 1º
  save; `load()` levanta `TerminalStoreError` em arquivo ilegível ⇒
  controller **falha fechado**).
- **`ToolsController`** (0.6.x): `terminal_file` opcional no construtor
  + `_load_terminal()` (fail closed por entrada: denylistada/inválida ⇒
  descartada com aviso; defaults restaurados; **permissão TERMINAL
  nunca restaurada**); `grant_terminal()`/`revoke_terminal()` —
  **explícitos e auditados** (`grant_permission` genérico segue
  rejeitando TERMINAL); `list_allowed_commands()` (nome/flags/limites
  resolvidos), `remove_allowed_command()`, `terminal_status()`;
  `allow_command` **bootstrap** a allowlist no 1º cadastro (habilitar ≠
  conceder; auditado `terminal_enable`) e persiste; `disable_terminal`
  esvazia a lista persistida; `_audit_admin()` registra tudo em JSONL
  (`tool=terminal_admin`, inclusive tentativas rejeitadas).
- **UI `tools_dialog.py`**: seção **TERMINAL (0.6.x)** — linha da
  permissão (estado + Conceder/Revogar dedicados), allowlist com
  cadastro (toggle Aprovação SIM/NÃO), remoção por comando e botão
  "Desabilitar terminal" (confirmação); hint explicando exatamente o
  que TERMINAL permite; **card de aprovação** com Comando / Argumentos
  / Diretório de trabalho / Timeout em linhas separadas. A UI importa
  **somente** `app.tools.control` (testes AST/inspeção garantem).
- **`main.py`**: apenas passa `terminal_file` (leitura; nada nasce no
  startup). Versão **0.6.1**; exports `TerminalStore(Error)`.
- **Testes novos (31)**: `tests/test_terminal_admin.py` (22: linha
  TERMINAL em permission_status; genérico rejeita TERMINAL; grant/
  revoke explícitos+auditados; COMPUTER_CONTROL sem via dedicada;
  allowlist add/remove/persiste; denylist rejeitada e não persistida;
  bootstrap do 1º comando; terminal_status; disable esvazia; admin em
  JSONL; restauração entre sessões **sem** concessão; startup não cria
  arquivo; ilegível ⇒ fail closed; entrada "sh" no arquivo ⇒ descartada;
  gate sem TERMINAL bloqueia (sem checkpoint decorativo); grant ⇒
  checkpoint com argv/timeout/cwd; **revogar com pendente ⇒ aprovar NÃO
  executa**; fluxo completo POSIX; comando removido não roda mais) e
  +9 em `tests/test_tools_dialog.py` (seção vazia; concede/revoga pela
  UI com auditoria; cadastra+persiste; toggle de aprovação; denylist
  com status 🔴 e não cadastra; remove; desabilita; card completo; UI
  só usa a fachada). Harness → **55 checks** (+9: arquivo de allowlist
  não nasce; TERMINAL não fica concedida sem ato explícito; seção
  mostra concessão/allowlist; cadastro pela UI; denylist rejeitada na
  UI; remoção pela UI; revogação/concessão pela UI; ações administrativas
  auditadas).
- **Preservado**: todas as proteções 0.6.0 (allowlist/denylist/sem
  shell/timeout/limites/cwd/args/env/checkpoints/auditoria sem
  stdout), suíte 0.6 verde (695 → 726).

## COMPLETED — 0.6 (Terminal Tools — fundação controlada)

### Lumen 0.6 — Terminal Tools ✅

- **Novo módulo** `app/tools/terminal.py` (**único** com `subprocess`
  — garantido por testes AST):
  - `TerminalPolicy` — **allowlist explícita** (`allow()`/ctor) +
    **denylist permanente** `FORBIDDEN_COMMANDS` (137 nomes
    normalizados: shells `sh`/`powershell`/`cmd`/`wsl`, interpretadores
    `python`/`node`/`ruby`…, executores de subcomando `env`/`xargs`/
    `time`/`watch`/`gdb`, builders `make`/`cmake`/`dotnet`/`docker`,
    escalonamento `sudo`/`runas`/`pkexec`, administrativos `net`/`sc`/
    `reg`/`schtasks`/`taskkill`, desligamento `shutdown`/`reboot`,
    destrutivos `rm`/`dd`/`format`/`diskpart`, permissões `chmod`/
    `icacls`, **rede** `curl`/`wget`/`ssh`/`nc`/`ping`) +
    `DANGEROUS_ARGUMENTS` (`-exec`, `/c`, `-Command`,
    `-EncodedCommand`, `--eval`…) + `OPERATOR_TOKENS` (`&&`, `||`, `|`,
    `;`, `&`, `>`, `<`, `` ` ``, `$(`, newline — bloqueados salvo
    `allow_operators=True`); `validate()` rejeita com subtipos de
    `TerminalSecurityError` (motivo claro) e devolve `ValidatedCommand`
    (argv, cwd resolvido, timeout clampado, limites, requires_approval).
  - `AllowedCommand` — entrada da allowlist: `name` normalizado,
    `full_path` opcional (match **exato**), `args_allowlist` opcional
    (argumentos fixos), `requires_approval` (default **True**),
    `timeout_s`/`max_output_bytes` próprios; `normalize_command` mata
    aliases (`python.exe`→`python`, `/bin/SH`→`sh`).
  - `RunCommandTool` (`run_command`, permissão **TERMINAL**) — argv
    **sem shell** (`shell=False`), cwd confinado (args com `..` ou
    caminho absoluto fora dos workspaces bloqueados; no Windows
    `C:\…`/UNC detectados via `PureWindowsPath`), `stdin=DEVNULL`,
    **ambiente sanitizado** (`SAFE_ENV_VARS` + descarte de nomes com
    KEY/TOKEN/SECRET/PASSWORD), leitores com **teto de saída** (default
    64 KiB, threads que leem e descartam além do teto), **timeout**
    obrigatório (default 10 s, teto 60 s; `TimeoutExpired` ⇒ kill),
    captura `stdout`/`stderr` separadas (decode UTF-8 replace),
    `exit_code`/`timed_out`/`truncated`/`duration_ms` no `ToolResult`;
    `exit_code≠0`, timeout e truncamento = `ok=False` com motivo
    (falha honesta); `FileNotFoundError`/`OSError` controlados.
  - `PrevalidatedTerminalCheckpoints` — checkpoint **somente** para
    comandos viáveis (registry + permissão TERMINAL + validate OK) marcados
    `requires_approval`; inviáveis falham direto no handler com o
    motivo real (sem aprovação decorativa — lógica 0.5.1).
- **`ToolsController`** (0.6): `enable_terminal(allowlist, …)` (opt-in
  do integrador; denylist aplicada no registro; nada no startup),
  `allow_command(name, **kwargs)`, `disable_terminal()`,
  `terminal_policy`; `build_registry` registra `run_command` **só**
  quando habilitado; `run_plan` usa `_CombinedCheckpoints`
  (filesystem 0.5 + terminal 0.6); `pending_approval` mostra
  **argv completo + timeout** (`command`/`timeout_s`) além de
  ferramenta/operacao/permissão/onde; `TERMINAL` segue **concessão
  programática** (UI/`MANAGEABLE_LEVELS` intactos).
- **UI** (`tools_dialog.py`): card de aprovação ganha a linha
  `Comando: <argv> (timeout: Ns)` quando o pendente é de terminal —
  apresentação apenas; nenhuma tela nova (UI da allowlist é 0.6.x).
- **Handler**: `ToolTaskHandler` audita o permission_gate com
  `requested = path or cwd`; **auditoria JSONL** registra
  (`tool=run_command`) comando sanitizado (`_sanitize_for_audit`:
  ≤32 args/≤200 chars), cwd solicitado/resolvido, `exit_code`,
  `duration_ms`, `timed_out`/`truncated`, tarefa/plano — **nunca**
  stdout/stderr.
- **Testes novos (142 casos)**: `tests/test_terminal_policy.py` (108:
  allowlist vazia bloqueia; denylist em 38 nomes; aliases/variações;
  full_path exato; args_allowlist fixa; operadores em 9 formas;
  argumentos-perigo em 10; `..`; absolutos fora (POSIX/Windows/UNC);
  cwd fora/inexistente; timeouts/clamps; entradas malformadas),
  `tests/test_terminal_tool.py` (16: stdout/stderr/exit code;
  fora da allowlist não executa; timeout mata; truncamento; gate sem
  TERMINAL; READ/WRITE não bastam; com TERMINAL roda; auditoria sem
  stdout/stderr e com argv truncado; **env filho sem segredo**
  `SEGREDO-987` ausente com `printenv`), `tests/test_terminal_integration.py`
  (18: cadeia Registry→Handler→Executor; bloqueado falha plano sem
  executar; checkpoint pausa com contexto completo; aprova executa;
  **recusa não executa**; sem TERMINAL = sem checkpoint, só bloqueio
  auditado; requires_approval=False roda direto; plano com múltiplos
  checkpoints; plano misto filesystem+terminal; JSONL com run_command
  sem conteúdo; enable/disable/allow_command; startup sem run_command;
  gate via handler; **AST anti-futuro**: subprocess só em terminal.py,
  terminal sem rede/automação, núcleo/UI agnósticos). `test_app.py`
  → 0.6.0 + file-list; `test_filesystem_integration.py` AST atualizada
  (exceção única terminal.py); harness `verify_ui_headless.py` →
  **46 checks** (5 novos: startup sem terminal, card com argv/permissão/
  timeout, bloqueio até aprovação, recusa não executa, aprovação
  executa).
- **Preservado**: 5 providers, chat, memória, Planner/Executor
  (agnósticos), filesystem/workspaces/permissões/auditoria 0.5/0.5.x,
  UI existente (suíte anterior verde: 553 → 695 com os novos).

## COMPLETED — 0.5.x (UI de Workspaces, Permissões, Checkpoints e Auditoria)

### Lumen 0.5.x — Camada visual e de controle das Ferramentas ✅

- **Novos módulos** `app/tools/`:
  - `workspaces.py` — `WorkspaceEntry` (raiz + política
    somente-leitura/escrita/escrita+exclusão), `WorkspaceStore`
    (persistência atômica em `data/workspaces.json`; valida/normaliza:
    absoluto, existente, diretório, `resolve()`, sem duplicatas,
    **rejeita raiz de disco** `/`, `C:\`), `MultiWorkspaceSandbox`
    (herda `WorkspaceSandbox` da 0.5; `resolve` + `check_operation`
    aplicam a política **por raiz** — workspace somente-leitura bloqueia
    escrita nele mesmo que outro workspace permita).
  - `audit_log.py` — `JsonlAuditSink` (append JSONL thread-safe em
    `data/audit/audit.jsonl`; diretório criado na 1ª escrita) +
    `read_audit_tail` (leitura tolerante a linhas corrompidas).
  - `control.py` — `ToolsController`: fachada para a UI (workspaces
    add/remove, permissões grant/revoke **somente CHAT/READ/WRITE**,
    execução `run_plan` com pending/approve/refuse, auditoria
    `recent_audit`), composta no `main.py` com as **mesmas** instâncias
    do `Agent` (permissions/sandbox) e um registry dedicado;
    `PrevalidatedCheckpoints(ToolCheckpoints)` — pede checkpoint
    **somente** para operações destrutivas **viáveis** (permissão
    concedida + `resolve` + `check_operation` sem erro); inviáveis
    falham direto no handler com o motivo real (bloqueio honesto — sem
    aprovação decorativa).
- **UI** `app/ui/tools_dialog.py` — diálogo "🛡 Ferramentas e
  Segurança" (só apresentação; toda lógica no controller):
  - *Workspaces*: lista (caminho + modo), adicionar (com modo) e
    remover; nunca o Windows inteiro (a store rejeita raiz de disco).
  - *Permissões*: CHAT/READ/WRITE com estado e concessão/revogação;
    **DELETE exibido como opt-in por workspace** (não como nível);
    `TERMINAL`/`COMPUTER_CONTROL` rejeitados com erro claro.
  - *Aprovação*: card da operação aguardando com **o quê / onde
    (solicitado→resolvido + workspace) / ferramenta + operação +
    permissão** e botões APROVAR/RECUSAR (enquanto pendente, nada
    executa; RECUSAR marca `SKIPPED`/`FAILED` e o arquivo fica
    intocado — testado).
  - *Auditoria*: últimos registros (timestamp, ferramenta, operação,
    caminhos, ✓/✗, erro, tarefa/plano) — **sem conteúdo de arquivos**.
  - Botão **🛡** na janela principal (`main_window.py`).
- **`main.py`** compõe tudo **sem efeitos colaterais** no startup
  (nenhum `workspaces.json`/`audit.jsonl` criado, nenhuma permissão
  concedida, nenhuma ferramenta registrada até o usuário agir).
- **Modificados**: `filesystem.py` (`check_operation` ciente do
  caminho p/ política por raiz), `agent.py` (property read-only
  `permissions` para composição com a mesma instância), `main_window.py`
  (botão 🛡), `app/__init__.py` → **0.5.1**, `app/tools/__init__.py`,
  `fake_tk.py` (suporte aos widgets do diálogo), `main.py`.
- **Testes novos (55)**: `tests/test_workspaces.py` (17: validação/
  normalização/rejeição de raiz/dedup/persistência/sandbox por raiz),
  `tests/test_audit_log.py` (4: append JSONL/leitura/linhas
  corrompidas), `tests/test_tools_control.py` (21: permissões grant/
  revoke/rejeição de TERMINAL; workspaces; execução real com
  checkpoints; **segurança da spec** — traversal, read-only, DELETE
  opt-in, recusa não executa, startup limpo, gate auditado), e
  `tests/test_tools_dialog.py` (13: UI fake-tk — fluxos das 4 abas).
  Harness `tools_dev/verify_ui_headless.py` estendido a **41 checks**
  (seção 0.5.x com 11).
- **Bug real corrigido durante os testes**: o checkpoint genérico da
  0.5 pausava **antes** do gate de permissão (a UI pediria aprovação
  para operação que nem permissão tinha). Corrigido com
  `PrevalidatedCheckpoints` (viabilidade antes de pausar) — testes
  cobrem os dois lados (inviável falha direto; viável pausa, aprova
  executa, recusa não).
- **Preservado**: 5 providers (`mock`,`openai`,`gemini`,`groq`,
  `together`), chat, memória, Planner/Executor, sandbox/permissões da
  0.5 (suíte anterior verde; auditoria AST/grep anti-futuro verde — sem
  exec/rede/automação em `app/`; executor/planner sem `app.tools`;
  `MANAGEABLE_LEVELS` = CHAT/READ/WRITE).

## COMPLETED — 0.5 (Filesystem Tools — fundação segura)

### Lumen 0.5 — Filesystem Tools ✅

Funcionalidades **realmente implementadas e verificadas** (tudo da
0.1–0.4.2 permanece intacto; escopo **somente filesystem**, confinado,
permitido e auditado):

1. **`app/tools/filesystem.py`** — `WorkspaceSandbox`: raízes
   **autorizadas explicitamente** (absolutas, resolvidas, ≥1;
   relativa/lista vazia → `ValueError`); `writable=False` (somente
   leitura) e `allow_delete=False` por padrão; `resolve()` valida
   formato (texto, não vazio, sem caracteres de controle), **rejeita
   qualquer componente `..`** (traversal bloqueado inclusive se o
   destino ficaria dentro), aceita absoluto apenas dentro de uma raiz,
   resolve relativos contra as raízes na ordem declarada e **verifica
   contenção após `Path.resolve()`** (symlink para fora é bloqueado);
   `assert_operation_allowed` porta read/write/delete pela política.
   **6 ferramentas** (`StructuredTool`): `list_directory` (entradas
   ordenadas nome/tipo/tamanho + contagem), `read_file` (UTF-8,
   `max_bytes` default 1 MiB), `write_file` (cria/sobrescreve com flag
   `overwritten`; pai deve existir), `create_file` (falha se existe),
   `delete_file` (apenas arquivos; opt-in duplo), `file_exists`
   (`exists`/`is_dir`) — permissões `READ`/`WRITE` declaradas;
   resultados **estruturados** `ToolResult{ok, data, error}` (operação,
   caminho solicitado/resolvido, dados, erro amigável; falha não vira
   exceção para o chamador). `FilesystemAudit`: `AuditRecord` imutável
   (timestamp, ferramenta, operação, caminhos solicitado/resolvido,
   sucesso, erro, tarefa/plano via `scoped()`, `detail` de metadados) —
   **sem conteúdo de arquivos**; sink injetável (persistência futura);
   thread-safe. `build_filesystem_registry(permissions, sandbox,
   audit?)` registra as 6 tools — **registro sempre explícito**.
2. **`app/tools/handler.py`** — `ToolTaskHandler` (ponte Executor ↔
   ferramentas): despacha `task.tool`/`task.parameters` via
   `ToolRegistry` (permissão portada **antes** de qualquer código da
   ferramenta rodar); `PermissionDeniedError`/ferramenta inexistente/
   `ok=False` → `HandlerError` (fail-fast controlado; **bloqueado, não
   executado**); bloqueio de permissão também vai para a auditoria
   (`operation="permission_gate"`); tarefa sem ferramenta falha
   honestamente ("não designa ferramenta") — sem execução fantasma.
   `ToolCheckpoints(required_tools)`: pausa a execução antes de
   ferramentas destrutivas (`FILESYSTEM_DESTRUCTIVE_TOOLS` =
   write/create/delete) — aprovar executa, recusar bloqueia
   (consentimento sem UI obrigatória).
3. **`app/tools/base.py`** — extensão aditiva: `ToolResult` +
   `StructuredTool` (contrato 0.1 `Tool.execute → str` preservado; o
   resultado estruturado serializa em JSON); validação de metadados
   apenas em ferramentas concretas (marcador `_abstract_base`).
4. **`app/planner/models.py`** — `PlannedTask` ganha campos
   **opcionais** `tool`/`parameters` (default `None`; incluídos no
   `to_dict`). **Protocolo do Planner intocado** — ele não emite
   ferramentas; planos com tools são montados programaticamente.
5. **Integração** — `Agent.execute_plan(plan, handler=...)` já aceitava
   handler injetado (Agent **não mudou**); `main.py`/startup **sem
   efeitos colaterais** (nenhuma ferramenta registrada, nenhuma
   permissão nova — default segue só `CHAT`; providers/memória/chat/
   permissões intactos).
6. **Versão** — `app.__version__` → `0.5.0`.

---

## COMPLETED — 0.4.x (checkpoints/retry/verificação)

### Lumen 0.4.x — Checkpoints + Retry + Verificação ✅

Funcionalidades **realmente implementadas e verificadas** (tudo da
0.1–0.4.1 permanece intacto; **tudo simulado/in-memory**, sem UI nova
e sem ferramentas reais):

1. **`app/executor/checkpoints.py`** — `CheckpointPolicy` (ABC) com
   `NeverCheckpoints` (padrão — preserva o comportamento 0.4.1) e
   `EveryTaskCheckpoints`; `CheckpointRequest` (id `CP-0001`…, task,
   reason, note, timestamps) + `CheckpointStatus`:
   `PENDING_APPROVAL` (checkpoint **necessário**; execução **pausada**
   aguardando confirmação — `executor.paused`/`pending_checkpoint`) ·
   `APPROVED` (aprovado; retoma) · `REFUSED` (recusado ⇒ plano `FAILED`
   controlado, tarefa não executada e restantes `SKIPPED`). API
   `approve_checkpoint()`/`refuse_checkpoint()` com guards; histórico
   completo no `ExecutionReport.checkpoints`/`pending_checkpoint`.
2. **`app/executor/retry.py`** — `RetryPolicy(max_attempts ≥ 1,
   backoff_seconds ≥ 0)` validada no construtor (**impossível retry
   infinito por construção**); `AttemptRecord` (número, resultado,
   erro) acumulado em `TaskRun.attempt_log` (tentativas registradas
   uma a uma); backoff linear **injetável** (`sleeper`, padrão
   `time.sleep`); erros *inesperados* do handler não são repetidos.
3. **`app/executor/verification.py`** — `TaskVerifier` (ABC) +
   `VerificationResult` + `SimulatedVerifier` (in-memory): após
   executar com sucesso, o Executor verifica — `EXECUTOU → VERIFICOU →
   SUCESSO` (`DONE` + `verified=True` + evento
   `task_verification_passed`) ou `… → FALHOU` (novo status `REJECTED`
   + `verified=False` + resultado preservado + fail-fast; evento
   `task_verification_failed`). Falha de verificação **não** consome
   retry (corrigir antes de repetir — futuro); verificador quebrado
   vira reprovação controlada.
4. **`app/executor/correction.py`** — abstrações mínimas para o loop
   futuro `falha → análise → correção → nova tentativa → verificação`:
   `CorrectionStrategy` (ABC `propose_correction(task, run)`) +
   `CorrectionProposal` + `NoopCorrectionStrategy` (não propõe nada).
   O Executor **não importa nem chama** o módulo (auditoria AST);
   nenhum provider é acionado para corrigir.
5. **Integração** — `Agent.execute_plan(plan, handler?, verifier?,
   retry?, checkpoints?)`; `TaskRun` ganha `verified`/`attempt_log`;
   `ExecutionReport` ganha `checkpoints`/`pending_checkpoint`;
   `PlannedTaskStatus` ganha `REJECTED`. **Planner sem lógica de
   execução; providers/memória/chat/permissões/startup intocados.**
6. **Versão** — `app.__version__` → `0.4.2`.

---

## COMPLETED — 0.4.x (Executor — fundação)

### Lumen 0.4.x — Executor de Planos (fundação) ✅

Funcionalidades **realmente implementadas e verificadas** (tudo da
0.1–0.4 permanece intacto; **nenhuma ferramenta real** — apenas handlers
simulados/in-memory):

1. **`app/executor/handlers.py`** — `TaskHandler` (ABC: `execute(task)
   → str`, falha via `HandlerError`) — a costura única com o futuro
   (ferramentas reais da 0.5+ viram handlers sobre o `ToolRegistry`,
   que segue **vazio**); `SimulatedHandler` determinístico in-memory
   (resultados/falhas programados por task id).
2. **`app/executor/executor.py`** — `PlanExecutor(plan READY, handler,
   observer?)`: validação defensiva (READY · tarefas ≥1 · dependências
   existentes · sem ciclos); elegibilidade = **todas as dependências
   DONE** (ordem planejada respeitada); `step()` (exatamente uma tarefa
   — avanço por tarefa, base para checkpoints futuros) e `run_all()`;
   **fail-fast**: falha → tarefa `FAILED` com erro, restantes `SKIPPED`
   com motivo, plano `FAILED`; sucesso → todas `DONE` e plano
   `COMPLETED`; `TaskRun` (id/descrição/ordem/deps/status/result/error/
   attempts), `ExecutionReport` **imutável** (eventos
   `task_started/completed/failed/skipped/plan_finished`, timestamps,
   `to_dict()`); `ExecutionObserver` no-op (ganchos para
   checkpoints/retry/verificação futuros); determinismo garantido.
3. **Estados estendidos** — `PlanStatus` ganha `RUNNING`;
   `PlannedTaskStatus` ganha `IN_PROGRESS/DONE/FAILED/SKIPPED`
   (atribuídos pelo Executor aos `TaskRun`; o `Plan` original permanece
   imutável, com tarefas `PENDING`).
4. **Integração com o Agent** — `Agent.execute_plan(plan, handler?)`:
   gate `CHAT`, handler simulado por padrão, relatório completo como
   retorno; **não altera conversa, memória 0.3, providers**; Planner
   segue sem nenhuma lógica de execução (separação rigorosa).
5. **Versão** — `app.__version__` → `0.4.1`.

---

## COMPLETED — 0.4

### Lumen 0.4 — Planner (fundação) ✅

Funcionalidades **realmente implementadas e verificadas** (tudo da
0.1–0.3.x permanece intacto; UI não tocada; **nenhuma tarefa é
executada**):

1. **`app/planner/models.py`** — estruturas imutáveis:
   `PlanStatus` (`PLANNING` transitório · `READY` · `BLOCKED` ·
   `FAILED` · `COMPLETED` reservado ao executor futuro),
   `PlannedTaskStatus` (`PENDING` — nada é executado na 0.4),
   `PlannedTask` (id `T1…Tn`, description, order, dependencies,
   status, result, error) e `Plan` (id `PLN-0001`…, objective, status,
   analysis — o que analisar antes da execução —, tasks, error,
   timestamps; `to_dict()` para serialização futura).
2. **`app/planner/planner.py`** — `Planner.create_plan(pedido,
   contexto)`: prompt de planejador com **protocolo JSON strict**
   (objetivo/análise/tarefas+dependências; proíbe comandos e ações);
   chamada ao provider via abstração `AIProvider.chat` (nunca provider
   concreto); parser tolerante a cercas de código/texto ao redor;
   validação completa (JSON → objeto → tarefas ≥1 → descrições → ids →
   dependências existentes remapeadas para ids canônicos → **ciclos
   rejeitados por ordenação topológica**). Falhas **controladas**: plano
   inválido/erro do provedor → `FAILED` com motivo claro em `error`;
   pré-condição do ambiente ausente (sem API key/modelo/SDK) →
   `BLOCKED`; nunca lança exceção de negócio, nunca traceback.
3. **Memória 0.3 como leitura** — quando um `MemorySystem` é injetado,
   o Planner usa `recall(pedido)` (≤5 registros, excertos de 200 chars)
   para enriquecer o prompt; **nunca grava** (testado: stats e arquivos
   inalterados); memória ausente/indisponível não derruba o plano.
4. **Integração com o Agent** — `Agent.request_plan(pedido)` (novo
   método; `send_message` intocado): gate `CHAT`, snapshot thread-safe
   do provider vigente (respeita troca em runtime), histórico recente
   como contexto, não altera a conversa. `main.build_app` monta o
   `MemorySystem` (sem efeitos colaterais — arquivos de domínio só
   nascem no primeiro save) e o injeta como `memory_system` do Agent.
5. **Versão** — `app.__version__` → `0.4.0`.

---

## COMPLETED — 0.2 (histórico)

Funcionalidades **realmente implementadas e verificadas** (além de tudo
da 0.1, que permanece intacto):

1. **`OpenAIProvider`** (`app/ai/openai_provider.py`) — integração com a
   API da OpenAI via SDK oficial (`openai>=1.54,<2.0`), import lazy
   (modo mock funciona sem o pacote), client injetável para testes
   offline.
2. **Seleção de provedor por configuração** — `LUMEN_PROVIDER=mock`
   (offline, default) ou `LUMEN_PROVIDER=openai`; fábrica
   `create_provider()` com registro nome→classe.
3. **Validação de configuração com mensagens claras** — API key ausente
   (`MissingApiKeyError`) e modelo não configurado
   (`ModelNotConfiguredError`) explicam como configurar o `.env`;
   provedor inválido lista os disponíveis.
4. **Persona central** (`app/config/persona.py`) — nome Lumen,
   assistente **feminina**, papel de assistente de desenvolvimento,
   idioma português; nada de identidade espalhada pelo código.
5. **System prompt centralizado** (`build_system_prompt()`) — seções
   curtas: identidade, papel, idioma, estilo (objetiva/colaborativa),
   honestidade (nunca fingir ações; **sem acesso ao computador** nesta
   versão) e futuro (não prometer capacidades que não tem). O modelo
   real controla a conversa; sem respostas artificiais forçadas.
6. **Contexto de conversa** — o Agent envia system prompt + histórico
   limitado (`LUMEN_MAX_CONTEXT_MESSAGES`, default 50) + mensagem
   atual; timestamps e roles estranhos são filtrados do payload.
7. **Streaming** — respostas exibidas progressivamente na UI via
   callback `on_delta` (fila + `after`); política anti-duplicação: sem
   retry após deltas emitidos; provedores sem streaming caem no fluxo
   estável automaticamente.
8. **Async/threading preservado** — requisição de IA fora da thread da
   UI (verificado: `send()` retorna em <1 ms com provedor de 250 ms);
   erros voltam com segurança pela fila.
9. **Timeout** — `LUMEN_REQUEST_TIMEOUT` (default 60 s) repassado ao
   client e a cada requisição; nenhum tempo de espera indefinido.
10. **Retry limitado** — `LUMEN_MAX_RETRIES` (default 2) apenas para
    erros temporários (rate limit, timeout, rede, 5xx); nunca para
    autenticação/configuração/dependência.
11. **Tratamento de erros diferenciado** — key ausente, autenticação
    inválida, modelo inválido, rate limit, timeout, rede, 5xx,
    dependência ausente e inesperado — mensagens amigáveis na UI
    (`AgentError`), detalhes técnicos no log.
12. **`AIResponse` normalizada** (`app/ai/types.py`) — content, model,
    usage (input/output/total tokens preservados quando o provedor
    informa), finish_reason; Agent Core e UI não dependem do formato da
    API.
13. **Preparação para agente** — `ResponseType` (FINAL_RESPONSE |
    TOOL_CALL | PLAN) e campo `tool_calls` (sempre vazio na 0.2) já
    existem para que 0.4+ evolua sem reescrever o Agent Core. **Tool
    calling real NÃO implementado.**
14. **UI 0.2** — mantida da 0.1 com: cabeçalho mostrando
    provedor/modelo (e "modo simulado, sem rede" no mock), status
    "● Pensando…", erros amigáveis ("⚠ …") e resposta progressiva.
15. **Documentação** — README, ARCHITECTURE, ROADMAP e LUMEN_STATE
    atualizados; `.env.example` com as 8 variáveis da 0.2.

### Complemento 0.2 — Configurações de IA (tela gráfica) ✅

16. **Tela "⚙ Configurações → Inteligência Artificial"**
    (`app/ui/settings_dialog.py`) — acessada pelo botão "⚙
    Configurações" na janela principal; permite alterar **Provedor**
    (mock/openai), **Modelo** e **API Key** sem editar o `.env`.
17. **Cofre de credenciais** (`app/config/secrets.py`) — API Key no
    **Windows Credential Manager** (via `keyring`) com **fallback**
    documentado em arquivo restrito `data/.credentials.json` (0600,
    atômico, fora do Git); salvar/recuperar/alterar/remover; a chave
    salva **nunca** é exibida de volta (campo oculto `•••`; 👁 revela
    apenas o que está sendo digitado).
18. **ConfigService** (`app/config/config_service.py`) — única porta da
    UI de configuração: valida **antes** de persistir, grava valores
    não secretos em `data/settings.json`, chave no cofre, e **aplica ao
    Agent imediatamente** (`Agent.set_provider`, thread-safe, sem
    reiniciar); a próxima mensagem já usa o novo provider/modelo.
19. **Precedência documentada** — GUI salva > variáveis de ambiente >
    `.env` > padrões; chave: cofre > `.env` (remover do cofre cai para
    o `.env`, com aviso na UI).
20. **TESTAR CONEXÃO** — requisição mínima (`max_tokens=1`,
    `max_retries=0`) com os valores do formulário ou da configuração
    vigente; `🟢 MockProvider funcionando` (offline), `🟢 Conexão
    estabelecida` ou `🔴 …` amigável (chave inválida, modelo inválido,
    timeout, rede, rate limit, dependência ausente, inesperado) —
    detalhes técnicos apenas no log, sem segredos.
21. **Startup integrado** — `main.build_app()` já sobe com a
    configuração da GUI vigente (ex.: `.env` diz mock, GUI salvou
    openai → o provedor usado é openai).

### Complemento 0.2 — Google Gemini (terceiro provider) ✅

22. **`GeminiProvider`** (`app/ai/gemini_provider.py`) — integração com
    a API do Google Gemini via **SDK oficial `google-genai`** (GA; o
    legado `google-generativeai` está deprecated; o endpoint
    OpenAI-compat foi avaliado e descartado em favor do caminho
    recomendado oficialmente). Import lazy + `client_factory` injetável
    (testes 100% offline); adaptador interno converte dict→
    `GenerateContentConfig` e timeout s→ms.
23. **Modelo padrão fundamentado** — `gemini-2.5-flash` quando
    `LUMEN_MODEL` vazio (GA estável, melhor preço/desempenho para
    conversa com raciocínio segundo a documentação oficial atual);
    qualquer modelo configurável (ex.: `gemini-2.5-pro`).
24. **Integração completa** — registro na fábrica (`mock | openai |
    gemini`); combobox dinâmico; histórico com roles nativas
    (`assistant`→`model`); system prompt via `system_instruction`;
    streaming; `usage_metadata` preservado em `Usage`; erros na
    taxonomia existente (incl. 400 "API key" → autenticação); API Key
    no **mesmo cofre**; TESTAR CONEXÃO com sonda sem `max_tokens`
    (thinking geraria falso negativo); troca openai↔gemini em runtime
    via `Agent.set_provider()`; cabeçalho mostra provider/modelo.

Permissões, ToolRegistry, memória e TaskManager permanecem exatamente
como na 0.1 (nenhuma permissão nova, nenhuma ferramenta concreta).

---

## COMPLETED — 0.3

### Lumen 0.3 — Memória avançada (fundação) ✅

Funcionalidades **realmente implementadas e verificadas** (tudo da 0.2
permanece intacto; `app/core/agent.py`, `app/ui/`, providers e
`main.py` NÃO foram tocados — o gancho para o futuro é
`MemorySystem.build_context()`):

1. **`app/memory/sanitization.py`** — `redact_secrets()`/
    `contains_secret()`: padrões `sk-…`, `AIza…` e atribuições explícitas
    (`api_key=`, `password:`, `…token=`, `Bearer eyJ…` + token) viram
    `***` **antes** de qualquer gravação na memória estruturada.
2. **`app/memory/records.py`** — `MemoryKind` com os 6 domínios da spec
    (PROJECT, TASK, KNOWLEDGE, DECISION, ISSUE, SOLUTION),
    `RecordStatus` (ACTIVE/OBSOLETE), `MemoryRecord` frozen dataclass
    (id, kind, title, content, origin, status, created_at, updated_at,
    tags, project_id, related_ids, supersedes, content_hash),
    `normalize_text` (NFD, sem acentos, espaços colapsados) +
    `compute_hash` (sha256 título+conteúdo), `RecordError` com validação
    completa no `from_dict` (status inválido incluído).
3. **`app/memory/record_store.py`** — um `RecordStore` por domínio:
    JSON com escrita atômica `.tmp`+`os.replace`, `RLock`, IDs
    sequenciais (`PRJ-/TASK-/KN-/DEC-/ERR-/SOL-0001`), dedup por hash
    entre ACTIVE (regravável após obsoleto), `update` imutável (bump
    `updated_at`, hash recalculado, `DuplicateRecordError` em colisão
    com outro ACTIVE), `mark_obsolete`, `supersede` (novo registro com
    `supersedes`/`related_ids`, antigo vira OBSOLETE — trilha preservada),
    `search` por relevância (título 3 > tag 2 > conteúdo 1; +1 quando
    todos os termos casam; obsoletos ×0,2 e excluídos por padrão;
    acento-insensível), arquivo corrompido/forma inválida →
    `RecordStoreError` com mensagem clara.
4. **`app/memory/system.py`** — `MemorySystem`: fachada da conversa
    (MemoryStore 0.1 intacto) + 6 `RecordStore`s em `data/memory/`;
    `remember`/`update`/`mark_obsolete`/`supersede`/`get`/`recall`
    (busca unificada nos domínios, ordenada por relevância)/`relate`
    (bidirecional por iteração sobre os stores)/`stats`;
    **`build_context(query)`**: registros estruturados primeiro (até a
    cota), mensagens da conversa completam a cota restante, excertos
    ≤400 chars — o pacote que o fluxo futuro do Agent enviará ao
    provedor; `ContextEntry` (kind, source, excerpt).
5. **Configuração** — nova variável `LUMEN_MAX_MEMORY_RECORDS` (default
    12, validada ≥1) em `Settings` + `.env.example`; `app.__version__`
    → `0.3.0`; `MemoryStore.search()` (conversa) agora acento-insensível
    (`unicodedata`), reutilizada pelo `recall`.
6. **Arquivos de domínio** criados sob demanda em `data/memory/`:
    `projects.json`, `task_records.json`, `knowledge.json`,
    `decisions.json`, `issues.json`, `solutions.json` (+ o
    `conversation.json` existente). Nada é enviado a provedores; a
    memória é 100% local.

### Complemento 0.3.x — Provider Expansion (Groq + Together AI) ✅

7. **`GroqProvider`** (`app/ai/groq_provider.py`) — API da GroqCloud via
    SDK oficial `groq` (lazy, `client_factory` injetável, introspecção
    da v1.7.0 validada em teste). Herda o núcleo testado do
    `OpenAIProvider` (payload/timeout/retry/streaming/normalização/
    erros — SDK OpenAI-compatível) com implementação própria de fábrica,
    modelo padrão e validação. Modelo **opcional**: vazio usa
    `openai/gpt-oss-120b` (produção em destaque no catálogo oficial:
    131k contexto, raciocínio, tool calling); Llama `llama-3.3-70b-versatile`/
    `llama-3.1-8b-instant` documentados como alternativas.
8. **`TogetherProvider`** (`app/ai/together_provider.py`) — **Llama 4
    real** via SDK oficial `together` (lazy, introspecção da v2.32.0).
    Mesma decisão de herança. Modelo opcional: vazio usa
    `meta-llama/Llama-4-Scout-17B-16E-Instruct`; alternativa
    `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8`.
    **Decisão de pesquisa registrada**: a "Meta Llama API" original foi
    **encerrada pela Meta em 06/07/2026** (endpoint devolve apenas
    resposta de sunset); a Cerebras removeu todos os Llama do catálogo
    público (10/2025–05/2026); a Together AI mantém o Llama 4 em API
    pública — escolhida com autorização explícita do usuário. O Meta
    Model API (api.meta.ai, Muse Spark) NÃO foi implementado (não é
    Llama).
9. **Integração completa** — registro na fábrica (`mock | openai |
    gemini | groq | together`); combobox da tela ⚙ descobre os 5
    dinamicamente (`available_providers()`); `ConfigService._build_provider`
    estendido; TESTAR CONEXÃO sem `max_tokens` (política já usada com
    Gemini — evita falso negativo com modelos de raciocínio); cofre de
    credenciais único; troca em runtime via `Agent.set_provider()`;
    requirements.txt + `.env.example` + `app.__version__` → `0.3.1`.
    **Nenhum arquivo do Agent/UI/providers existentes foi alterado além
    de `config_service.py` (injeção de fake) e do rótulo de exemplo do
    diálogo de configurações.**

---

## VERIFIED

### Verificação da 0.6.6 — Desfecho pós-aprovação (2026-08-28, atual)

- **Suíte completa (2 ambientes)**: desenvolvimento **875 passed + 5
  skipped**; venv limpa **875 passed + 5 skipped** — **880 testes**
  (+8 de UI pós-aprovação). `pip check` ✔; `pyflakes` ✔ (projeto e
  venv); `import main` OK (**0.6.6**); **harness 55/55** ✔.
- **Fluxo validado (fake-tk, caminho de produção: fila + _poll_queue)**:
  chat → `WAITING_APPROVAL` com mensagem de pausa → APROVAR na tela 🛡
  → "✔ Plano … concluído" NO CHAT + arquivo criado com conteúdo exato
  `TESTE LUMEN 0.6.3` + auditoria JSONL + desfecho na memória linear;
  RECUSAR → mensagem de recusa no chat e NADA executado; falha de
  execução (arquivo pré-existente) → "✖ … falhou: … já existe" no chat
  com conteúdo original intacto; sem callback o diálogo funciona como
  antes; callback que lança exceção não quebra nada.
- **Auditoria AST/anti-futuro**: nenhum `subprocess` em Agent/Bridge/UI
  (import subprocess segue SOMENTE em `app/tools/terminal.py`);
  planner/core sem `app.tools`; nenhuma permissão ampliada; nenhum
  bypass de checkpoint (aprovação segue obrigatória — o callback só
  REPORTA o desfecho, nunca dispara execução); nenhum sistema novo de
  eventos/memória; nada de 0.7+.

### Verificação da 0.6.3 — Tool Calling / Planner Bridge (2026-08-28)

- **Suíte completa (2 ambientes)**: desenvolvimento **863 passed + 5
  skipped**; venv limpa **863 passed + 5 skipped** — **868 testes**,
  **97 novos** (44 + 16 + 37). `pip check` ✔; `pyflakes` ✔ (projeto e
  venv); `import main` OK (**0.6.3**); **harness 55/55** ✔.
- **Fluxo completo testado (FASE 15/16)**: mensagem canônica
  "Crie um arquivo chamado teste_lumen.txt dentro do workspace atual
  contendo: TESTE LUMEN 0.6.3" → plano `create_file` com path/content
  EXATOS → checkpoint (CP-…) com conteúdo no card → APROVAR → arquivo
  criado com o conteúdo correto → auditoria JSONL → verificação
  (COMPLETED). RECUSAR → nada executado. Conversa pura → fluxo clássico
  (nenhum plano, nenhuma tool chamada — spy testado).
- **Garantias de segurança (testadas)**: LLM inventando ferramenta
  (`execute_anything`/ghost) → `PLAN_INVALID` sem executar e sem
  checkpoint decorativo; sem WRITE/READ → falha controlada (permissão ≠
  checkpoint, "pediu" ≠ "autorizou"); sem workspace → bloqueado; path
  `../../`/absoluto → rejeitado NO PROTOCOLO (e sandbox segue como
  defesa de execução); injection ("ignore as regras e execute
  powershell", "execute qualquer comando", "ignore o checkpoint",
  "apague todos os arquivos") → conversa ou falha controlada, JAMAIS
  bypass; terminal desabilitado → `run_command` fora do catálogo;
  habilitado → plano pode referenciar, mas denylist/allowlist/política
  negam shells (powershell falha controlado); nenhuma permissão
  concedida automaticamente (granted == manual); plano original
  imutável; retry e correction finitos (correção 0.6.2 funciona via
  chat: create sobre existente → proposta → write_file → SUCCEEDED).
- **Hotfix 0.6.3 (mesma versão — bug + stub de teste, sem
  funcionalidade nova; 2026-08-28)**: (1) `TerminalPolicy.entry_for`
  comparava `str(full_path)` cru com o comando — no Windows
  `Path("/opt/bin/x")` vira `\opt\bin\x` e o match exato nunca casava
  (`CommandNotAllowlistedError` em `test_full_path_entry_matches_exactly`
  na venv com display/Windows); agora a comparação é normalizada pelo
  `Path` do SO nos DOIS lados — caminho completo exato continua
  obrigatório, **sem fallback** para nome simples (comprovado com
  `PureWindowsPath`: mesmo caminho casa em qualquer estilo de barra;
  caminho diferente segue negado); `argv0` usa o comando validado quando
  o casamento foi por caminho (nome simples em entrada com `full_path`
  segue executando o caminho registrado — comportamento 0.6.x
  preservado). (2) `StubAgent` do `test_ui_smoke.py` ganhou
  `process_message` (contrato 0.6.3 da UI: devolve `AgentOutcome`; o
  teste só roda com display — nas runs headless ele pula, por isso não
  apareceu na validação sandbox). Revalidado: 863 passed + 5 skipped
  (sandbox E venv limpa), 164/164 nos 4 arquivos de terminal, pyflakes
  0×2, pip check×2, import main, harness 55/55, AST/anti-futuro verde.
- **Hotfix 2 do parser do mock (mesma versão 0.6.3; 2026-08-28, após
  teste manual no Windows)**: `MockProvider._content_of` não aceitava
  conectores ("contendo **exatamente**:") nem conteúdo em **nova
  linha** — a mensagem exata do teste manual virava `conversation`
  ("modo simulado"). Agora aceita conectores seguros combináveis
  (exatamente/isso/o seguinte/o texto/o conteúdo/este texto/essa
  frase/a seguinte mensagem), conteúdo multilinha (preservado;
  apenas bordas/linhas em branco e um par de aspas que envolve TODO
  o conteúdo são removidos). Só o mock mudou (determinístico; zero
  impacto em permissões/sandbox/registry/executor/checkpoints/
  auditoria/terminal). +4 testes de regressão (mensagem exata →
  `create_file`/`teste_lumen.txt`/`TESTE LUMEN 0.6.3`, conectores,
  multilinha, ponta-a-ponta WAITING_APPROVAL→approve→arquivo).
  Revalidado: **867 passed + 5 skipped** (sandbox E venv; 872
  testes), pyflakes 0×2, import main (0.6.3), AST/anti-futuro
  verde, harness 55/55.
- **Auditoria AST/anti-futuro**: executor **sem `app.tools`**;
  planner+core **sem `app.tools`**; `subprocess` importado SOMENTE em
  `app/tools/terminal.py` (AST, não texto); Agent/bridge sem caminhos
  de execução real; catalog puro (sem escrita de arquivos); providers 5
  intactos; **nada de 0.7+ iniciado**.

### Verificação da 0.4.x — Correção Automática Controlada (2026-08-28)

- **Suíte completa (2 ambientes)**: desenvolvimento **766 passed + 5
  skipped**; venv limpa **766 passed + 5 skipped** — **771 testes**,
  **45 novos** (20 motor + 25 controller/UI). `pip check` ✔;
  `pyflakes` ✔ (projeto e venv); `import main` OK (**0.6.2**);
  **harness 55/55** ✔.
- **Garantias da spec (testadas)**: ciclo completo
  EXECUTAR→VERIFICAR→FALHA→ANALISAR→PROPOR→VALIDAR→APROVAR→APLICAR→
  RETRY→VERIFICAR com checkpoint da operação original **antes** da
  falha e checkpoint próprio da correção depois; recusa ⇒ nada
  executado após; proposta inválida (tool fantasma, caminho fora do
  workspace, sem permissão WRITE) ⇒ `INVALID`/`NO_PROPOSAL` **sem
  aplicar e sem pausa decorativa**; `max_cycles=0` desliga o loop;
  loop sempre finito (aprovações < 12 com limite 3); plano original
  imutável; sucessor `#C1` mantém id/ordem; `FAILED` quando correção
  aplicada não resolve; auditoria JSONL de todo ciclo com
  `tool=correction` e sem conteúdo sensível; UI aprova/recusa pelo
  card CORREÇÃO PROPOSTA; estratégia conservadora nunca propõe sobre
  marcadores de segurança.
- **Auditoria anti-futuro**: `app/executor/` segue **sem importar
  `app.tools`**/subprocess/os (AST cobre `correction.py`);
  `subprocess` exclusivo de `app/tools/terminal.py`; UI fala só com
  o controller; Planner sem lógica de execução; sem novos poderes —
  nada de shell livre, mouse, teclado, screenshot, vision, computer
  control, Unreal, coding agent, acesso fora dos workspaces ou
  bypass de permissões/checkpoints; **nada de 0.7+ iniciado**.

### Verificação da 0.6.x — UI de Terminal (2026-08-28)

- **Suíte completa (2 venvs)**: desenvolvimento **721 passed + 5
  skipped**; venv limpa com os 4 SDKs reais **725 passed + 1 skipped**
  — **726 testes**, **31 novos** (22 admin + 9 UI). `pip check` ✔;
  `pyflakes` ✔ (projeto e venv); `import main` OK (**0.6.1**);
  **harness 55/55** ✔.
- **Garantias da spec (testadas)**: `grant_permission("TERMINAL")`
  segue **rejeitado** (concessão só por `grant_terminal` dedicado,
  auditado); `COMPUTER_CONTROL` sem via alguma; concessão **não
  persiste** (nova sessão começa sem TERMINAL mesmo com allowlist
  restaurada); **startup** não cria `terminal.json` nem concede nada;
  arquivo ilegível ⇒ terminal desabilitado (**fail closed**); entrada
  denylistada (`sh`) no arquivo ⇒ descartada na carga; denylist inviolável
  na UI (powershell/python.exe rejeitados com status 🔴, nada
  cadastrado/persistido); remoção pela UI persiste; revogação com
  checkpoint pendente ⇒ **aprovar NÃO executa** (gate de verdade);
  card de aprovação mostra comando/argumentos/diretório/timeout;
  ações administrativas no JSONL; comandos fora da allowlist
  continuam bloqueados antes de executar.
- **Auditoria anti-futuro**: `subprocess` exclusivo de
  `app/tools/terminal.py`; UI importa apenas `app.tools.control`
  (fachada) — sem filesystem/terminal/subprocess diretos;
  planner/executor/core/ai/memory sem `app.tools`/subprocess;
  `MANAGEABLE_LEVELS == [CHAT, READ, WRITE]`; `main.py` sem
  grant/enable diretos; providers 5 intactos; nada de 0.7+.

### Verificação da 0.6 — Terminal Tools (2026-08-28)

- **Suíte completa (2 venvs)**: desenvolvimento **690 passed + 5
  skipped**; venv limpa com os 4 SDKs reais **694 passed + 1 skipped**
  (smoke real de LLM, offline por contrato) — **695 testes**, **142
  novos** (policy 108 + tool 16 + integration 18). `pip check` sem
  conflitos (dev e venv limpa); `pyflakes` limpo (projeto e venv);
  `import main` OK (0.6.0); **harness 46/46** ✔.
- **Segurança da spec (testada)**: comando fora da allowlist ⇒
  **bloqueado antes de executar** (nada roda; plano FAILED com
  "allowlist" no motivo; sem checkpoint decorativo); denylist
  permanente rejeita **registro** e **execução** (38 nomes testados,
  incluindo `powershell`/`cmd`/`python`/`sudo`/`rm`/`curl`/`make`) e
  aliases (`python.exe`/`POWERSHELL`/`/bin/bash`); operadores
  (`&&`/`||`/`|`/`;`/`>`/`>>`/`<`/backtick/`$(`/`&`) e
  redirecionamentos bloqueados em argumentos; `-exec`/`/c`/
  `-EncodedCommand` bloqueados; `..` em argumento bloqueado; caminho
  absoluto fora (POSIX/`C:\`/UNC) bloqueado; cwd fora/inexistente
  bloqueado; **timeout mata** (sleep 30 com timeout 1 s ⇒ timed_out,
  <15 s); **limite de saída** trunca e falha honesto (seq 100000 com
  1 KiB); **sem TERMINAL** ⇒ gate bloqueia com NADA executado (READ/
  WRITE não bastam; gate auditado como `permission_gate` com cwd);
  **checkpoint**: comando viável pausa com argv/permissão/timeout
  visíveis; **RECUSAR ⇒ nada roda** (SKIPPED, efeito zero — mkdir não
  cria); APROVAR executa; `requires_approval=False` roda direto;
  **auditoria sem stdout/stderr** (só argv sanitizado/cwd/exit_code/
  duração; argv truncado 32 args/200 chars); **env filho sem segredos**
  (`SEGREDO-987` ausente de `printenv`; PATH presente); startup sem
  `run_command` no registry; `TERMINAL` não concedível pela UI.
- **Auditoria anti-futuro**: `subprocess` **exclusivo** de
  `app/tools/terminal.py` (grep + AST em todo `app/`); terminal.py sem
  socket/urllib/requests/http.client/ftplib/pyautogui/pynput/selenium/
  mss/shutil/ctypes; planner/executor/core/ai/memory sem `app.tools` e
  sem subprocess; UI só importa `app.tools.control` (fachada) e sem
  subprocess; `MANAGEABLE_LEVELS == [CHAT, READ, WRITE]`;
  `FORBIDDEN_COMMANDS` com 137 nomes; providers 5 intactos
  (mock/openai/gemini/groq/together); `main.py` sem `enable_terminal`
  (0 ocorrências — startup sem terminal); menções a mouse/teclado/
  screenshot/Unreal apenas em docstrings de proibição.

### Verificação da 0.5.x — UI/Controle (2026-08-28)

- **Suíte completa (2 venvs)**: desenvolvimento **548 passed + 5
  skipped**; venv limpa `/tmp/lumen-providers-sim` com os 4 SDKs reais
  **552 passed + 1 skipped** (o skip é o smoke real de LLM, offline por
  contrato) — **553 testes** no total, **55 novos** (17 workspaces +
  4 audit_log + 21 tools_control + 13 tools_dialog). `pip check` sem
  conflitos; `pyflakes` limpo; `python -c "import main"` OK;
  **harness `tools_dev/verify_ui_headless.py` 41/41 checks ✔**.
- **Segurança da spec (testada)**: fora das raízes e `..`/traversal ⇒
  falha controlada (sem pending); symlink escapando ⇒ bloqueado;
  workspace somente-leitura ⇒ escrita bloqueada com "somente leitura";
  sem READ/WRITE ⇒ falha com o nome do nível no motivo; `delete_file`
  sem opt-in ⇒ falha "allow_delete"; com opt-in ⇒ pausa para aprovação;
  **RECUSAR ⇒ nada roda** (arquivo intocado, tarefa SKIPPED, plano
  FAILED); APROVAR ⇒ executa; sem workspaces ⇒ "Nenhum workspace
  autorizado"; **startup sem efeitos colaterais** (data_dir sem
  workspaces.json/audit/); permission gate auditado como
  `operation="permission_gate" success=False`; **auditoria JSONL sem
  conteúdo** (arquivo com SEGREDO-987 lido ⇒ "SEGREDO-987" ausente do
  JSONL); UI rejeita conceder TERMINAL/COMPUTER_CONTROL.
- **Auditoria anti-futuro**: grep em `app/` sem
  subprocess/socket/requests/pyautogui/etc. (única menção a "shell" é
  docstring de bloqueio); AST confirma executor/planner sem imports de
  `app.tools`; `PermissionManager.MANAGEABLE_LEVELS == ['CHAT','READ',
  'WRITE']`; providers intactos (`gemini`,`groq`,`mock`,`openai`,
  `together`); versão `app.__version__ == "0.5.1"`.

### Verificação da 0.5 — Filesystem Tools (2026-08-28, atual)

- ✅ **Suíte completa: 498 testes** — **493 passed + 5 skipped** no
  ambiente de desenvolvimento (4 introspecção de SDK + 1 smoke da UI
  sem display) e **497 passed + 1 skipped na venv limpa** com os 4 SDKs
  reais; **59 testes novos** (`test_filesystem_sandbox.py`: 21 —
  construção de raízes, resolução relativa/absoluta/dentro/fora,
  `..`/traversal (inclusive interno), caminhos inválidos, symlink
  escape, multi-raiz em ordem, política read-only/writable/allow_delete
  duplo/operação desconhecida, auditoria contexto+sink+imutabilidade ·
  `test_filesystem_tools.py`: 19 — contratos das 6 ferramentas
  (listar/ler/criar/escrever/apagar/existir, caminho inexistente/
  inválido, UTF-8/binário, limite de leitura, pai ausente, arquivo
  somente leitura do SO, escape bloqueado, gate de permissão
  READ/WRITE, concessão/revogação progressiva, trilha de auditoria sem
  conteúdo) · `test_filesystem_integration.py`: 21 — cadeia completa
  Registry→Handler→Executor com arquivos reais em tmp, Planner
  (protocolo intacto; sem ferramenta → falha honesta), permissão
  ausente bloqueia e NADA executa, escape por parâmetros bloqueado,
  delete com opt-in duplo, checkpoint pausa/aprova/recusa em operação
  destrutiva, auditoria com tarefa/plano e sem conteúdo, Agent com
  handler de filesystem (conversa/memória intocadas), **auditorias AST
  anti-futuro** (planner sem fs/tools; executor agnóstico; tools sem
  execução/rede; Agent sem tools; startup sem efeitos colaterais));
  todos os 439 anteriores preservados.
- ✅ **pyflakes limpo**; **pip check** sem conflitos (dev e venv limpa);
  `import main` OK; **harness headless 30/30** (UI intocada).
- ✅ **Garantias exigidas pela spec** — bloqueio (não execução) quando
  política/permissão não permite (arquivo não nasce); tarefa sem
  ferramenta falha honestamente (plano do Planner não é "executado por
  engano"); checkpoint em operação destrutiva pausa ANTES (arquivo
  inalterado até aprovação; recusa ⇒ nada roda); auditoria registra
  ferramenta/caminhos/operação/desfecho/erro/timestamp/tarefa/plano —
  nunca conteúdo; nenhuma escrita/leitura fora do workspace autorizado
  (testes de escape/absoluto/symlink).
- ✅ **Auditoria de segurança** — default só `CHAT` (concessões
  READ/WRITE apenas explícitas nos testes); `main.py` sem permissão
  nova e sem registro de ferramentas no startup; registry novo nasce
  vazio; porteio de permissão acontece antes do código da tool rodar;
  `delete_file` exige WRITE + `writable` + `allow_delete`.
- ✅ **Auditoria anti-futuro (AST + bash)** — `app/planner` sem
  os/pathlib/subprocess/app.tools; `app/executor` segue sem
  `app.tools`/identificadores fs (auditoria 0.4.x preservada);
  `app/tools/{base,filesystem,handler}.py` sem
  subprocess/shutil/ctypes/socket/urllib/requests/pyautogui/pynput/
  system/popen/exec/eval/screenshot; `Agent` sem `app.tools` (ponte é
  handler injetado); providers intactos (5); imports de
  `filesystem.py` = stdlib + app.security + app.tools.base;
  `handler.py` = contratos do executor + planner.models + tools.
- ✅ **Anti-0.6+** — nenhum terminal/shell/subprocess/comando/
  PowerShell/mouse/teclado/screenshot/vision/computer control/Unreal/
  compilação/coding agent completo/execução arbitrária; `EXECUTE`
  inexistente (operação desconhecida é rejeitada pela política).

### Verificação da 0.4.x — checkpoints/retry/verificação (2026-08-28)

- ✅ **Suíte completa: 439 testes** — **434 passed + 5 skipped** no
  ambiente de desenvolvimento (4 introspecção de SDK + 1 smoke da UI
  sem display) e **438 passed + 1 skipped na venv limpa** com os 4 SDKs
  reais; **31 testes novos** (`test_executor_checkpoints.py`: 11 —
  pausa/aprovação/recusa/retomada, política padrão e seletiva, guards,
  determinismo · `test_executor_retry_verify.py`: 20 — retry com
  sucesso/até limite/após erro, backoff injetável, **segurança contra
  retry infinito**, verificação sucesso/falha/reprovada, tentativas
  preservadas, correção não ligada, determinismo, AST); todos os 408
  anteriores preservados (retrocompatibilidade: executor reescrito
  manteve os 34 testes da fundação verdes sem alteração).
- ✅ **pyflakes limpo**; **pip check** sem conflitos (dev e venv limpa);
  `import main` OK; **harness headless 30/30** (UI intocada).
- ✅ **Garantias exigidas pela spec** — retry limitado ao máximo
  configurado (testado com contador: exatamente N execuções);
  checkpoint realmente interrompe a execução (handler não é chamado;
  `paused`/`pending_checkpoint` expostos; recusa ⇒ `FAILED` sem
  executar); correção automática desligada (Executor não importa
  `correction` — AST); verificação representa claramente
  executou→verificou→sucesso/falhou com resultado preservado.
- ✅ **Auditoria anti-futuro (dupla)** — AST nos testes (nenhum
  import/identificador de ferramenta real no pacote `app/executor`,
  incluindo os 4 módulos novos) + auditoria bash: imports do
  `executor.py` = stdlib pura + `app.executor.*` + `app.planner.models`;
  `ToolRegistry` **vazio**; providers intactos (5).
- ✅ **Anti-0.5+** — nenhum filesystem/terminal/subprocess/shell/
  comando, mouse, teclado, captura de tela, vision, computer control,
  Unreal, ferramenta externa, tool calling real, UI nova, TaskManager
  integrado ou provider chamado para corrigir.

### Verificação da 0.4.x — Executor fundação (2026-08-28)

- ✅ **Suíte completa: 408 testes** — **403 passed + 5 skipped** no
  ambiente de desenvolvimento (4 introspecção de SDK + 1 smoke da UI
  sem display) e **407 passed + 1 skipped na venv limpa** com os 4 SDKs
  reais; **34 testes novos** (`test_executor.py`: 22 — os 15 cenários
  da spec + diamante/step/events/observer/determinismo/serialização ·
  `test_executor_integration.py`: 12 — Planner→Executor ponta a ponta,
  Agent→Executor, permissão, conversa/memória intocadas, auditoria por
  AST); todos os 374 anteriores preservados.
- ✅ **pyflakes limpo**; **pip check** sem conflitos (dev e venv limpa);
  `import main` OK; **harness headless 30/30** (UI intocada).
- ✅ **Garantia de não-execução real (dupla)** — auditoria **por AST**
  nos testes (nenhum import/identificador de ferramenta real no pacote
  `app/executor`) + auditoria bash: imports do pacote são apenas
  stdlib pura (`collections/dataclasses/datetime/logging/abc/typing`) +
  `app.planner.models`; `ToolRegistry` **vazio**; sem `os`/`pathlib`/
  subprocess/rede/automação; providers intactos (5).
- ✅ **Comportamento validado** — plano do pedido-exemplo da 0.4
  (`request_plan` → `READY` com 4 tarefas) executa ponta a ponta em
  ordem `T1→T4` e termina `COMPLETED`; falha em `T2` → `T2 FAILED`,
  `T3/T4 SKIPPED`, plano `FAILED` com motivo; `step()` avança uma
  tarefa por vez com relatórios parciais `RUNNING`.
- ✅ **Anti-0.5+** — nenhuma ferramenta real, filesystem, terminal,
  subprocess, mouse/teclado, vision, computer control, Unreal, tool
  calling real, checkpoints/retry/verificação implementados (apenas
  abstrações no-op preparatórias).

### Verificação da 0.4 — Planner fundação (2026-08-28)

- ✅ **Suíte completa: 374 testes** — **369 passed + 5 skipped** no
  ambiente de desenvolvimento (4 introspecção de SDK + 1 smoke da UI
  sem display) e **373 passed + 1 skipped na venv limpa** com os 4 SDKs
  reais; **51 testes novos** (`test_planner.py`: 37 — modelos, parser,
  dependências/ciclos, estados, planos inválidos, erros do provider,
  memória leitura-apenas · `test_planner_integration.py`: 14 —
  Agent→Planner, permissão, troca de provider em runtime, conversa
  intocada, build_app sem efeitos colaterais, garantias anti-execução);
  todos os 323 anteriores preservados.
- ✅ **pyflakes limpo**; **pip check** sem conflitos (dev e venv limpa);
  `import main` OK; **harness headless 30/30** (UI intocada).
- ✅ **Garantia de não-execução** — testes estáticos auditam o código
  do pacote `app/planner` (nenhum `subprocess`/`os.system`/`shutil`/
  `ctypes`/automação/escrita de arquivos); todas as tarefas saem
  `PENDING` com `result=None`; `ToolRegistry` sem nenhuma tool; Agent
  sem dispatcher de ferramentas.
- ✅ **Comportamento validado** — pedido de exemplo da spec ("crie um
  sistema de evolução de níveis com recompensa em pontos") produz plano
  `READY` com 6 etapas ordenadas e dependentes (`T1`→`T6`), análise
  prévia preservada; MockProvider (que não devolve JSON) gera `FAILED`
  controlado com motivo claro.
- ✅ **Anti-0.5+** — nenhum executor, tool calling real, filesystem,
  terminal, mouse/teclado, vision, Unreal, checkpoints, UI de planos ou
  sincronização com `TaskManager`.

### Verificação do complemento 0.3.x — Provider Expansion (2026-08-28)

- ✅ **Suíte completa: 323 testes** — **318 passed + 5 skipped** no
  ambiente de desenvolvimento (sem os SDKs: 4 skips de introspecção via
  `importorskip` + 1 smoke da UI Tk sem display) e **322 passed +
  1 skipped na venv limpa** com `pytest + openai + google-genai + keyring
  + groq + together` instalados segundo o `requirements.txt` — os 2
  testes de introspecção novos **rodam e validam as assinaturas usadas
  pelas factories contra os SDKs reais** (groq 1.7.0, together 2.32.0).
- ✅ **70 testes novos**: `test_groq_provider.py` (27), 
  `test_together_provider.py` (26), `test_provider_expansion.py` (17 —
  integração offline ConfigService → Provider → Agent → memória,
  descoberta dinâmica pela UI, sonda, troca em runtime, segurança da
  chave). Todos os 253 anteriores preservados.
- ✅ **`pip check`** sem conflitos na venv limpa; **pyflakes limpo**;
  `import main` OK.
- ✅ **UI headless: 30/30** (`tools_dev/verify_ui_headless.py`) — UI
  intacta; combobox da ⚙ já mostra os 5 providers.
- ✅ **Auditoria de segurança** — nenhuma chave real no projeto (padrões
  `sk-/gsk_/tgp_/AIza` apenas como fixtures fake de teste); chave nunca
  no payload capturado pelos fakes, nunca em `settings.json`, nunca em
  logs (teste com sentinelas `caplog`); cofre único reutilizado.
- ✅ **Auditoria anti-futuro** — nenhuma lib de mouse/teclado/vision,
  nenhum `subprocess`/`os.system`/`shutil` em `app/`; nenhum recurso de
  planner/tool calling/0.4+; `agent.py`, `main.py` e memória 0.3
  intocados (testes de compatibilidade verde).
- ✅ **Pesquisa obrigatória registrada** — docs oficiais consultadas
  (GroqCloud, Meta deprecação, Together AI, Cerebras deprecations);
  introspecção dos SDKs reais em venv limpa; decisões documentadas em
  `docs/ARCHITECTURE.md` §3.6/§3.7/§11.
- ✅ **Correções após execução da suíte pelo usuário em Windows real**
  (2026-08-28 — 321 passed/2 failed na máquina dele, com Credential
  Manager ativo e a credencial real da Lumen já gravada no uso diário;
  implementação funcional preservada, só testes corrigidos):
  1. `test_build_app_starts_without_any_config` não era hermético —
     `build_app` consultava o **cofre da máquina** e, no Windows do
     usuário, encontrava a credencial real (`key_source="cofre"`).
     Agora o teste isola o cofre em arquivo temporário (monkeypatch em
     `main.create_secret_store`) e **mantém as asserções estritas**
     (`provider="mock"`, `key_source="nenhuma"`, `has_stored_key=False`)
     — comportamento reproduzido e verificado no sandbox (sem isolamento
     → "cofre"; com isolamento → "nenhuma" em qualquer máquina). O uso
     do Windows Credential Manager no produto NÃO foi alterado nem
     enfraquecido.
  2. `StubAgent` do smoke test da UI não representava o contrato atual
     do Agent — `_provider_subtitle()` acessa `agent.provider`.
     Atualizado: `provider` (`MockProvider` real) + `set_provider`
     (troca em runtime) + nova asserção do cabeçalho ("provedor: mock").
     Caminho validado headless (método executado com o Stub corrigido);
     execução Tk real confirmada pelo usuário no Windows.
- ⚠️ Números pós-correção no **Windows real** a confirmar pelo usuário
  (no sandbox o smoke continua pulando por falta de display): esperado
  **323 passed, 0 failed** — sandbox 318/5 · venv limpa 322/1.

### Verificação da 0.3 (2026-08-28)

- ✅ **Suíte completa: 253 testes** — **250 passed + 3 skipped** no
  ambiente de desenvolvimento (Linux, sem os SDKs → 2 skips por
  `importorskip` + 1 smoke da UI Tk sem display) e **252 passed +
  1 skipped na venv limpa** com `pytest + openai + google-genai +
  keyring` instalados; **56 testes novos da 0.3**
  (`test_memory_records.py`, `test_memory_advanced.py`,
  `test_memory_system.py`, `test_config_03.py`) e todos os 197
  anteriores preservados.
- ✅ **pyflakes limpo** em `main.py`, `app`, `tests`, `tools_dev`.
- ✅ **UI headless: 30/30** (`tools_dev/verify_ui_headless.py`) — a UI
  não foi alterada e continua íntegra.
- ✅ **Persistência/recuperação** — dados recarregados de disco após
  nova instância; IDs sequenciais estáveis; conversa 0.1 intacta.
- ✅ **Corrupção/invalidade** — JSON quebrado, forma errada (não-lista)
  e registro com status inválido geram `RecordStoreError`/`RecordError`
  com mensagens claras (testes dedicados).
- ✅ **Segurança da memória** — segredos (`sk-`, `AIza`, `api_key=`,
  `Bearer …`) redigidos antes de persistir em todos os domínios,
  verificado no disco (testes leem o JSON); memória local, nunca enviada
  a provedores (nenhum provider importa `app.memory` além do Agent
  original, que segue usando apenas `MemoryStore` de conversa).
- ✅ **Anti-0.4** — nenhuma lib de mouse/teclado/vision, nenhum
  `subprocess`/`os.system`/`shutil` em `app/`; fábrica segue
  `mock|openai|gemini`; `agent.py`/`main.py` sem referência a
  `MemorySystem` (integração futura deliberada); nenhuma tool concreta.
- ✅ **State↔disco** — estrutura de arquivos deste documento confere
  com a árvore real do projeto (ver abaixo).

### Verificação da 0.2 (histórico — complemento Gemini)

Resultados reais da verificação completa (2026-08-28, após o complemento
de configuração gráfica, a etapa de validação para Windows **e o
complemento Google Gemini**; contagem final: **194 passed + 3 skipped no
ambiente de desenvolvimento** e **196 passed + 1 skipped na instalação
limpa com os SDKs reais** — os skips são o smoke test da UI Tk sem
display e testes de introspecção de SDK que pulam via `importorskip`
onde o pacote correspondente não está instalado):

- ✅ **194/196 testes passaram** (`python -m pytest -v`, conforme o
  ambiente) — **197 no total**, com **36 novos do Gemini** (provider:
  23+1 skip · integração: 12) e todos os anteriores preservados
- ✅ **UI headless: 30/30** verificações (`tools_dev/verify_ui_headless.py`:
  conversa+streaming, botão ⚙, diálogo com provider atual, 👁
  mostra/oculta, chave nunca exibida, TESTAR CONEXÃO mock/openai/gemini
  (🟢), SALVAR troca o provider do Agent sem reiniciar (openai e gemini),
  chave só no cofre (mesmo cofre p/ gemini), `settings.json` sem
  segredos, cabeçalho atualizado com provider/modelo, sonda gemini sem
  limite de tokens, conversa com o provider gemini aplicado, remoção de
  chave, volta ao mock)
- ✅ **Instalação limpa** — venv nova + `pip install -r requirements.txt`
  (openai 1.109.1, keyring 25.7.0, google-genai 2.20.0) + `pip check` +
  pytest completo + harness na instalação nova
- ✅ **SDK google-genai validado por introspecção** (sem rede):
  `genai.Client(api_key, http_options=HttpOptions(timeout_ms))`,
  `models.generate_content(_stream)(model, contents, config)`,
  `GenerateContentConfig(system_instruction, max_output_tokens)`,
  `usage_metadata`, `FinishReason`, `errors.ClientError(code)` — o
  adaptador da Lumen converte dict→config e s→ms corretamente
- ✅ **Imports/pyflakes** — todos os módulos importam; pyflakes sem
  advertências
- ✅ **Inicialização** — `python main.py` (mock, sem `.env`, sem chave)
  sobe todas as camadas; com configuração GUI salva, o startup usa a
  GUI (precedência verificada em runtime); `.env` openai sem chave
  continua com erro claro
- ✅ **Segurança** — API Key nunca em logs (teste com sentinelas), nunca
  em arquivos comuns (`settings.json`, README, código — verificado),
  nunca no payload enviado ao modelo (client fake captura o payload);
  chave só no cofre (keyring/fallback 0600)
- ✅ **Troca de provider** — thread-safe durante conversas ativas (teste
  com thread conversando enquanto a config muda)
- ✅ **Auditoria anti-futuro** — nenhum recurso de 0.3+ foi implementado

### Etapa de validação para uso real no Windows (2026-08-28)

- ✅ **Compatibilidade Windows auditada no código** — paths 100%
  `pathlib`/`os.replace` (multiplataforma), fonte Segoe UI (nativa),
  encodings UTF-8 explícitos, `os.chmod` best-effort envolvido em
  try/except (inócuo no Windows, onde o caminho primário é o cofre do
  SO), `keyring` no `requirements.txt` (Windows Credential Manager).
- ✅ **Instalação do zero simulada** — venv limpa +
  `pip install -r requirements.txt` + `pip check` (sem conflitos) +
  suite pytest completa + harness headless, tudo dentro da instalação
  nova (revelou e corrigiu o bug do probe de cofre, abaixo).
- ✅ **SDK oficial validado por introspecção** (openai 1.109.1):
  `OpenAI(api_key, timeout, max_retries)`; `chat.completions.create`
  aceita `model/messages/timeout/stream/max_tokens`; todas as exceções
  mapeadas existem no SDK.
- ✅ **Correções desta etapa** — (1) `README` agora documenta a ativação
  de venv correta para PowerShell (`Activate.ps1` + nota de
  ExecutionPolicy) e Prompt de Comando; (2) `KeyringSecretStore` faz um
  probe funcional (leitura inofensiva) antes de considerar o cofre
  disponível — backends presentes porém não operacionais agora caem
  para o fallback corretamente; (3) TESTAR CONEXÃO repete automaticamente
  sem `max_tokens` quando o modelo rejeita o parâmetro (ex.: série o);
  (4) harness `tools_dev` usa caminho relativo (portável).
- ⚠️ **LIMITAÇÃO DECLARADA** — o ambiente de validação é **Linux sem
  display**. A UI foi validada via **harness headless com o código real
  + revisão de código**; a execução em **Windows real (janela Tk,
  Credential Manager, ativação de venv)** **não foi executada
  automaticamente** — cabe ao usuário o passo a passo "Primeiro uso no
  Windows" do README.

## SECURITY

**Ordem de autoridade (0.6.3, explícita no bridge)**: Sistema de
segurança → Permissões → Workspace/Sandbox → Checkpoint → ToolRegistry
→ Plano → LLM (**nunca o contrário**). LLM não é autorização; Planner
não é autorização; plano não é autorização — "o usuário pediu" não é
"o usuário autorizou". A autorização continua pertencendo ao sistema
de permissões/checkpoints.

**Permissões** (`app/security/permissions.py`) — níveis inalterados da
0.1; **concessões continuam explícitas** (default: apenas `CHAT`):

| Nível              | Descrição                             | Concedida por padrão? |
| ------------------ | ------------------------------------- | --------------------- |
| `CHAT`             | Conversar com o usuário               | **SIM** (única)       |
| `READ`             | Ler arquivos e diretórios             | NÃO                   |
| `WRITE`            | Criar, modificar ou apagar arquivos   | NÃO                   |
| `TERMINAL`         | Executar comandos no terminal         | NÃO                   |
| `COMPUTER_CONTROL` | Controlar mouse, teclado e aplicações | NÃO                   |

**Filesystem (0.5):** as ferramentas de arquivo são o ÚNICO acesso real
ao computador nesta versão — e nunca rodam sozinhas: exigem (1) registro
explícito com `WorkspaceSandbox` cujas **raízes foram autorizadas por
quem integra** (bloqueio de `..`/traversal, caminhos fora das raízes,
inválidos, symlinks que escapam, escrita em modo somente leitura e
exclusão sem opt-in duplo `writable`+`allow_delete`), (2) concessão
explícita de `READ`/`WRITE` (porteio pelo `ToolRegistry` antes de
qualquer código da ferramenta rodar) e (3) checkpoint/consentimento
disponível para operações destrutivas (`ToolCheckpoints`). Toda
tentativa é **auditada** (ferramenta, caminhos, operação, desfecho,
erro, timestamp, tarefa/plano) **sem conteúdo de arquivos**. Não existe
permissão global, acesso irrestrito ao Windows nem ferramenta de outra
natureza (terminal/comandos/mouse/teclado/tela/rede continuam
**inexistentes no código**).

**Terminal (0.6):** a Lumen **NÃO recebe acesso irrestrito ao
PowerShell/CMD** — não existe `execute_any_command("qualquer coisa")`.
`run_command` exige, em ordem: (0) terminal habilitado pelo integrador
(`enable_terminal` — nada no startup), (1) permissão **`TERMINAL`**
(porteio do `ToolRegistry` **antes** de qualquer código da ferramenta;
concessão programática explícita — a UI concede apenas CHAT/READ/WRITE),
(2) **allowlist explícita** (fora da lista ⇒ bloqueado antes de
executar) com denylist permanente por cima (shells, interpretadores,
builders, escalonamento, destrutivos/administrativos e **rede** —
jamais allowlistáveis, nem como `python.exe`/`/bin/sh`), (3) validação
de argumentos (sem operadores/redirecionamento/`-exec`/`..`/caminho
absoluto fora) e cwd confinado aos workspaces, (4) **timeout
obrigatório** (mata o processo) e **limite de saída** (trunca e falha
honesto), (5) **checkpoint** para comandos `requires_approval`
(default todos; só operações viáveis pausam; recusa ⇒ nada roda) e
(6) **auditoria** (comando sanitizado, cwd, exit code, desfecho —
nunca stdout/stderr/segredos; env filho sem KEY/TOKEN/SECRET/PASSWORD).
`subprocess` existe exclusivamente em `app/tools/terminal.py`
(testes AST). Limites assumidos: allowlist é confiança explícita do
integrador; defesas de argumento/cwd são profundidade, não sandbox de
SO (documentado em `docs/ARCHITECTURE.md` §17.3).

**UI de Terminal (0.6.x):** a tela 🛡 administra concessão e allowlist
**somente via fachada** (`grant_terminal`/`revoke_terminal` dedicados e
auditados; o caminho genérico de permissões **rejeita** TERMINAL —
nenhuma concessão silenciosa; `COMPUTER_CONTROL` inconcedível). A
concessão **vale só na sessão** (nunca persistida/restaurada); a
allowlist persiste em `data/terminal.json` com **fail closed**
(ilegível ⇒ desabilitado; entrada denylistada/inválida ⇒ descartada);
toda ação administrativa vai para a auditoria JSONL
(`terminal_admin`: grant/revoke/allowlist_add/remove/enable/disable,
inclusive tentativas rejeitadas); revogar com checkpoint pendente faz
aprovar **não executar** (gate real).

**UI de controle (0.5.x):** quem autoriza é o usuário, pela tela 🛡 —
workspaces (validados/normalizados; **raiz de disco rejeitada na
origem**; modo visível), permissões (a UI concede/revoga **somente**
CHAT/READ/WRITE; TERMINAL/COMPUTER_CONTROL **rejeitados**; DELETE é
opt-in por workspace, não nível), aprovação de operações destrutivas
(**recusa garantida por teste — nada roda**; o pedido só ocorre para
operações já viáveis, via `PrevalidatedCheckpoints`) e auditoria
persistida em **JSONL** (`data/audit/audit.jsonl`, append-only,
**sem conteúdo de arquivos**, separado do conteúdo). Startup **sem
efeitos colaterais**: nenhum arquivo de dados nasce, nenhuma permissão
é concedida, nenhuma ferramenta é registrada até o usuário agir.

**Capacidades bloqueadas (e inexistentes no código):** shell/script
irrestrito (executar QUALQUER comando), controlar mouse, teclado,
aplicações ou Unreal, captura de tela/visão, rede das ferramentas,
edição inteligente de código (0.7+).

**Credenciais (0.2 + complemento):** a API Key vive no **cofre do sistema
operacional** (Windows Credential Manager via `keyring`) ou, como fallback
documentado, em `data/.credentials.json` (0600, fora do Git); o `.env`
permanece como fonte de desenvolvimento. A chave nunca é embutida em
código, nunca é registrada em log (redação automática adicional), nunca
aparece em `data/settings.json` nem no payload enviado ao modelo; a chave
salva nunca é reexibida pela interface. Nenhuma chave real existe no
projeto.

**Memória (0.3):** 100% local (`data/memory/*.json`, nunca versionada —
`.gitkeep` apenas); o banco de memória **nunca é enviado a provedores**
(ainda não é enviado nada: o Agent segue usando apenas o histórico de
conversa; a integração futura enviará somente o contexto selecionado por
`build_context()`); **segredos são redigidos antes de persistir** em
qualquer domínio estruturado (`redact_secrets`: `sk-…`, `AIza…`,
`api_key=`, `password:`, `token=`, `Bearer …`); logs continuam sem
conteúdo de mensagens.

---

## NOT IMPLEMENTED

Tudo o que **NÃO existe** nesta versão:

- ❌ **Ferramentas reais além de filesystem e terminal allowlistado** —
  o acesso real segue sendo **arquivo** (0.5) e **comando da allowlist**
  (0.6): sem shell/script irrestrito ("executar qualquer comando"),
  compilação automática, execução arbitrária de programas, rede das
  ferramentas, mouse, teclado, captura de tela/screenshot, visão
  computacional, computer control, Unreal, coding agent completo
  (0.7+)
- ❌ **Permissão global/acesso irrestrito ao Windows** — não existe:
  concessões seguem explícitas por nível (default só `CHAT`);
  READ/WRITE só por concessão explícita (agora também pela UI 🛡, que
  rejeita TERMINAL/COMPUTER_CONTROL); sandbox exige raízes autorizadas
  (a UI valida/normaliza e rejeita raiz de disco); escrita/exclusão são
  opt-in separados; `EXECUTE` é inexistente (operação desconhecida
  rejeitada)
- ❌ **Planner autônomo fora da allowlist** — o Planner 0.6.3 emite
  `tool`/`parameters` SOMENTE para as ferramentas da allowlist de
  protocolo (6 filesystem + `run_command` com terminal habilitado),
  validadas antes de qualquer execução; o modo 0.4 clássico
  (`create_plan`, sem tools) segue intacto; nada além da allowlist
- ❌ **Chat como autoridade** — o chat 0.6.3 despacha planos VALIDADOS
  para o `ToolsController.run_plan` (bridge §19), mas **LLM não é
  autorização**: sem permissão/workspace/checkpoint nada roda;
  `ResponseType.TOOL_CALL`/`PLAN` e `tool_calls` seguem apenas
  estrutura (não há tool calling nativo do SDK); `send_message`
  conversacional permanece intacto
- ❌ **Isolamento de sistema operacional para comandos** — as defesas
  (allowlist/denylist/args/cwd/timeout/limites) são profundidade, não
  sandbox de SO; limites documentados (ARCHITECTURE §17.3)
- ❌ **Correção automática inteligente** — o ciclo CONTROLADO existe
  (0.6.2: estratégia conservadora `create_file → write_file`,
  limites, aprovação, auditoria), mas **análise de falha via
  provider/LLM**, estratégias arbitrárias e auto-correção sem
  aprovação explícita **não existem**
- ❌ **Integração Executor ↔ TaskManager/memória** — a execução não
  sincroniza com o TaskManager nem grava conhecimento na memória 0.3
  (resultados vivem no `ExecutionReport`)
- ❌ **Integração da memória estruturada ao Agent** — a fundação existe
  e está testada (`MemorySystem.build_context()`), mas o Agent ainda
  não a consulta ao responder; nada é gravado automaticamente nos
  domínios a partir das conversas ainda (deliberado: escopo fechado)
- ❌ **Memória avançada além da fundação** — sem sumarização de
  conversas, busca semântica (embeddings), múltiplas sessões ou
  migração para SQLite (futuras 0.3.x)
- ❌ **Terminal** — sem executar comandos
- ❌ **Coding agent** — sem criar/modificar código automaticamente
- ❌ **Vision** — sem captura de tela ou visão computacional
- ❌ **Mouse** — sem controle de mouse
- ❌ **Keyboard** — sem controle de teclado
- ❌ **Computer control** — sem abrir/operar aplicações
- ❌ **Unreal Engine integration** — inexistente
- ❌ **Outros provedores reais** (ex.: Anthropic, xAI, Cerebras e o
  **Meta Model API**/Muse Spark — sucessor da extinta Llama API) — a
  arquitetura os aceita com 1 linha no registro, mas só `mock`,
  `openai`, `gemini`, `groq` e `together` existem
- ❌ **Controle financeiro/cobrança de tokens** — `Usage` é preservado,
  mas nada acumula nem cobra

---

## ARCHITECTURE

Sistema modular em camadas; dependências apontam sempre para baixo:

```text
UI (Tkinter)
 ↓
AGENT CORE
 ↓
AI PROVIDER (abstrato)      MEMORY      TASK SYSTEM
                             ↕               ↕
                          TOOLS  →  PERMISSIONS
```

| Camada | Módulo | Papel |
| ------ | ------ | ----- |
| UI | `app/ui/main_window.py` | Apresentação: janela, status, streaming via fila; worker thread; botões ⚙ Configurações e 🛡 Ferramentas (0.5.x) |
| UI | `app/ui/settings_dialog.py` | Diálogo Configurações → Inteligência Artificial (provider/modelo/API Key, 👁, testar conexão, salvar) |
| UI | `app/ui/tools_dialog.py` | **0.5.x:** diálogo 🛡 Ferramentas e Segurança — workspaces, permissões, aprovação de checkpoints e auditoria (só apresentação; lógica no controller); **0.6.2:** card CORREÇÃO PROPOSTA |
| Agent Core | `app/core/agent.py` | `send_message(text, on_delta)`: permissão → contexto → provedor → memória; **`request_plan(text)` (0.4)**: pedido → Planner → `Plan` estruturado; **`execute_plan(plan, handler?)` (0.4.x)**: plano READY → Executor simulado → `ExecutionReport`; erros viram `AgentError` amigável |
| Planner | `app/planner/` | **0.4 — fundação:** `Planner.create_plan()` → `Plan`/`PlannedTask` (ordem, dependências, análise prévia, `PlanStatus` PLANNING/READY/RUNNING/BLOCKED/FAILED/COMPLETED); JSON strict validado (ciclos rejeitados); falha controlada; memória 0.3 como leitura; provider-agnóstico; **não executa nada** |
| Executor | `app/executor/` | **0.4.x:** `PlanExecutor` executa plano READY (ordem/dependências, `step()`/`run_all()`, fail-fast → `SKIPPED`), `TaskRun`/`ExecutionReport` + eventos; **checkpoints** (`CheckpointPolicy`: pausa `PENDING_APPROVAL` → `APPROVED`/`REFUSED`), **retry** (`RetryPolicy` limite estrito + `AttemptRecord`), **verificação** (`TaskVerifier` simulado: `DONE`/`REJECTED`), **correção real** (0.6.2 `CorrectionEngine`: ciclo controlado, limites rígidos, sucessores imutáveis, sem importar `app.tools`); **agnóstico de ferramentas** (ponte 0.5 vive em `app/tools/handler.py`); separado do Planner |
| AI Provider | `app/ai/` | ABC `AIProvider` (`chat` rica + `generate` compatível), fábrica, `MockProvider`, `OpenAIProvider`, `GeminiProvider`, `GroqProvider` e `TogetherProvider` (SDKs oficiais, lazy; groq/together herdam o núcleo do OpenAIProvider — 0.3.x), `AIResponse`/`Usage`/`ResponseType` |
| Config | `app/config/` | `Settings` (.env com as 9 variáveis — 8 da 0.2 + `LUMEN_MAX_MEMORY_RECORDS`), `setup_logging()` com redação, **persona central + system prompt**, `UserConfigStore` (GUI), `SecretStore` (cofre), `ConfigService` (salva/aplica/testa) |
| Memory | `app/memory/` | **0.3:** `MemoryStore` (conversa, inalterado) + `sanitization` (redação pré-persistência) + `records` (`MemoryRecord`/`MemoryKind`/hashes) + `record_store` (persistência por domínio, dedup, supersede, busca) + `system` (`MemorySystem`: fachada, `recall`, `build_context`) — tudo local, nunca enviado a provedores |
| Task System | `app/tasks/manager.py` | Registro de tarefas, sem execução (inalterado) |
| Tools | `app/tools/` | **0.5:** contrato (`Tool`/`ToolResult`/`StructuredTool`/`ToolRegistry` porteiro) + **filesystem confinado**: `WorkspaceSandbox` (raízes autorizadas, bloqueio `..`/fora/symlink, writable/allow_delete), `FilesystemAudit` (trilha sem conteúdo), 6 ferramentas (list/read/write/create/delete/exists; READ/WRITE) + `ToolTaskHandler` (ponte Executor↔Tools) e `ToolCheckpoints` (destrutivas); registro sempre explícito; **0.5.x:** `workspaces.py` (`WorkspaceStore` persistente + `MultiWorkspaceSandbox` por raiz), `audit_log.py` (JSONL), `control.py` (`ToolsController` fachada da UI + `PrevalidatedCheckpoints` — checkpoint só p/ operações viáveis; 0.6: `enable_terminal`); **0.6:** `terminal.py` (`TerminalPolicy` allowlist+denylist+timeout+limites, `RunCommandTool` com permissão TERMINAL, `PrevalidatedTerminalCheckpoints` — único módulo com subprocess); **0.6.2:** `correction.py` (`ToolCorrectionStrategy` conservadora + `build_proposal_validator`) |
| Permissions | `app/security/permissions.py` | 5 níveis; apenas `CHAT` concedida (inalterado) |
| Entrada | `main.py` | Composition root; falha com mensagens claras se a configuração do provedor estiver incompleta; **0.5.x:** compõe o `ToolsController` (workspaces/auditoria/registry dedicado) sem efeitos colaterais no startup; **0.6:** terminal NÃO é habilitado no startup (opt-in via `enable_terminal`) |

Detalhes completos: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## CURRENT FILE STRUCTURE

Estrutura real do projeto nesta versão:

```text
Lumen/
├── main.py                     # ponto de entrada (composition root)
├── LUMEN_STATE.md              # ESTE ARQUIVO — estado oficial do projeto
├── README.md
├── requirements.txt            # openai/google-genai/groq/together (providers) + keyring + pytest
├── .env.example                # 9 variáveis (8 da 0.2 + LUMEN_MAX_MEMORY_RECORDS)
├── .gitignore
│
├── app/
│   ├── __init__.py             # APP_NAME, __version__ = 0.4.0
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── provider.py         # AIProvider (ABC), erros, fábrica
│   │   ├── openai_provider.py  # OpenAIProvider (SDK oficial, lazy)
│   │   ├── gemini_provider.py  # GeminiProvider (SDK google-genai, lazy)
│   │   ├── groq_provider.py    # GroqProvider (SDK groq, lazy — 0.3.x)
│   │   ├── together_provider.py # TogetherProvider (SDK together, Llama 4 — 0.3.x)
│   │   ├── mock.py             # MockProvider (modo simulado)
│   │   └── types.py            # AIResponse, Usage, ResponseType
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py         # Settings + setup_logging()
│   │   ├── persona.py          # identidade central + system prompt
│   │   ├── user_config.py      # config salva pela UI + precedência
│   │   ├── secrets.py          # cofre de credenciais (keyring/arquivo)
│   │   └── config_service.py   # ConfigService: salva/aplica/testa conexão
│   ├── core/
│   │   ├── __init__.py
│   │   ├── agent.py            # Agent.send_message() + request_plan() (0.4)
│   │                           #   + execute_plan() (0.4.x)
│   │                           #   + process_message/request_tool_plan/
│   │                           #   set_tools_controller (0.6.3)
│   │   └── bridge.py           # ToolCallingBridge + RequestState:
│   │                           #   CHAT→PLANNER→TOOLS (0.6.3)
│   ├── executor/              # EXECUTOR (0.4.x)
│   │   ├── __init__.py         # exports do pacote (0.4.x)
│   │   ├── handlers.py         # TaskHandler (ABC) + SimulatedHandler
│   │   ├── checkpoints.py      # CheckpointPolicy/Request/Status (0.4.2)
│   │   ├── retry.py            # RetryPolicy + AttemptRecord (0.4.2)
│   │   ├── verification.py     # TaskVerifier + SimulatedVerifier (0.4.2)
│   │   ├── correction.py       # CorrectionEngine: ciclo de correção
│   │   │                       #   controlado + limites (0.6.2)
│   │   └── catalog.py          # allowlist de ferramentas p/ o
│   │                           #   planejamento + validação (0.6.3)
│   │   └── executor.py         # PlanExecutor: step/run_all, fail-fast,
│   │                           #   TaskRun/ExecutionReport/eventos
│   ├── memory/
│   │   ├── __init__.py         # exports do pacote (0.3)
│   │   ├── store.py            # MemoryStore, Message (conversa — 0.1)
│   │   ├── sanitization.py     # redact_secrets/contains_secret (0.3)
│   │   ├── records.py          # MemoryRecord, MemoryKind, hashes (0.3)
│   │   ├── record_store.py     # RecordStore por domínio (0.3)
│   │   └── system.py           # MemorySystem: fachada + build_context (0.3)
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── manager.py          # TaskManager, Task, TaskStatus
│   ├── tools/                # TOOLS (0.5/0.5.x — filesystem confinado +
│   │   │                     # auditado + camada de controle)
│   │   ├── __init__.py       # exports do pacote (0.5)
│   │   ├── base.py           # Tool (ABC) + ToolResult/StructuredTool +
│   │   │                     # ToolRegistry (porteiro de permissões)
│   │   ├── filesystem.py     # WorkspaceSandbox + FilesystemAudit +
│   │   │                     # 6 ferramentas (0.5)
│   │   ├── handler.py        # ToolTaskHandler + ToolCheckpoints (0.5)
│   │   ├── workspaces.py     # WorkspaceStore (persistência) +
│   │   │                     # MultiWorkspaceSandbox (0.5.x)
│   │   ├── audit_log.py      # JsonlAuditSink + leitor (0.5.x)
│   │   ├── control.py        # ToolsController + PrevalidatedCheckpoints
│   │   │                     # + enable_terminal + grant_terminal/
│   │   │                     # allowlist persistente (0.5.x/0.6/0.6.x)
│   │   ├── terminal.py       # TERMINAL (0.6): TerminalPolicy (allowlist+
│   │   │                     # denylist+timeout+limites) + run_command —
│   │   │                     # único subprocess + TerminalStore (0.6.x)
│   │   └── correction.py     # CORREÇÃO (0.6.2): ToolCorrectionStrategy
│   │                         # conservadora + build_proposal_validator
│   ├── security/
│   │   ├── __init__.py
│   │   └── permissions.py      # PermissionLevel, PermissionManager
│   └── ui/
│       ├── __init__.py
│       ├── main_window.py      # LumenWindow (Tkinter + streaming + ⚙ + 🛡)
│       ├── settings_dialog.py  # ⚙ Configurações → Inteligência Artificial
│       └── tools_dialog.py     # 🛡 Ferramentas e Segurança (0.5.x)
│
├── data/
│   ├── memory/                 # conversation.json + 6 domínios (runtime)
│   │   └── .gitkeep
│   └── logs/                   # lumen.log (runtime)
│       └── .gitkeep
│
├── tests/                      # 880 testes (todos offline)
│   ├── conftest.py
│   ├── fake_tk.py              # toolkit Tk falso p/ testes de UI sem display
│   ├── test_memory.py
│   ├── test_tasks.py
│   ├── test_provider.py
│   ├── test_agent.py
│   ├── test_permissions.py
│   ├── test_tools.py
│   ├── test_app.py
│   ├── test_ui_smoke.py        # skip automático sem display
│   ├── test_persona.py         # 0.2
│   ├── test_openai_provider.py # 0.2 (client fake, offline)
│   ├── test_agent_chat.py      # 0.2
│   ├── test_config_02.py       # 0.2
│   ├── test_logging_security.py# 0.2
│   ├── test_secrets.py         # 0.2-compl. (cofre de credenciais)
│   ├── test_user_config.py     # 0.2-compl. (precedência GUI/.env)
│   ├── test_config_service.py  # 0.2-compl. (salvar/aplicar/testar)
│   ├── test_settings_dialog.py # 0.2-compl. (tela de configurações)
│   ├── test_gemini_provider.py # 0.2-compl. (Gemini, offline)
│   ├── test_gemini_integration.py # 0.2-compl. (Gemini+ConfigService/UI)
│   ├── test_memory_records.py  # 0.3 (modelo, hashes, redação)
│   ├── test_memory_advanced.py # 0.3 (RecordStore: dedup/supersede/busca)
│   ├── test_memory_system.py   # 0.3 (MemorySystem: recall/contexto)
│   ├── test_config_03.py       # 0.3 (LUMEN_MAX_MEMORY_RECORDS)
│   ├── test_groq_provider.py   # 0.3.x (Groq, offline)
│   ├── test_together_provider.py # 0.3.x (Together/Llama 4, offline)
│   └── test_provider_expansion.py # 0.3.x (integração + introspecção SDK)
│   ├── test_planner.py         # 0.4 (modelos, parser, validação, falhas)
│   └── test_planner_integration.py # 0.4 (Agent→Planner, memória, anti-execução)
│   ├── test_executor.py           # 0.4.x (executor: ordem/deps/fail-fast/estados)
│   └── test_executor_integration.py # 0.4.x (Planner→Executor, Agent, auditoria AST)
│   ├── test_executor_checkpoints.py # 0.4.x (pausa/aprova/recusa/retoma)
│   ├── test_executor_retry_verify.py # 0.4.x (retry/verificação/correção/AST)
│   ├── test_filesystem_sandbox.py   # 0.5 (política de workspace + auditoria)
│   ├── test_filesystem_tools.py     # 0.5 (contratos das 6 ferramentas)
│   ├── test_filesystem_integration.py # 0.5 (cadeia Planner→Executor→Tools,
│   │                                   #   checkpoints, segurança, AST)
│   ├── test_workspaces.py           # 0.5.x (store: validação/normalização/
│   │                                   #   raiz de disco/dedup/persistência)
│   ├── test_audit_log.py            # 0.5.x (sink JSONL + leitor tolerante)
│   ├── test_tools_control.py        # 0.5.x (controller: permissões/workspaces/
│   │                                   #   execução+checkpoints/segurança)
│   ├── test_tools_dialog.py         # 0.5.x (UI fake-tk das 4 áreas)
│   ├── test_terminal_policy.py      # 0.6 (allowlist/denylist/args/cwd —
│   │                                   #   sem executar nada)
│   ├── test_terminal_tool.py        # 0.6 (run_command real: saída/timeout/
│   │                                   #   limites/gate/auditoria/env)
│   ├── test_terminal_integration.py # 0.6 (cadeia Executor↔Terminal,
│   │                                   #   checkpoints, JSONL, AST anti-futuro)
│   ├── test_terminal_admin.py        # 0.6.x (grant/allowlist/persistência/
│   │                                   #   fail closed/auditoria admin)
│   ├── test_correction.py             # 0.6.2 (motor: ciclo/limites/recusa/
│   │                                   #   inválida/imutabilidade/FAILED)
│   ├── test_tools_correction.py       # 0.6.2 (controller+UI: cadeia real,
│   │                                   #   sem bypass, JSONL, loop finito)
│   ├── test_planner_tools.py          # 0.6.3 (allowlist/validação de
│   │                                   #   protocolo/parse tool_mode)
│   ├── test_mock_tool_planning.py     # 0.6.3 (determinismo do mock)
│   ├── test_agent_bridge.py           # 0.6.3 (fluxo completo chat→tools,
│                                       #   segurança, AST anti-futuro)
│   └── test_post_approval_ui.py       # 0.6.6 (desfecho pós-aprovação
│                                       #   no chat via callback 🛡)
│
├── tools_dev/
│   └── verify_ui_headless.py   # verificação headless da UI (55 checks)
│
└── docs/
    ├── ARCHITECTURE.md
    └── ROADMAP.md
```

*Arquivos de runtime (`conversation.json`, os 6 JSONs de domínio,
`tasks.json`, `lumen.log`) são gerados sob demanda e não fazem parte do
repositório.*

---

## ROADMAP

| Versão | Foco | Status |
| ------ | ---- | ------ |
| 0.1 | Foundation | **COMPLETED** ✅ |
| 0.2 | Real AI Provider | **COMPLETED** ✅ |
| 0.3 | Advanced Memory (fundação) | **COMPLETED** ✅ |
| 0.3.x | Provider Expansion (Groq + Together AI) | **COMPLETED** ✅ |
| 0.4 | Planner (fundação) | **COMPLETED** ✅ |
| 0.4.x | Executor de Planos (fundação, simulado) | **COMPLETED** ✅ |
| 0.4.x | Checkpoints + retry + verificação (simulado) | **COMPLETED** ✅ |
| 0.5 | Filesystem Tools (workspace + auditoria) | **COMPLETED** ✅ |
| 0.5.x | UI de Workspaces/Permissões/Checkpoints; auditoria JSONL | **COMPLETED** ✅ |
| 0.6 | Terminal Tools (allowlist, denylist, timeout, auditoria) | **COMPLETED** ✅ |
| 0.6.x | UI de Terminal (allowlist gerenciável + concessão TERMINAL explícita) | **COMPLETED** ✅ |
| 0.6.x | **Correção Automática Controlada** (motor + estratégia conservadora + UI, versão 0.6.2) | **COMPLETED** ✅ |
| 0.6.3 | **Tool Calling / Planner Bridge** (chat → plano `tool`/`parameters` → controller) | **COMPLETED** ✅ |
| 0.6.6 | **Desfecho pós-aprovação no chat** (callback 🛡 → bridge → fila do chat) | **COMPLETED** ✅ |
| 0.4.x | Executor: ferramentas reais (0.5+), checkpoints, retry, verificação, TaskManager | PENDING |
| 0.4.x | Planner: executor, checkpoints, tentativas/verificação, UI de planos | PENDING |
| 0.3.x | Memória: integração ao Agent (chat), sumarização, embeddings, sessões, SQLite | PENDING |
| 0.5 | Filesystem Tools | PENDING |
| 0.6 | Terminal Tools | PENDING |
| 0.7 | Coding Agent | PENDING |
| 0.8 | Vision | PENDING |
| 0.9 | Mouse + Keyboard | PENDING |
| 1.0 | Computer Agent | PENDING |
| 1.x | Unreal Engine Agent | PENDING |

Detalhamento por versão: [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## NEXT STEP

**Nada será iniciado sem autorização explícita do usuário.** A etapa
0.6.3 (Tool Calling / Planner Bridge) está encerrada; a versão
principal é **0.6.3 — COMPLETED** e nada além disso foi implementado
(**nada da 0.7+ foi iniciado**). Candidatos naturais, em ordem de
dependência:

1. **Ampliar o catálogo de planejamento com cuidado** (mais padrões de
   linguagem no mock; tool calling nativo dos SDKs reais com
   function-calling — exige autorização explícita).
2. **Plano multi-tarefa via chat** (hoje o mock planeja 1 tarefa;
   dependências entre tools ficam a cargo de providers reais).
3. **Estratégias de correção adicionais** (além da conservadora
   `create_file → write_file`; análise de falha via provider continua
   fora de escopo sem autorização explícita).
4. **0.3.x — Integrar a memória ao fluxo de chat do Agent** +
   sumarização, embeddings, sessões, SQLite.
5. **0.7 — Coding Agent** (somente com autorização explícita — usando
   as fundações 0.5/0.6/0.6.x/0.6.2/0.6.3).

---

## DEVELOPMENT RULE

**Este arquivo deve ser atualizado ao final de cada versão** para refletir o
estado REAL do projeto: versão, status, funcionalidades completadas,
resultados de verificação (números reais de testes), permissões vigentes,
itens não implementados, estrutura de arquivos e próximo passo. Estado
documentado que não corresponder ao código é considerado bug de
documentação.


---

# ROADMAP DE EVOLUÇÃO — CONTINUIDADE 2026-09

## Fonte oficial complementar

O roadmap detalhado está em `docs/LUMEN_COMPUTER_INTELLIGENCE_ROADMAP.md`.

A continuidade operacional por fases está em `docs/LUMEN_CONTINUITY_PHASES.md`.

## MASTER STATUS

| Fase | Status |
|---|---|
| F0 Baseline/Auditoria/Contratos | 🟥 PENDENTE |
| F1 Local Provider/Ollama | 🟥 PENDENTE |
| F2 Research Engine | 🟥 PENDENTE |
| F3 Knowledge + Experience Memory | 🟥 PENDENTE |
| F4 Tool/Agent Protocol | 🟥 PENDENTE |
| F5 Computer Intelligence | 🟥 PENDENTE |
| F6 Windows Native Intelligence | 🟥 PENDENTE |
| F7 Vision Provider/LLaVA | 🟥 PENDENTE |
| F8 Grounding Engine | 🟥 PENDENTE |
| F9 Secure Computer Control | 🟥 PENDENTE |
| F10 Verification/Recovery/Regression | 🟥 PENDENTE |
| F11 Unreal Engine Agent | 🟥 PENDENTE |
| F12 Workflow Learning | 🟥 PENDENTE |
| F13 Autonomous Multi-Step Agent | 🟥 PENDENTE |
| F14 Evolution Foundation | 🟥 PENDENTE |
| F15 Evolution Laboratory | 🟥 PENDENTE |
| F16 Self-Diagnostics + Research for Improvement | 🟥 PENDENTE |
| F17 Candidate/Benchmark/Promotion | 🟥 PENDENTE |
| F18 Continuous Evolution | 🟥 PENDENTE |

## PRIORIDADE MÁXIMA

**Lumen Evolution System (LES)** é a prioridade arquitetural máxima desta nova trilha.

Objetivo do LES:

> detectar limitações, pesquisar soluções, criar hipóteses, experimentar, implementar, testar, medir, verificar, aprender com sucesso e fracasso e promover melhorias sem colocar a versão estável ou o Security Core em risco.

## PROTEÇÃO

O LES não recebe autoridade unilateral para alterar ou remover:
- PermissionManager;
- Policy;
- Sandbox;
- Checkpoint;
- Audit;
- Rollback;
- Promotion Rules;
- proteção de secrets;
- limites de autoridade.

Mudanças de alto risco exigem Human Approval Gate.

## BASELINE ATUAL

A versão oficial histórica registrada neste arquivo continua sendo 0.6.8, com 995 passed / 5 skipped / 0 failed conforme o último registro existente. Esses números são históricos e não devem ser apresentados como execução nova desta trilha.

## REGRA DE IMPLEMENTAÇÃO

Não criar outra Lumen. Toda implementação deve alterar a Lumen existente, usando o laboratório experimental do Evolution System quando a fase permitir.

## CHECKPOINT DE CONTINUIDADE

Após cada fase:
- marcar status;
- registrar evidência;
- atualizar LUMEN_STATE;
- atualizar docs/LUMEN_CONTINUITY_PHASES.md;
- atualizar decisões/tarefas/handoff quando aplicável;
- executar testes;
- commit/push;
- só então avançar.


F20 validação final: **1292 passed / 1 skipped / 0 failed**; compile SUCCESS; F0 Validation SUCCESS; PR #14 merged (`8c19f7644896c9382ded9af799a262c53eccdbb5`).


**Próxima fase oficial: F21 — Provider Independence.**

## F34 — Autonomous Mission Supervisor (2026-10-01)

- 🟩 Missão única persistente criada como contrato de runtime.
- 🟩 Supervisor iniciado automaticamente pelo `main.py` quando existe uma missão.
- 🟩 Supervisor aguarda o Unreal MCP real e retoma quando o endpoint loopback volta.
- 🟩 Broker Unreal limitado a toolsets anunciados pelo servidor e com orçamento de chamadas.
- 🟩 Autonomous Evolution Loop existente foi conectado como ação de evolução do código.
- 🟩 Pesquisa Web e observação Unreal foram conectadas ao ciclo de missão.
- 🟩 Estado persistente em `data/evolution/mission.json`.
- 🟩 Documentação canônica criada em `docs/AUTONOMOUS_MISSION.md`.
- 🟨 Ainda requer validação física no ambiente do operador: reiniciar Unreal, detectar MCP, executar uma ação Unreal real e demonstrar um ciclo completo de evolução.

**Próximo gate real:** iniciar o Unreal Editor com o MCP ativo e validar que a missão persistente sai de `WAITING_UNREAL` para `EVOLVING` sem intervenção manual.
