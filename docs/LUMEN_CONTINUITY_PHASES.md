# F18 — MODEL ADAPTATION LABORATORY — 🟩 CONCLUÍDA

**Data:** 2026-09-27

## Evidência final

- laboratório de adaptação de modelos isolado;
- contratos para datasets, adaptações, experimentos, evidências e candidatos;
- suporte contratual a LoRA, fine-tuning, distillation, pruning, quantization,
  dataset curation, synthetic data, curriculum, tool-use, domain adaptation e
  inference optimization;
- seed e chave de reprodutibilidade obrigatórios;
- artefatos e testes obrigatórios antes do candidato;
- benchmark e RegressionDetector;
- SafetyValidator e Human Approval para alto risco;
- invariantes de identidade entre provider, modelo base, modelo candidato e métrica;
- compile SUCCESS;
- **1256 passed / 1 skipped / 0 failed** no Lumen Tests;
- **1256 passed / 1 skipped / 0 failed** no Lumen F0 Validation;
- PR #12 pronta para merge.

## Limites de segurança

F18 é uma camada de laboratório/validação. Não executa treinamento, inferência,
processos, rede, download ou deploy. Não concede Permission, altera Policy,
Sandbox, Checkpoint ou Audit, não amplia Scope e não promove automaticamente.
O candidato permanece isolado e a promoção continua delegada ao F15
PromotionGate.

## Próxima fase

**F19 — Lumen Intelligence Lab.**

F19 deverá unificar Evolution Lab + Model Adaptation Lab em um ambiente permanente
de pesquisa de inteligência, mantendo a separação entre Stable Runtime,
Experimental Workspace e Candidate.
# F16 — CONTINUOUS EVOLUTION — 🟩 CONCLUÍDA

**Data:** 2026-09-27

## Evidência final

- monitoramento pós-promoção bounded;
- estabilidade, degradação e regressão determinísticas;
- histórico de observações limitado;
- Evolution Trigger para novo ciclo;
- integração de evidências com EvolutionMemory;
- planner de oportunidade baseado em pesquisa;
- primeira CI: 9 falhas de fixture, corrigidas;
- validação final: **1236 passed / 1 skipped / 0 failed**;
- Lumen Tests run 36355972633: SUCCESS;
- Lumen F0 Validation run 36355972659: SUCCESS;
- compile SUCCESS;
- PR #10 mergeada em master; merge commit 01a2d08881a3537ab3ddf96491b0c64a0998ec0d.

## Limites de segurança

F16 é observacional/propositiva. Não executa código, processos, drivers ou deploy,
não concede Permission, não altera Policy/Sandbox/Checkpoint/Audit, não faz rollback
físico e não promove automaticamente. Um trigger de degradação apenas inicia novo
ciclo F12–F15, preservando benchmark, security review e Human Approval.

## Próxima fase

**F17 — Intelligence Stack Evolution.**

F17 deverá evoluir a pilha de inteligência da Lumen mantendo Provider ≠ Lumen,
modelos substituíveis, isolamento experimental e evidência mensurável.

# F14 — SELF-DIAGNOSTICS + RESEARCH FOR IMPROVEMENT — 🟩 CONCLUÍDA

**Data:** 2026-09-27

## Evidência
- diagnóstico determinístico de capacidades;
- pesquisa baseada em evidências fornecidas pelo chamador;
- oportunidades de melhoria vinculadas a evidências;
- ImprovementPlanner preservando baseline, risco e fontes;
- **1205 passed / 1 skipped / 0 failed**;
- compile SUCCESS;
- F0 Validation SUCCESS;
- PR #8 mergeada;
- merge commit `09ec80b500bf4b63efcc085dda2fce5cfeb8b132`.

## Limites
F14 não executa pesquisa externa por conta própria, não executa experimentos, não chama drivers, não concede permissões e não altera Security Core.

## Próxima fase
**F15 — Candidate Build + Benchmark + Promotion.**

F15 deverá transformar propostas em candidatos avaliáveis, executar benchmarks controlados e aplicar os gates de segurança e aprovação humana antes de qualquer promoção.

---

# F13 — EVOLUTION LABORATORY — 🟩 CONCLUÍDA

**Data:** 2026-09-27

## Evidência
- laboratório isolado sob `evolution-lab/`;
- workspace por evolução;
- path traversal e stable-runtime targeting bloqueados;
- experimentos e mudanças apenas registrados;
- candidatos vinculados ao workspace correto;
- lifecycle F12 reutilizado;
- **1191 passed / 1 skipped / 0 failed**;
- Lumen F0 Validation: SUCCESS;
- PR #7 mergeada;
- merge commit: `5f2f89d9e49f9839a93e79a867b227d83dbf4bbd`.

## Limites
F13 não executa código, não chama drivers, não concede permissões, não altera Policy/Sandbox/Checkpoint/Audit e não promove candidatos.

## Próxima fase
**F14 — Self-Diagnostics + Research for Improvement.**

F14 deverá conectar diagnóstico estruturado, pesquisa de evidências e geração de propostas de melhoria, preservando a separação entre conhecimento/evidência e execução.

---

# F12 — EVOLUTION FOUNDATION — 🟩 CONCLUÍDA

**Data:** 2026-09-27

## Evidência

- Capability Registry e Measurement;
- Self-Diagnostics e Improvement Planner;
- Hypothesis Manager;
- Experiment Manager com transições bounded;
- Candidate Registry;
- Benchmark Engine;
- Regression Detector;
- Safety Validator;
- Promotion Manager com Human Approval Gate;
- Rollback Manager;
- Evolution Memory;
- IDs `EVOLUTION-000001...`;
- testes dedicados;
- primeira CI detectou e permitiu corrigir 1 falha de regex;
- CI final: **1177 passed / 1 skipped / 0 failed**;
- Lumen F0 Validation: SUCCESS;
- PR #6 mergeado em master.

## Limites

F12 é fundação de contratos e governança. Ela não executa experimentos nem altera automaticamente o runtime estável. Permission, Policy, Sandbox, Checkpoint, Audit, Secrets, Security Core e regras de promoção permanecem protegidos.

## Próxima fase

**F13 — Evolution Laboratory.**

F13 deve construir o ambiente isolado de experimentação sobre esta fundação, mantendo Stable Runtime separado de Experimental Workspace e Candidate.

---

# CURRENT OFFICIAL CONTINUITY — 2026-09-27

**F10 — WORKFLOW LEARNING: 🟩 CONCLUÍDA.**
**F11 — AUTONOMOUS MULTI-STEP AGENT: 🟩 CONCLUÍDA.**
**Próxima fase oficial: F12 — EVOLUTION FOUNDATION.**

## F11 — EVIDÊNCIA FINAL

- [x] AutonomyLimits.
- [x] AutonomyGrant com aprovação humana explícita.
- [x] MultiStepTask / MultiStep.
- [x] execução sequencial.
- [x] estado por etapa.
- [x] estado global da execução.
- [x] retry/recovery bounded.
- [x] terminalidade para Permission/Scope.
- [x] orçamento máximo de passos.
- [x] orçamento máximo de recoveries.
- [x] orçamento máximo de tentativas.
- [x] bloqueio de etapas que exigem aprovação humana adicional.
- [x] integração opcional com WorkflowMatcher.
- [x] testes dedicados.
- [x] documentação F11.
- [x] CI completa: **1160 passed / 1 skipped / 0 failed**.
- [x] PR #4 mergeado no master.

## CADEIA OFICIAL

Goal
 ↓
Workflow / MultiStepTask
 ↓
AutonomousMultiStepAgent
 ↓
Autorização humana + orçamento
 ↓
StepExecutor seguro
 ↓
F7 Permission / Policy / Scope / Checkpoint / Driver / Audit
 ↓
F8 Verification / Recovery / Regression
 ↓
Próximo passo

A F11 não cria uma autoridade de execução paralela.

## CAPACIDADES ACUMULADAS

A Lumen agora consegue perceber/groundear estado, planejar ações, controlar o computador pela barreira F7, verificar resultados, recuperar falhas limitadas, detectar regressões, planejar operações do Unreal, aprender workflows e orquestrar tarefas com múltiplas etapas sob orçamento e aprovação explícita.

## LIMITAÇÕES

- autonomia não é ilimitada;
- Permission/Scope não podem ser recuperados automaticamente;
- etapas de alto risco continuam exigindo aprovação;
- matcher F10 ainda é lexical;
- registry F10 é em memória;
- não houve smoke test físico Windows/Unreal no CI Linux.

---

# CURRENT OFFICIAL CONTINUITY — 2026-09-27

**F9 — UNREAL ENGINE AGENT: 🟩 CONCLUÍDA.**
**F10 — WORKFLOW LEARNING: 🟩 IMPLEMENTAÇÃO CONCLUÍDA / VALIDAÇÃO FOCADA CONCLUÍDA.**

Evidência:
- 18 testes focados definidos;
- validação comportamental dos contratos centrais: OK;
- workflow de CI reproduzível adicionado;
- o conector desta sessão não retornou execução/status do GitHub Actions para F10; não há contagem CI nova a declarar;
- última CI comprovada: F9, 1132 passed / 1 skipped / 0 failed.
**Próxima fase oficial: F11 — AUTONOMOUS MULTI-STEP AGENT.**

## F10 — EVIDÊNCIA E ENTREGAS

- [x] WorkflowDefinition versionado.
- [x] WorkflowStep com pós-condição e risco.
- [x] fingerprint determinístico SHA-256.
- [x] WorkflowRegistry.
- [x] WorkflowMatcher determinístico.
- [x] WorkflowLearner.
- [x] WorkflowEvidence.
- [x] estatísticas e elegibilidade.
- [x] bloqueio após falha mais recente.
- [x] adaptação somente por variáveis declaradas.
- [x] Human Approval para workflows de alto risco.
- [x] testes dedicados em tests/test_workflow_learning.py.
- [x] documentação em docs/WORKFLOW_LEARNING_IMPLEMENTATION.md.
- [x] CI reproduzível em .github/workflows/tests.yml.

## REGRA DE EXECUÇÃO

Workflow aprendido é conhecimento/plano, nunca autoridade. A cadeia obrigatória permanece:

Workflow aprendido
→ proposta/planejamento
→ PermissionManager
→ Policy
→ Scope
→ Checkpoint
→ ComputerControlService
→ Driver
→ Audit
→ Verification
→ Recovery/Regression.

A F10 não cria um caminho paralelo de execução.

## O QUE A LUMEN JÁ CONSEGUE FAZER

1. Observar/representar estado do computador com fingerprint determinístico.
2. Resolver alvos usando grounding structured-first.
3. Planejar ações sem executar diretamente o driver.
4. Executar Computer Control somente pela barreira segura F7.
5. Exigir checkpoint one-shot antes da execução física.
6. Verificar pós-condições e classificar falhas.
7. Fazer recovery bounded sem ampliar permissões ou escopo.
8. Comparar regressões por evidência determinística.
9. Planejar operações específicas do Unreal: foco, abrir asset/level, salvar, salvar tudo, Play e Stop Play.
10. Registrar sequências observadas como workflows reutilizáveis.
11. Medir histórico de sucesso/falha/inconclusivo.
12. Bloquear reutilização de workflow cuja última execução falhou.
13. Encontrar workflows compatíveis com um objetivo por matching determinístico.
14. Adaptar somente parâmetros declarados, sem criar novos passos.
15. Marcar workflows de alto risco para aprovação humana adicional.

## LIMITAÇÕES ATUAIS

- Matcher ainda é lexical, sem embeddings/semântica.
- Registry F10 é em memória; persistência durável/Experience Memory integrada é futura.
- Não existe execução automática de workflow.
- Não existe ainda Agent multi-etapas autônomo completo; isso é F11.
- Não houve smoke test físico Windows/Unreal no CI Linux.

---

# LUMEN — CONTINUIDADE POR FASES

> **Arquivo oficial de continuidade da arquitetura de evolução.**
> Complementa `LUMEN_STATE.md` sem substituir o histórico técnico existente.
> O estado real deve sempre ser atualizado com evidência; nunca marcar uma fase como concluída apenas por intenção.

## REGRA PRINCIPAL

**NÃO CRIE OUTRA LUMEN. ALTERE SEMPRE A LUMEN EXISTENTE.**

A Lumen deve evoluir dentro de sua própria arquitetura, usando ambientes experimentais isolados quando houver autoaperfeiçoamento.

## LEGENDA

- 🟩 CONCLUÍDO — evidência/testes/documentação confirmam.
- 🟥 PENDENTE — ainda não concluído.
- 🟨 EM PROGRESSO — parcial, sem critério completo.

## ESTADO DESTE PLANO

O estado acima é a referência operacional atual. F0–F7 possuem evidência registrada; as demais permanecem pendentes. A base 0.6.8 existente e suas fases internas continuam registradas em `LUMEN_STATE.md`; elas não devem ser falsamente convertidas em conclusão das novas fases.

---

# FASES — ESTADO OFICIAL 2026-09-27

## F0 — BASELINE / AUDITORIA / CONTRATOS
🟩 CONCLUÍDA

## F1 — LOCAL PROVIDER / OLLAMA
🟩 CONCLUÍDA

## F2 — TOOL / AGENT PROTOCOL
🟩 CONCLUÍDA

## F3 — COMPUTER INTELLIGENCE
🟩 CONCLUÍDA

Entregues:
- [x] Perception estruturada.
- [x] State fingerprint determinístico.
- [x] Targeting com prioridade native-first.
- [x] Grounding vinculado à observação.
- [x] ActionIntent / ActionPlan.
- [x] Resolução para CCActionRequest sem execução direta.
- [x] Verification de alvo e mudança de estado.
- [x] Recovery limitado.
- [x] Testes focados + CI completa: 1065 passed / 1 skipped / 0 failed.
- [x] Documentação em docs/COMPUTER_INTELLIGENCE_IMPLEMENTATION.md.

## F4 — WINDOWS NATIVE INTELLIGENCE
🟩 CONCLUÍDA

Entregues:
- [x] Enumeração e correspondência de janelas por handle/título/processo/aplicação.
- [x] Backend Windows UI Automation com imports COM lazy.
- [x] Árvore UIA limitada por profundidade e quantidade.
- [x] Propriedades estruturadas de controles.
- [x] Conversão NativeElement → GroundedTarget.
- [x] NativeActionRequest sem execução física/bypass de segurança.
- [x] Testes focados + CI completa: 1073 passed / 1 skipped / 0 failed.
- [x] Documentação em docs/WINDOWS_NATIVE_INTELLIGENCE.md.

## F5 — VISION PROVIDER
🟩 CONCLUÍDA

Entregues:
- [x] VisionProvider independente e desacoplado de modelo específico.
- [x] JsonVisionProvider com validação fail-closed.
- [x] OllamaVisionProvider com qwen3-vl:8b configurável.
- [x] limites de imagem, resposta, tokens e payload.
- [x] VisionProviderManager para múltiplos modelos/providers.
- [x] testes focados + CI completa: 1084 passed / 1 skipped / 0 failed.
- [x] documentação em docs/VISION_PROVIDER_IMPLEMENTATION.md.

## F6 — GROUNDING ENGINE
🟩 CONCLUÍDA

Entregues:
- [x] GroundingEngine com ordem estruturada-first.
- [x] Elegibilidade validada antes da priorização de fonte.
- [x] Validação de confiança, imagem, região e identidade de janela.
- [x] Normalização determinística de labels.
- [x] Adaptação de VisionObservation.
- [x] Adaptação de NativeElement sem acoplamento ao backend Windows.
- [x] Deduplicação de candidatos.
- [x] Fallback seguro quando candidato prioritário é inválido.
- [x] TargetingEngine integrado ao novo fluxo de elegibilidade.
- [x] Testes focados + CI: 1094 passed / 1 skipped / 0 failed.
- [x] Documentação em docs/GROUNDING_ENGINE_IMPLEMENTATION.md.

## F7 — SECURE COMPUTER CONTROL
🟩 CONCLUÍDA

Entregues:
- [x] PermissionManager(COMPUTER_CONTROL) como autoridade explícita.
- [x] CC Policy fail-closed.
- [x] CCScope com ações, expiração, orçamento e região.
- [x] checkpoint one-shot CC-CP-XXXXXX antes da execução.
- [x] fingerprint vinculado ao scope e à requisição.
- [x] aprovação não reutilizável.
- [x] revalidação do scope imediatamente antes do driver.
- [x] regiões de screenshot revalidadas contra o scope.
- [x] GroundedTarget revalidado antes da ação.
- [x] auditoria metadata-only.
- [x] ações não suportadas falham de forma controlada.
- [x] testes de negação, aprovação, replay, mismatch, recusa, escopo, orçamento e falha.
- [x] CI completa: 1104 passed / 1 skipped / 0 failed.
- [x] documentação em docs/SECURE_COMPUTER_CONTROL_IMPLEMENTATION.md.

## F8 — VERIFICATION + RECOVERY + REGRESSION
🟩 CONCLUÍDA

Entregues:
- [x] pós-condições explícitas de verification;
- [x] estados VERIFIED / FAILED / INCONCLUSIVE;
- [x] classificação de falhas;
- [x] recovery bounded, com segurança terminal;
- [x] RegressionDetector determinístico;
- [x] integração com ComputerIntelligence;
- [x] testes dedicados + CI da PR;
- [x] documentação em docs/VERIFICATION_RECOVERY_REGRESSION_IMPLEMENTATION.md.

## F9 — UNREAL ENGINE AGENT
🟩 CONCLUÍDA

- foco, Open Asset, Open Level, Save, Save All, Play e Stop;
- planos convertíveis para a cadeia segura;
- objetivos ambíguos rejeitados;
- CI final: 1132 passed / 1 skipped / 0 failed.

## F10 — WORKFLOW LEARNING
🟩 CONCLUÍDA

- workflows versionados e fingerprint determinístico;
- evidências de sucesso/falha/inconclusivo;
- matcher e adaptação bounded;
- alto risco exige aprovação;
- execução continua na cadeia F7/F8.

## F11 — AUTONOMOUS MULTI-STEP AGENT
🟩 CONCLUÍDA

- tarefas multi-etapas sequenciais;
- orçamento de passos/recovery/tentativas;
- approval explícito;
- terminalidade para falhas de segurança;
- CI final: 1160 passed / 1 skipped / 0 failed.

# LUMEN EVOLUTION SYSTEM

## F12 — EVOLUTION FOUNDATION
🟩 CONCLUÍDA

Capability Registry, Measurement, Diagnostics, Improvement Planner, Hypothesis Manager,
Experiment Manager, Candidate Registry, Benchmark/Regression, Safety Validator,
Promotion Manager, Rollback Manager e Evolution Memory.

## F13 — EVOLUTION LABORATORY
🟩 CONCLUÍDA

Laboratório isolado, path safety, separação de runtime estável e registro bounded de
experimentos/mudanças/candidatos.

## F14 — SELF-DIAGNOSTICS + RESEARCH FOR IMPROVEMENT
🟩 CONCLUÍDA

Diagnóstico determinístico, pesquisa baseada em evidências fornecidas pelo chamador,
oportunidades e planos de melhoria. CI final: 1205 passed / 1 skipped / 0 failed.

## F15 — CANDIDATE BUILD + BENCHMARK + PROMOTION
🟩 CONCLUÍDA

Build evidence, benchmark, regression gate, safety review, Human Approval Gate e
promoção metadata-only. CI final: 1222 passed / 1 skipped / 0 failed.

## F16 — CONTINUOUS EVOLUTION
🟨 IMPLEMENTAÇÃO CONCLUÍDA / CI EM VALIDAÇÃO

Entregas:
- [x] Post-promotion monitoring.
- [x] Stability assessment.
- [x] Degradation/regression detection.
- [x] Bounded monitoring history.
- [x] Evolution trigger para novo ciclo.
- [x] Research-to-opportunity planner.
- [x] Integração de evidência de monitoramento com EvolutionMemory.
- [x] testes dedicados.
- [x] documentação.
- [ ] CI completa e F0 Validation.
- [ ] merge em master e atualização final da evidência.

## F17 — INTELLIGENCE STACK EVOLUTION
🟥 PENDENTE

## F18 — MODEL ADAPTATION LABORATORY
🟥 PENDENTE

## F19 — LUMEN INTELLIGENCE LAB
🟥 PENDENTE

## F20 — SELF-OPTIMIZING INTELLIGENCE
🟥 PENDENTE

## F21 — PROVIDER INDEPENDENCE
🟥 PENDENTE

## F22 — CONTINUOUS INTELLIGENCE EVOLUTION
🟥 PENDENTE

# BOUNDARY DE SEGURANÇA — NÃO NEGOCIÁVEL

O Evolution System pode evoluir **capacidades**, mas não pode unilateralmente remover ou enfraquecer:

- PermissionManager;
- Policy Engine;
- Sandbox;
- Checkpoint;
- Audit;
- Rollback;
- Promotion Rules;
- proteção de secrets;
- limites de autoridade;
- isolamento do Evolution Lab.

Mudanças nesses mecanismos exigem **Human Approval Gate**.

## NÍVEIS DE RISCO

### 🟢 BAIXO
Documentação, conhecimento, índices, workflows, testes e otimizações isoladas.

### 🟡 MÉDIO
Dependências, Providers, ferramentas e mudanças com impacto transversal.

### 🔴 ALTO
Computer Control, permissões, sandbox, Policy, Checkpoints, Audit, secrets e Security Core.

---

# MODELO DE ESTADOS DO EVOLUTION SYSTEM

`PROPOSED → RESEARCHING → HYPOTHESIS → PLANNED → EXPERIMENTAL → BUILDING → TESTING → BENCHMARKING → SECURITY_REVIEW → PROMOTION_PENDING → APPROVED/REJECTED → PROMOTED → MONITORED`

Nenhum estado pode ser pulado sem uma regra explícita e auditável.

---

# EXEMPLO DE EVOLUÇÃO

**Objetivo:** melhorar Computer Control + Visão.

1. 🟥 Baseline.
2. 🟥 Diagnóstico das falhas.
3. 🟥 Pesquisa.
4. 🟥 Hipóteses.
5. 🟥 Experimento isolado.
6. 🟥 Implementação.
7. 🟥 Testes.
8. 🟥 Benchmark.
9. 🟥 Security validation.
10. 🟥 Comparação.
11. 🟥 Rejeitar ou promover.
12. 🟥 Registrar sucesso/falha na Experience Memory.
13. 🟥 Monitorar após promoção.

**Nunca:** editar o runtime estável diretamente e depender da própria alteração para recuperação.

---

# CRITÉRIO DE CONTINUIDADE

Ao concluir qualquer item:

1. marcar 🟩;
2. registrar teste/evidência;
3. atualizar `LUMEN_STATE.md`;
4. atualizar este arquivo;
5. atualizar decisões quando aplicável;
6. atualizar handoff;
7. commit no GitHub;
8. só então avançar.

## REGRA DE PAUSA

Se um teste crítico falhar, a fase permanece 🟥 ou 🟨. Não avançar artificialmente.

## VISÃO FINAL

A Lumen deve evoluir de:

`Agent + Tools`

para:

`Agent + Research + Knowledge + Experience + Computer Intelligence + Secure Execution + Verification + Evolution System`

e finalmente para:

`Agent capaz de descobrir limitações, pesquisar soluções, experimentar melhorias, provar resultados e evoluir continuamente sem colocar sua própria continuidade em risco.`
