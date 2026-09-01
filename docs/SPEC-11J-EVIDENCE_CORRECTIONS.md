# Spec 11J — Evidence-Based Corrections (repair-loop com evidência real)

**Status:** **IMPLEMENTADA + TESTADA** (entregue em 2026-08-31 —
COMANDOS 073–078). Status anterior: DRAFT / EM DISCUSSÃO — 11J
PLANEJADA, NÃO IMPLEMENTADA (preservado no Histórico).

**Escopo:** melhorar a qualidade do feedback do repair-loop (Corrections,
0.6.2) usando **evidências reais já disponíveis** (`run_pytest` 11D /
verificação 11E / export 11I) — sem auto-replanning (R4 continua proibido),
sem execução escondida e mantendo a aprovação explícita do usuário.

**Fora do escopo (MVP):** nova regra de correção que mude o plano (ex.:
re-rer de `run_pytest` com `-k` — TBD §8); contexto cross-task no engine;
qualquer mudança de permission/checkpoint/tetos.

> Baseline da suíte na data do DRAFT: **989 passed / 5 skipped / 0 failed**
> (994 coletados) — baseline pós-11I (commit `ab73bea`).

---

## 1. Status

- **IMPLEMENTADA + TESTADA** (2026-08-31): COMANDO 076 (código + teste —
  escopo MVP §5/§6), COMANDO 077 (regressão completa 990/5/0) e COMANDO
  078 (doc sync). Status anterior: DRAFT / EM DISCUSSÃO (ver Histórico).
- Pré-requisitos entregues: 11D (`run_pytest`), 11E (verificação real),
  11F (auto-append), 11G (corrections + evidência), 11H (toggles
  persistentes + UI), 11I (report export) — todos commitados.
- Decisões de fluxo/UX ficam abertas em §8 até a aprovação do DRAFT.

## 2. Evidência do estado atual (mapeamento — COMANDO 073 1/3)

- **API atual:** `CorrectionStrategy.propose_correction(task: PlannedTask,
  run: TaskRun) -> CorrectionProposal | None` — a strategy recebe **apenas**
  a task falhada + seu `TaskRun` (`status`, `error`, `result` (str),
  `attempts`, `verified`, `attempt_log`).
- **`CorrectionProposal`** (frozen): `suggestion, retry_recommended,
  detail, corrected_task (None = somente conselho — nada é aplicado),
  requires_approval` (default **True**).
- **Strategy padrão é conservadora** (`ToolCorrectionStrategy`): única regra
  real — `create_file` + "já existe" ⇒ propõe `write_file` (com aprovação);
  erro de segurança/política ⇒ **Nunca propõe**; qualquer outro erro ⇒ None
  (a estratégia não inventa).
- **Validator já garante** (`build_proposal_validator`): ferramenta
  registrada + permissão concedida + sandbox (resolve + check_operation) +
  `TerminalPolicy` — proposta inválida vira `INVALID` e **nunca** é aplicada.
- **Evidência disponível no próprio `TaskRun`:** `run.result` é o **JSON do
  `ToolResult` da `run_pytest`** (`ok` / `data{exit_code, summary_line,
  truncated, duration_s}` / `error`) — o mesmo input que o
  `PytestResultVerifier` (11E) parseia; falha de verificação chega como
  status **`REJECTED`** (`failure_kind="verification"`, 11E/11G).
- **Engine (`CorrectionEngine`):** `_handle_failure` escolhe o primeiro run
  `FAILED`/`REJECTED`; tetos rígidos (`max_cycles`/`max_total_attempts`);
  `requires_approval` ⇒ `PendingCorrection` + pausa (card 🛡);
  `corrected_task=None` ⇒ `NO_PROPOSAL`/`FAILED` — **conselho registrado no
  ciclo (JSONL), sem pausa e sem aplicação**.
- **Fontes correlatas:** auditoria JSONL já correlaciona por `plan_id`
  (`audit_records(limit)`); o export 11I
  (`data_dir/reports/<safe_plan_id>.json`) é **pós-facto** (gravado no
  `_final`, depois do loop) — contexto para o relatório, não para a
  estratégia in-loop.

## 3. Objetivo (MVP)

- Melhorar a qualidade do feedback de correção com **evidência real**:
  - se a falha for `run_pytest`/verificação (`FAILED`/`REJECTED`):
    **motivo claro** (`exit_code`/`summary_line`/`timed_out`) + **sugestão
    objetiva do próximo passo** (o que corrigir/rever) — **sem execução
    automática**;
  - evidência em `suggestion` (registrada no ciclo/JSONL, truncada em 160
    chars pelo `_audit_cycle`) + `detail` (versão completa para o
    relatório/card).
- **Semântica do engine a preservar (nota importante):** proposta
  **somente-conselho** (`corrected_task=None`) **não gera
  `PendingCorrection`/pausa** — o ciclo é registrado (JSONL + relatório
  11I) e o loop encerra (`NO_PROPOSAL`/`FAILED`). Expor a evidência num
  card **com pausa** exige `corrected_task` — ver TBD 1/3 (§8).

## 4. Princípios de segurança (normativo)

1. **Sem bypass:** nunca propor correção para erro de
   segurança/permissão/policy (manter `_is_security_error` ⇒ `None`);
   proposta com `corrected_task` segue o `build_proposal_validator`
   inalterado (registry/permissão/sandbox/policy).
2. **Sem auto-replanning:** R4 continua proibido — 11J **não replaneja**:
   no MVP não há `corrected_task` (nada é aplicado); se houver
   `corrected_task` no futuro, o sucessor continua sendo **apenas** a
   substituição da task falhada (regra 0.6.2), nunca novo plano.
3. **Sem execução escondida:** a strategy **somente lê** dados já existentes
   (`run.result`, `run.error`); **sem subprocess/shell/tool**, sem nova
   escrita de arquivo no caminho da proposta (a leitura opcional de auditoria
   é TBD §8).
4. **Approval explícita sempre:** qualquer proposta que venha a ter
   `corrected_task` mantém `requires_approval=True` (default do engine);
   card `PendingCorrection` e tetos (`max_cycles`/`max_total_attempts`)
   inalterados.
5. **Bit-a-bit no default:** sem evidência aplicável (outra tool; JSON
   ausente/inválido; pytest verde), o comportamento é **idêntico** ao
   `ToolCorrectionStrategy` atual (delegação).

## 5. Proposta recomendada (Opção A — mínimo risco)

- **Nova classe `EvidenceCorrectionStrategy` (wrapper)** em
  `app/tools/correction.py`, com a **mesma assinatura**
  `propose_correction(task, run)` — **sem tocar** engine, ABC, validator,
  checkpoints nem tetos:
  - **MVP:**
    - `task.tool == "run_pytest"`: `json.loads(run.result)` (JSON
      inválido/ausente ⇒ conselho genérico, sem crash):
      - falha (`ok=False` / `exit_code != 0` / `timed_out`):
        `suggestion` = motivo claro + próximo passo objetivo
        (ex.: "pytest falhou (exit_code=1): 2 falharam — revise o código/
        testes e rode a suíte novamente"); `detail` = evidência completa
        (`exit_code`, `summary_line`, `timed_out`, `truncated`,
        `duration_s`); **`corrected_task=None`** (somente conselho);
        `requires_approval=True`;
      - verde ⇒ `None` (nenhuma "correção" para sucesso);
    - **demais tools: delega** para o `ToolCorrectionStrategy` atual
      (`create_file`→`write_file`, segurança ⇒ None, resto ⇒ None) —
      regras conservadoras intactas.
- **Alternativa (Opção B — REJEITADA neste DRAFT):** contexto no ABC
  (`propose_correction(task, run, context)`) com report/plano/auditoria —
  blast radius maior (ABC + `Noop` + todos os testes); reabrir só se houver
  demanda de contexto cross-task.

## 6. Integração

- `ToolsController.enable_corrections(strategy=None)`: o **default** vira
  `EvidenceCorrectionStrategy()` (que embute o `ToolCorrectionStrategy`
  atual como delegação) — o wiring da branch corrections em `run_plan`
  continua usando `self._corrections["strategy"]` (engine montado como
  hoje).
- **Strategy custom nunca é sobrescrita:** se o integrador passar
  `strategy=…` explicitamente, ela é usada (comportamento atual da
  assinatura preservado).
- Nada muda em: `enable_verification`, 11F/11G (`verifier_factory`,
  `plan_transform`), toggles 11H, export 11I.

## 7. Plano de testes (execução registrada — COMANDOS 076/077)

- **Unit (parse + delegação):** `run.result` JSON válido verde ⇒ `None`;
  JSON vermelho (exit≠0) ⇒ `suggestion`/`detail` com `summary_line`/
  `exit_code` e `corrected_task=None`; `timed_out` ⇒ motivo "timed out";
  JSON inválido/ausente ⇒ conselho genérico (sem crash); outras tools ⇒
  delegação bit-a-bit (`create_file`+já-existe continua propondo
  `write_file`; erro de segurança ⇒ `None`).
- **Integração:** corrections ON + plano com `run_pytest` vermelho
  (`REJECTED`) ⇒ **ciclo de correção registrado** (JSONL/
  `correction_history()`) com a evidência (`summary_line`/`exit_code`);
  plano `FAILED` **sem aplicação e sem sucessor** (MVP: somente conselho);
  nenhuma permissão concedida; tetos respeitados.
  *(Se o TBD 3 resolver expor card com pausa, o teste passa a asserir a
  `PendingCorrection` com `detail` contendo `summary_line`.)*
- **Regressão completa:** suíte inteira sem regressão; baseline 11I
  (989/5/0) como piso.

**Resultado (2026-08-31):** entregue o teste integrado do §7 (pytest
vermelho ⇒ ciclo com evidência, **sem pausa**, plano `FAILED`) e a
regressão completa (990/5/0 — COMANDO 077). Os unitários dedicados de
parse/delegação não foram adicionados: a delegação bit-a-bit continua
coberta pelos testes 0.6.2 existentes (`test_strategy_*`) e o caminho de
parse (JSON válido) é exercitado pelo teste integrado; o caminho JSON
inválido segue sem teste dedicado (evolução futura). Ver §9.

## 8. Questões abertas (TBD)

- **RESOLVIDO (2026-08-31, COMANDO 076):** advice-only para
  `run_pytest` entregue conforme §3/§5 — `corrected_task=None`,
  evidência registrada no ciclo/JSONL/relatório 11I, **sem execução
  escondida** (somente parse do `run.result`) e sem pausa; aprovação
  continua obrigatória para correções com tarefa (ver §9).

1. **Re-rer com `-k` (sempre com aprovação):** propor
   `corrected_task` = nova task `run_pytest` (possivelmente
   `-k <teste_falhado>`) — gera `PendingCorrection` real (pausa + card +
   aprovação) e novo ciclo de execução; muda o fluxo (consome
   `max_cycles`/tentativas) — decisão explícita necessária.
2. **Limites de tamanho:** `summary_line` pode ser longa — definir
   truncamento para `detail` (o JSONL já trunca `suggestion` em 160 chars)
   e para o card (se o TBD 3/1 for adotado).
3. **Exposição da evidência — card com pausa:** o MVP foi RESOLVIDO
   (somente ciclo/JSONL/relatório — §9); permanece em aberto decidir se
   a evidência será exposta num card **com pausa** (exige
   `corrected_task` — item 1).
4. **Incluir `audit_tail` (read-only) no contexto da strategy:** leitura do
   JSONL via closure do controller **sem acoplar o engine** — avaliar
   benefício vs. complexidade (ex.: qual tool falhou antes do pytest).

## 9. Evidências (implementação e testes)

- **Implementação (COMANDO 076):**
  - `app/tools/correction.py` — nova `EvidenceCorrectionStrategy`
    (wrapper sobre `ToolCorrectionStrategy`): falha de `run_pytest`
    (`REJECTED`/`FAILED`) ⇒ conselho com evidência
    (`exit_code`/`summary_line`/`timed_out`/`truncated`) extraída do
    JSON do `ToolResult` em `run.result` (somente parse); JSON
    inválido ⇒ conselho genérico; demais casos (incluindo erros de
    segurança) ⇒ delegação à base.
  - `app/tools/control.py` — default de `enable_corrections` passa a ser
    `EvidenceCorrectionStrategy(ToolCorrectionStrategy())`; strategy
    custom fornecida **nunca é sobrescrita**.
- **Testes (COMANDO 076):** `tests/test_tools_correction.py` — +1 teste
  integrado `test_11j_pytest_failure_records_evidence_advice_in_cycle`:
  terminal + verificação + corrections (default) com suíte vermelha ⇒
  plano `FAILED`, **sem pending/pausa** (advice-only) e
  `correction_history()` com 1 ciclo: `suggestion` "pytest falhou: …"
  (evidência), `decision_note` "somente conselho", `replacement_tool=None`.
- **Baseline (COMANDO 077):** **995 coletados — 990 passed / 5 skipped /
  0 failed** (regressão completa; piso 989/5/0 do DRAFT mantido).

---

## Histórico

- **2026-08-31 — DRAFT inicial (11J).** Mapeamento do repair-loop
  (COMANDO 073 1/3): API `propose_correction(task, run)`; strategy
  conservadora; validator já garante registry/permissão/sandbox/policy;
  evidência no próprio `TaskRun` (JSON `run_pytest`) + status `REJECTED`
  (11E/11G); 11I é pós-facto. Decisões do DRAFT: `EvidenceCorrectionStrategy`
  (wrapper, mesma assinatura; `run_pytest` ⇒ enriquece `suggestion`/`detail`
  com `exit_code`/`summary_line`, `corrected_task=None`; delega demais
  cases); default em `enable_corrections` (custom nunca sobrescrita); **sem
  auto-replanning, sem execução, approval sempre**. Baseline de referência:
  989/5/0 (pós-11I).
- **2026-08-31 — IMPLEMENTADA + TESTADA (status atual).** COMANDO 076:
  `EvidenceCorrectionStrategy` em `app/tools/correction.py` + default em
  `enable_corrections` (`app/tools/control.py`) + 1 teste integrado em
  `tests/test_tools_correction.py` (advice com evidência, sem pausa).
  COMANDO 077: regressão completa **990 passed / 5 skipped / 0 failed**
  (995 coletados). COMANDO 078: doc sync (LUMEN_STATE/README/ROADMAP +
  esta spec). Status anterior: **DRAFT / EM DISCUSSÃO — 11J PLANEJADA,
  NÃO IMPLEMENTADA.**
