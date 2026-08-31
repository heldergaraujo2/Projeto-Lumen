# SPEC — Fase 11G: evidência real em modo Corrections (sem bypass)

> **Status: IMPLEMENTADA + TESTADA (entregue em 2026-08-31).** A
> Fase 11G foi autorizada em etapas (mapeamento read-only, spec,
> etapa 0, etapa 1 e testes focados) e o MVP descrito em §3–§5 está
> entregue e coberto por testes — ver "Evidências (implementação e
> testes)" abaixo. O status original (DRAFT / em discussão) fica
> preservado em "Histórico do documento".

- **Base da discussão:** `0.6.8` + fases internas 9A–11F concluídas
  (11D: tool `run_pytest`; 11E: verificação real opt-in; 11F:
  auto-anexo após WRITE; ver `docs/SPEC-11D-BUILD_TEST.md`,
  `docs/SPEC-11E-REAL_VERIFICATION.md` e
  `docs/SPEC-11F-AUTO_PYTEST_AFTER_WRITE.md`).
- **Suíte vigente após a entrega:** 982 passed / 5 skipped /
  0 failed (987 coletados); baseline na data do draft: 980 passed / 5
  skipped / 0 failed (985 coletados, pós-11F) — preservada como
  histórico.
- **Evidência de base:** mapeamento read-only (COMANDO 045, parte
  1/3, 2026-08-31) — os arquivos/linhas citados em §2 vêm dessa
  auditoria.
- **Leituras complementares:** `docs/ARCHITECTURE.md`
  (executor/correction), `app/executor/correction.py`,
  `app/tools/control.py`, `app/tools/run_pytest.py`.

## Evidências (implementação e testes) — entregue em 2026-08-31

**Implementação:**

- `app/tools/control.py` — **etapa 0**: o branch de corrections de
  `ToolsController.run_plan` passa
  `verifier_factory=lambda: self._verifier` ao `CorrectionEngine`
  (com 11E desligada, `None` = default preservado); **etapa 1**:
  quando terminal + `verification_enabled`, passa um
  `plan_transform` que reutiliza os helpers 11F
  (`_needs_auto_pytest`/`_attach_run_pytest`) e o guardrail 12/12
  (`ValueError` claro se não puder anexar).
- `app/executor/correction.py` — novo parâmetro opcional
  `plan_transform: Callable[[Plan], Plan] | None` (default `None`
  ⇒ comportamento atual bit-a-bit); aplicada a **cada sucessor #C**
  no `_apply` (antes do `_build_executor`); exceção do transform ⇒
  falha controlada e terminal do engine (`EXHAUSTED` com motivo
  claro; o sucessor nunca executa); o plano raiz não é transformado.

**Testes:**

- `tests/test_tools_correction.py` — 2 testes 11G: (1) **etapa 0** —
  corrections ON + verificação ON + pytest vermelho ⇒ task
  `REJECTED` + `verified=False` + plano `FAILED` (sem o wiring seria
  `DONE`); (2) **etapa 1** — root com `run_pytest` não último (11F
  não anexa no root); o sucessor `#C1` (com WRITE e sem `run_pytest`
  herdado) recebe a task anexada final (`tool="run_pytest"`,
  `{"path": "tests"}`, dependente da task corrigida), executada por
  último e `verified=True`, com o ciclo em `SUCCEEDED`.

**Baseline:** 987 coletados — 982 passed / 5 skipped / 0 failed
(anterior, pós-11F: 980/5/0 (985) — preservada).

## 2. Evidência do problema (estado atual)

- **Bypass do verifier 11E em modo corrections:** o branch de
  corrections em `ToolsController.run_plan` (`app/tools/control.py`
  L819–837) constrói o `CorrectionEngine` (L822–835) **sem
  `verifier_factory`** — o engine usa o default `lambda: None`
  (`app/executor/correction.py` L271) e `_build_executor` (L291)
  monta cada `PlanExecutor` com `verifier=None`. O ramo **direto**
  sim passa o verifier (L841 `verifier=self._verifier`).
  Consequência concreta: a tool `run_pytest` retorna
  `ToolResult(ok=True, exit_code=1)` quando o pytest é vermelho
  (`app/tools/run_pytest.py` — "a evidência vai na data"); **sem
  verifier a task fica `DONE` em silêncio** — o opt-in 11E
  (`enable_verification("pytest_result")`) é efetivamente ignorado
  em modo corrections, mesmo habilitado.
- **Perda de evidência nos sucessores #C:** o auto-anexo 11F roda
  **antes** do branch (L806–816) ⇒ o plano original que entra no
  engine já contém a task `run_pytest` (quando terminal + 11E +
  WRITE). Porém `_build_successor` (`correction.py` L490) monta o
  sucessor `<root>#C<n>` apenas com a tarefa corrigida + **restantes**
  — se a falha ocorre **na última task** (ex.: a própria
  `run_pytest` rejeitada), o sucessor **perde a evidência** e não
  há mecanismo que re-anexe.
- **Fluxo de execução das correções (contexto):**
  `controller.approve()/refuse()` delegam a
  `engine.approve_correction()/refuse_correction()/run()`
  (`control.py` L652+; `correction.py` L529–557) — **nunca** passam
  por `run_plan` de novo; todo sucessor é executado internamente via
  `self._executor = self._build_executor(successor)` (`_apply`, L470
  → L485). O controller não tem ponto de interposição entre
  "correção aplicada" e "execução do #C".

## 3. Objetivo (MVP)

- **11E aplica em modo corrections:** todo `PlanExecutor` montado
  pelo `CorrectionEngine` (plano original e sucessores #C) recebe o
  mesmo verifier do ramo direto quando `enable_verification(...)`
  está ativo (com `self._verifier is None`, comportamento atual é
  preservado).
- **Evidência persiste nos sucessores #C:** ao criar cada sucessor,
  aplica-se a **mesma regra do 11F** (terminal habilitado +
  `verification_enabled` + plano contém WRITE + plano não contém
  `run_pytest` + teto de tasks respeitado): anexa 1 task final
  `run_pytest` quando aplicável; nunca duplica.
- **Semântica explícita:** 11G **não introduz bypass nenhum** — só
  garante verificação/evidência no caminho de corrections. Não
  implementa reparo da task WRITE (repair-loop é trilha 11A —
  continua NÃO AUTORIZADO); um pytest vermelho em modo corrections
  gera ciclo de correção **sobre a task `run_pytest`** (estratégia
  pode propor nova tarefa ou `NO_PROPOSAL` ⇒ falha definitiva).

**Não-objetivos do MVP (fora de escopo):** repair-loop/reparo da
task que escreveu; auto-replanning (R4); alterar a allowlist de
`run_command`; criar nova permissão; mudanças de UI (UX fica em §7);
telemetria de "plano transformado" (fica em §7).

## 4. Princípios de segurança (normativo para a implementação)

1. **Não executar pytest "escondido"** — a evidência nos #C segue
   SEMPRE como task visível `run_pytest`, sujeita a permissão
   `TERMINAL` + checkpoint obrigatório (mesma semântica 11D/11F).
2. **Não liberar `python`/`pytest` no `run_command`** — a allowlist
   do terminal permanece inalterada.
3. **Não exceder `max_tasks` (12) silenciosamente** — o guardrail do
   11F vale para os sucessores transformados; em modo
   corrections+11F ativo o plano original só entra com ≤ 11 tasks
   (12 ⇒ rejeitado pré-execução) e sucessores são truncados (≤
   tamanho do atual), então o anexo no #C não excede 12 — a regra
   defensiva continua aplicada e testada.
4. **Default intacto** — com corrections OFF, comportamento atual é
   bit-a-bit idêntico; com corrections ON e verificação 11E OFF
   (default), o engine segue sem verifier e sem transformação de
   planos (o hook existe, mas o controller não o ativa sem a
   verificação habilitada).
5. **Engine agnóstico a tools** — o `CorrectionEngine` recebe um
   hook genérico (`plan_transform`); **não** passa a conhecer
   `run_pytest`, 11F ou permissões. A política vive no controller.

## 5. Proposta (em 2 etapas, impacto mínimo)

**Etapa 0 (obrigatória) — ligar o verifier no branch de corrections:**

- `app/tools/control.py`, construção do `CorrectionEngine` em
  `run_plan` (L822): adicionar
  `verifier_factory=lambda: self._verifier` — API existente e
  documentada do engine (`correction.py` L266–271); com
  `self._verifier is None` o factory devolve `None` (comportamento
  atual preservado). ~1 linha no controller.

**Etapa 1 — hook genérico no engine para transformar sucessores:**

- `app/executor/correction.py`: novo parâmetro opcional
  `plan_transform: Callable[[Plan], Plan] | None` (default `None`
  ⇒ comportamento idêntico ao atual) em `CorrectionEngine.__init__`.
- Ponto único de aplicação: `_apply` (L470), após
  `_build_successor` (L490) e **antes** de
  `self._executor = self._build_executor(successor)` (L485) — todo
  #C nasce ali; o hook recebe e devolve o `Plan` (puro, sem efeito
  colateral).
- `app/tools/control.py`: o controller fornece a função de
  transformação apenas quando as condições 11F valem (terminal
  habilitado + `verification_enabled`); a função reutiliza os
  helpers puros já existentes do 11F
  (`_needs_auto_pytest` / `_attach_run_pytest`) e o guardrail
  12/12 (`_auto_pytest_limit_report` — em modo corrections a
  violação do teto deve **falhar antes de executar o sucessor**,
  com plano `FAILED`/tudo `SKIPPED`, coerente com o 11F; o
  mecanismo exato — exceção controlada × relatório — é detalhe de
  implementação, mas o comportamento observável é invariante:
  **nada executa** + motivo claro).
- **Por que não interpor no controller:** `approve_correction`
  aplica e retoma internamente (`_apply` → `run()`); o controller
  não vê o sucessor antes da execução. O hook genérico no engine é
  o ponto único e mínimo (mesma camada de `verifier_factory`).
- **Impacto mínimo:** `control.py` ~+2 linhas; `correction.py`
  ~+8 linhas (parâmetro + aplicação); engine continua agnóstico a
  tools; caminho sem hook (default) é idêntico ao atual e coberto
  pela regressão existente.

## 6. Plano de testes (quando implementada)

**Integração — modo corrections + `enable_verification("pytest_result")`:**

- pytest **vermelho** na task `run_pytest` ⇒ task `REJECTED`
  (não `DONE`) ⇒ ciclo de correção disparado sobre ela (etapa 0).
- Falha em task final `run_pytest` (rejeitada) ⇒ sucessor `#C`
  contém novamente a task `run_pytest` ao final, quando as regras
  11F valem para o sucessor (etapa 1).
- Sucessor `#C` que **herda** a task anexada (falha em task
  não-final) ⇒ **sem duplicata** (idempotência do 11F).
- Sucessor sem WRITE ⇒ sem anexo.

**Regressão/defaults:**

- corrections OFF ⇒ comportamento idêntico (suíte atual inalterada).
- corrections ON + verificação OFF ⇒ sem verifier e sem
  transformação (default preservado).
- Hook `plan_transform=None` ⇒ `_apply` idêntico ao atual (coberto
  pelos testes 0.6.2 existentes).

**Regressão completa:** suíte vigente 980/5/0 (985) + novos testes.

## 7. Questões abertas (TBD) — decisões (2026-08-31)

**RESOLVIDO / IMPLEMENTADO (entregue):**

- **Etapa 0 — verifier 11E em modo corrections** — implementado: o
  branch passa `verifier_factory` ao engine; pytest vermelho ⇒
  `REJECTED` (provado em teste).
- **Etapa 1 — `plan_transform` para sucessores** — implementado no
  `CorrectionEngine` (genérico, opcional, default `None`) + wiring
  no controller (regra 11F + guardrail 12/12; falha controlada sem
  execução quando não puder anexar).
- **Semântica quando o que falha é o próprio `run_pytest`** —
  decisão de MVP implementada: a `ToolCorrectionStrategy` não
  propõe correção para ela (sem proposta ⇒ `NO_PROPOSAL` ⇒ falha
  definitiva) — provado no teste da etapa 0; corrigir a *evidência*
  (novo `path`/`k`/`timeout_s`) segue como evolução futura.
- **Interação com limites de cycles/attempts** — decisão de MVP
  implementada: limites do engine inalterados
  (`max_cycles`/`max_total_attempts`); o ciclo consome as tentativas
  naturalmente (comportamento do engine, sem mudança).

**Ainda aberto (evoluções futuras — NÃO AUTORIZADAS):**

- **UX/telemetria/auditoria de "plano transformado":** o listener de
  ciclos (`self._audit_cycle`) registra `plan_id` do #C; decidir se
  o anexo no #C merece evento/label próprio (ex.: "run_pytest
  anexado ao #C1" na auditoria/UI).
- **9B:** o bundle persiste `self._plan` (plano original anexado) +
  relatório do último executor (ids do #C) — avaliar se o histórico
  de correções atual já é suficiente para rastreabilidade (fora do
  escopo do MVP).

## Histórico do documento

- **2026-08-31 — sincronizado com a implementação entregue:** status
  DRAFT / em discussão → IMPLEMENTADA + TESTADA; adicionada seção
  "Evidências (implementação e testes)"; §7 reestruturado
  (RESOLVIDO / IMPLEMENTADO × ainda aberto); suíte atualizada para
  982/5/0 (987 coletados).
- **2026-08-31 — DRAFT criado** (COMANDO 045, parte 2/3), com base no
  mapeamento read-only da parte 1/3 (branch de corrections sem
  `verifier_factory`; sucessores #C sem re-anexo 11F; fluxo
  `approve_correction` interno ao engine). 11G **planejada, não
  implementada**.
