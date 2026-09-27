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
🟥 PENDENTE

## F10 — WORKFLOW LEARNING
🟥 PENDENTE

## F11 — AUTONOMOUS MULTI-STEP AGENT
🟥 PENDENTE

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
