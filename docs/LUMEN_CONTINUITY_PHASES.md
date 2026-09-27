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

Todas as fases desta trilha são inicialmente **🟥 PENDENTES**. A base 0.6.8 existente e suas fases internas continuam registradas em `LUMEN_STATE.md`; elas não devem ser falsamente convertidas em conclusão das novas fases.

---

# FASES

## F0 — BASELINE / AUDITORIA / CONTRATOS
🟩 CONCLUÍDA

- [x] Auditoria completa da arquitetura atual — registrada em docs/LUMEN_F0_BASELINE_AUDIT.md.
- [x] Capability Registry — app/core/capabilities.py + tests/test_capabilities.py.
- [x] Contratos de Provider/Tool/Memory/Research/Vision/Evolution — docs/LUMEN_CONTRACTS.md.
- [x] Baseline de desempenho e confiabilidade — CI reproduzível; 1018 passed / 1 skipped / 0 failed.
- [x] Threat model — docs/LUMEN_THREAT_MODEL.md.
- [x] Critérios de promoção — docs/LUMEN_PROMOTION_CRITERIA.md.
- [x] pip check e compileall validados na CI.

Evidência final da F0: workflow Lumen F0 Validation, run 36348740037, commit a33af8a598cab12b21194854bbf08d2da1fd15dd.

**Próximo desbloqueio:** F1.

## F1 — LOCAL PROVIDER
🟥 PENDENTE

- [ ] Ollama Provider.
- [ ] `qwen2.5-coder:7b-instruct-q8_0`.
- [ ] Health check.
- [ ] Timeout.
- [ ] Observabilidade.
- [ ] Testes.
- [ ] ProviderManager isolado.

## F2 — RESEARCH ENGINE
🟥 PENDENTE

- [ ] Web search.
- [ ] Coleta de fontes.
- [ ] GitHub/docs/PDF.
- [ ] Extração.
- [ ] Deduplicação.
- [ ] Comparação de fontes.
- [ ] Verificação.
- [ ] Proveniência.
- [ ] Proteção contra prompt injection em conteúdo externo.

## F3 — KNOWLEDGE + EXPERIENCE MEMORY
🟥 PENDENTE

- [ ] Knowledge Engine.
- [ ] Experience Memory.
- [ ] Failure Memory.
- [ ] Success Memory.
- [ ] Strategy Memory.
- [ ] Skill Evidence.
- [ ] Índice semântico/Qdrant quando apropriado.
- [ ] Proveniência e confiança.

## F4 — TOOL / AGENT PROTOCOL
🟥 PENDENTE

- [ ] Intenção estruturada.
- [ ] Planner.
- [ ] Tool contract.
- [ ] Validation.
- [ ] Permission.
- [ ] Checkpoint.
- [ ] Audit.
- [ ] Verification.
- [ ] Nenhum acesso direto do LLM aos drivers.

## F5 — COMPUTER INTELLIGENCE
🟥 PENDENTE

- [ ] Perception.
- [ ] State understanding.
- [ ] Targeting.
- [ ] Action resolution.
- [ ] Observation.
- [ ] Verification.
- [ ] Recovery.

## F6 — WINDOWS NATIVE INTELLIGENCE
🟥 PENDENTE

- [ ] UIA.
- [ ] Accessibility/UI Tree.
- [ ] Win32.
- [ ] WinCOM quando necessário.
- [ ] Window/focus handling.
- [ ] Structured actions.

## F7 — VISION PROVIDER
🟥 PENDENTE

- [ ] VisionProvider.
- [ ] LLaVA como Provider visual inicial/candidato.
- [ ] Arquitetura para Qwen-VL/Qwen3-VL/outros.
- [ ] Screenshot understanding.
- [ ] OCR.
- [ ] Element detection.
- [ ] Structured visual output.

## F8 — GROUNDING ENGINE
🟥 PENDENTE

- [ ] Native-first resolution.
- [ ] Template matching.
- [ ] Vision grounding.
- [ ] Confidence.
- [ ] Window bounds.
- [ ] Region bounds.
- [ ] DPI/scale.
- [ ] Action validation.

## F9 — SECURE COMPUTER CONTROL
🟥 PENDENTE

- [ ] Mouse.
- [ ] Keyboard.
- [ ] Clipboard.
- [ ] Windows.
- [ ] Screenshot.
- [ ] Backend abstraction.
- [ ] PyAutoGUI/PyDirectInput/MSS somente como adaptadores.
- [ ] Permission/Policy/Checkpoint/Audit/Verification.

## F10 — VERIFICATION / RECOVERY / REGRESSION
🟥 PENDENTE

- [ ] Result verification.
- [ ] Failure classification.
- [ ] Controlled retry.
- [ ] Alternative strategy.
- [ ] Recovery.
- [ ] Regression suite.
- [ ] Action/time/cost budgets.

## F11 — UNREAL ENGINE AGENT
🟥 PENDENTE

- [ ] Unreal Python/API.
- [ ] Project/filesystem.
- [ ] C++.
- [ ] Blueprint.
- [ ] Build.
- [ ] Test.
- [ ] Computer Control somente quando necessário.
- [ ] Verification.

## F12 — WORKFLOW LEARNING
🟥 PENDENTE

- [ ] Trajectory recording.
- [ ] Successful workflow extraction.
- [ ] Failure/correction recording.
- [ ] Deterministic workflow execution.
- [ ] Verification obrigatório.

## F13 — AUTONOMOUS MULTI-STEP AGENT
🟥 PENDENTE

- [ ] Goal decomposition.
- [ ] Research.
- [ ] Plan.
- [ ] Execute.
- [ ] Observe.
- [ ] Verify.
- [ ] Correct.
- [ ] Test.
- [ ] Report.
- [ ] Remember.

# LUMEN EVOLUTION SYSTEM

## F14 — EVOLUTION FOUNDATION
🟥 PENDENTE

- [ ] Evolution Engine.
- [ ] Capability Registry.
- [ ] Capability Measurement.
- [ ] Self-Diagnostics.
- [ ] Improvement Planner.
- [ ] Hypothesis Manager.
- [ ] Experiment Manager.
- [ ] Candidate Registry.
- [ ] Benchmark Engine.
- [ ] Regression Detector.
- [ ] Safety Validator.
- [ ] Promotion Manager.
- [ ] Rollback Manager.
- [ ] Evolution Memory.

## F15 — EVOLUTION LABORATORY
🟥 PENDENTE

- [ ] Stable runtime separado.
- [ ] Experimental workspace.
- [ ] Candidate workspace.
- [ ] Experiments.
- [ ] Benchmarks.
- [ ] Reports.
- [ ] Rejected candidates.
- [ ] Approved candidates.
- [ ] Checkpoint antes de alterações relevantes.
- [ ] Rollback independente do candidato.

## F16 — SELF-DIAGNOSTICS + RESEARCH FOR IMPROVEMENT
🟥 PENDENTE

A Lumen deverá aceitar solicitações como:

> "Seu Computer Control e Visão estão ruins. Melhore."

E executar:

- [ ] Diagnóstico.
- [ ] Baseline.
- [ ] Pesquisa.
- [ ] Avaliação das fontes.
- [ ] Hipóteses.
- [ ] Plano de melhoria.
- [ ] Experimento.

## F17 — CANDIDATE / BENCHMARK / PROMOTION
🟥 PENDENTE

- [ ] Build candidato.
- [ ] Unit tests.
- [ ] Integration tests.
- [ ] Regression tests.
- [ ] Security tests.
- [ ] Capability tests.
- [ ] Benchmark.
- [ ] Comparação contra baseline.
- [ ] Promotion Gate.
- [ ] Human Approval Gate quando necessário.
- [ ] Rejeição rastreável.
- [ ] Promoção rastreável.
- [ ] Monitoramento pós-promoção.

## F18 — CONTINUOUS EVOLUTION
🟥 PENDENTE

- [ ] Observe.
- [ ] Measure.
- [ ] Diagnose.
- [ ] Research.
- [ ] Hypothesize.
- [ ] Experiment.
- [ ] Implement.
- [ ] Test.
- [ ] Benchmark.
- [ ] Verify.
- [ ] Promote/Reject.
- [ ] Learn.
- [ ] Measure again.

---

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
