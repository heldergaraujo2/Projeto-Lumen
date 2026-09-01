# Spec 11I — Report Export de Evidências (pós-execução, opt-in)

**Status:** **IMPLEMENTADA + TESTADA (entregue em 2026-08-31).**
(O status original DRAFT é preservado no Histórico do documento, abaixo.)

**Escopo:** definir como **exportar** um relatório estruturado de evidências
pós-execução (plan + `ExecutionReport` + correções + auditoria correlacionada)
em arquivo JSON, **opt-in**, sem mudar a coleira (permissões/execução) e sem
vazar secrets.

**Fora do escopo (MVP):** export manual via UI (TBD, §7); formato Markdown
ou outros (TBD, §7); rotacionamento/limpeza de relatórios antigos; acoplar ao
bundle 9B (`ExecutionBundleStore`).

> Baseline da suíte na data do DRAFT: **987 passed / 5 skipped / 0 failed**
> (992 coletados) — baseline pós-11H (commit `7b674b1`).

---

## 1. Status

- **IMPLEMENTADA + TESTADA (entregue em 2026-08-31)** — MVP implementado
  como decidido neste DRAFT: módulo puro `app/tools/report_export.py` +
  hook best-effort no `ToolsController._final` + flag
  `export_execution_reports` (Settings/env) + wiring no `main.py`
  (ver "Evidências (implementação e testes)" abaixo).
- Pré-requisitos entregues: 11D (`run_pytest`), 11E (verificação real),
  11F (auto-append), 11G (corrections + evidência), 11H (toggles
  persistentes + UI) — todos commitados.
- Pontos abertos restantes (evoluções futuras) em §7; o status DRAFT
  original fica preservado no Histórico.

## 2. Evidência do estado atual (mapeamento — COMANDO 064 1/3)

- **`app/executor/executor.py :: ExecutionReport`** — frozen dataclass com
  `plan_id, objective, status, tasks (TaskRun), events (ExecutionEvent),
  error, started_at, finished_at, checkpoints, pending_checkpoint` e
  **`to_dict()` já existe** (serializa tudo, incluindo `pending_checkpoint`);
  `TaskRun` traz `result, error, attempts, verified, attempt_log` —
  **todo dado do relatório já existe; 11I é "montar + exportar", não
  "coletar novo dado"**.
- **`app/tools/control.py :: ToolsController._final(report)`** — **único
  funil terminal**: 8 call sites (run_plan ×2, approve ×3, refuse ×3); hoje
  só faz a persistência 9B (best-effort) em estado COMPLETED/FAILED.
- **`app/tools/audit_log.py`** — `JsonlAuditSink` (JSONL em
  `data/audit/audit.jsonl`) + **`read_audit_tail(path, limit)`** (tolerante);
  registros de tool do plano levam `plan_id`/`task_id` ⇒ **filtro por
  `plan_id` já é viável** (controller expõe `audit_records(limit)`).
- **9B (`app/memory/execution_store.py :: ExecutionBundleStore`)** — bundles
  em `data/executions/<plan_id>.json` são **opt-in via
  `Settings.persist_execution_state` (default OFF)**; **não devem ser
  acoplados ao 11I** (eixos de opt-in distintos; formato versionado próprio,
  `BUNDLE_VERSION`).
- **Sanitização existente:** `sanitize_any`/`sanitize_result_string`
  (execution_store, limite 16 KiB) — reutilizável.

## 3. Objetivo (MVP)

- **Opt-in** para exportar o relatório em **JSON** em
  `data_dir/reports/<plan_id>.json` ao final de cada execução em estado
  terminal (COMPLETED/FAILED — pausado/RUNNING não exporta).
- **Conteúdo mínimo:**
  - `meta` — `version` (schema do relatório, ex.: 1), `lumen_version`,
    `exported_at` (UTC);
  - `plan` — `Plan.to_dict()` (original imutável);
  - `execution_report` — `ExecutionReport.to_dict()`;
  - `correction_history` — `controller.correction_history()` (se houver;
    `None`/ausente se não houve correção);
  - `audit_tail` — registros do JSONL **filtrados por `plan_id`** (limite
    configurável, ex.: 200; registros admin sem `plan_id` não entram).
- **Sem acréscimo de coleta:** o export apenas lê estruturas já existentes
  (`report`, `plan`, `correction_history()`, auditoria) — nenhuma nova
  chamada a tools/providers/terminal.

## 4. Segurança (normativo)

1. **Export não concede permissões.** Nenhum level do
   `PermissionManager` é alterado; o export não depende de nenhuma
   permissão (é observabilidade de algo que o integrador já autorizou
   executar).
2. **Export não executa terminal** (nem nada): o caminho do export tem
   **zero subprocess/shell/tool** — apenas leitura de memória/arquivos de
   observabilidade e escrita de um arquivo JSON.
3. **Fail-closed por default.** Desabilitado por default (bit-a-bit atual:
   nenhum arquivo nasce); quando ON, **falha de escrita não quebra a
   execução** — erro é registrado e o `ExecutionReport` segue inalterado
   (mesma semântica best-effort da persistência 9B no `_final`).
4. **Sanitização obrigatória.** Reutilizar `sanitize_any`/
   `sanitize_result_string` (limite de strings do execution_store);
   **nenhum secret/stdout cru** no relatório (auditoria já não grava
   stdout; `result` é truncado; segredos nunca entram por construção —
   mesmo padrão dos bundles 9B).
5. **Sem efeito colateral no load:** com a flag OFF, nenhum diretório
   `reports/` é criado e nada é lido além do que já é lido hoje.

## 5. Integração proposta

- **Novo módulo `app/tools/report.py`** (nome sujeito a ajuste fino):
  - `build_execution_report(*, report, plan, correction=None,
    audit_records=(), lumen_version="") -> dict` — monta o payload do §3
    (puro; sem E/S);
  - `export_execution_report(*, report, plan, correction=None,
    audit_records=(), reports_dir, lumen_version="") -> Path` — sanitiza
    (reutilizando `sanitize_any`/`sanitize_result_string` do
    `app.memory.execution_store`), grava `<reports_dir>/<safe_plan_id>.json`
    (escrita atômica tmp+`os.replace`; diretório só nasce na 1ª escrita);
  - `ReportExportError(RuntimeError)` para falha de escrita.
- **Hook best-effort em `ToolsController._final(report)`** (mesmo funil do
  9B, após o bundle): se a flag estiver ON e `status ∈ {COMPLETED,
  FAILED}` → `export_execution_report(...)` dentro de try/except (log +
  segue). O `audit_tail` é obtido com `read_audit_tail(self._audit_file,
  <limite>)` filtrado por `plan_id`.
- **Nova flag opt-in (TBD na spec — sugestão via Settings/env):**
  - `export_execution_reports: bool` (**default OFF**) — espelha o padrão
    9B (`persist_execution_state` no `Settings` + env `LUMEN_*`);
  - `reports_dir: Path` (default `data_dir/"reports"`).
  - Wiring no `main.py` (composition root) + parâmetros opcionais no
    construtor do `ToolsController` (default OFF ⇒ testes atuais
    inalterados).
- **Alternativa descartada neste DRAFT:** acoplar ao
  `ExecutionBundleStore.save_bundle` (9B) — manteria o export preso ao
  opt-in do `.env` 9B e mudaria o formato versionado dos bundles (bump de
  `BUNDLE_VERSION` por algo independente).

## 6. Plano de testes (quando implementada)

- **Unit:** `build_execution_report` monta o payload exato (meta/plan/
  report/correction/audit filtrado); sanitização aplica limites de string;
  `export_execution_report` grava JSON válido e atômico; `audit_records`
  sem `plan_id` são excluídos do `audit_tail`.
- **Integração (opt-in ON):** executar um plano simples pelo
  `ToolsController` ⇒ `data/reports/<plan_id>.json` gerado com os 5 blocos
  do §3 e `plan_id` correto (e COMPLETED e FAILED — o export independe do
  desfecho).
- **Integração (opt-in OFF — default):** executar plano ⇒ **nenhum**
  arquivo/diretório `reports/` nasce; suíte bit-a-bit.
- **Falha de escrita:** diretório não gravável ⇒ `ReportExportError`
  registrada/log, `ExecutionReport` inalterado, fluxo de aprovação/recusa
  segue funcionando (best-effort).
- **Regressão completa:** suíte inteira sem regressão; baseline 11H
  (987/5/0) como piso.

## 7. Decisões (2026-08-31) e pontos restantes (TBD)

**Resolvidos na implementação (2026-08-31):**

- **Nome da flag/env (item 5 do DRAFT):** como sugerido —
  `LUMEN_EXPORT_EXECUTION_REPORTS` (aceita `1/true/yes/sim/on`; default
  OFF).
- **Naming do arquivo (parte do item 3 do DRAFT):**
  `<safe_plan_id>.json` com sanitização (`[^A-Za-z0-9._#-]` → `_`;
  `#` dos sucessores preservado).
- **Aplicação do limite do `audit_tail` (parte do item 2 do DRAFT):** o
  hook do controller lê o tail com limite (500 registros) e filtra por
  `plan_id`.

**Ainda abertos (evoluções futuras — TBD):**

1. **Formato final:** JSON no MVP entregue; Markdown (human-friendly)
   como saída alternativa — não entregue.
2. **Rotacionamento:** reexecução com o mesmo `plan_id` **sobrescreve**
   o relatório (comportamento atual); política de retenção/limpeza de
   relatórios antigos ainda indefinida.
3. **Limite do `audit_tail` configurável por execução** (hoje valor
   fixo no hook do controller).
4. **Export manual via UI (futuro):** botão/ação na tela 🛡 para exportar
   "o último relatório" ou por `plan_id` — fora do MVP entregue.

## Evidências (implementação e testes)

**Implementação (2026-08-31):**

- `app/tools/report_export.py` (novo) — funções puras
  `build_export_payload` (payload `{version: 1, lumen_version,
  exported_at, plan, execution_report, correction_history, audit}`,
  SEMPRE sanitizado via `sanitize_any`) e `export_execution_report`
  (escrita atômica tmp+`os.replace`; diretório só nasce no export) +
  `ReportExportError`.
- `app/tools/control.py` — parâmetros `export_execution_reports`/
  `reports_dir` no construtor do `ToolsController` (default OFF/
  `data/reports`); hook best-effort em `_final` (`_maybe_export_report`:
  só estado terminal + plano ativo; audit filtrado por `plan_id`;
  `safe_name` sanitizado; `try/except` + log — falha nunca quebra o
  report).
- `app/config/settings.py` — campo `export_execution_reports: bool =
  False` + carga via `LUMEN_EXPORT_EXECUTION_REPORTS`.
- `main.py` — passa `export_execution_reports=settings.export_execution_reports`
  + `reports_dir=settings.data_dir / "reports"`.

**Testes (2 novos, 2026-08-31):**

- `tests/test_tools_control.py` — ON: `run_plan` terminal com `plan_id`
  com caracteres inválidos exporta `reports/PLN_11I_TEST#1.json` (nome
  sanitizado; `#` preservado), payload com as 7 chaves, o segredo
  `sk-TESTSECRET` NÃO aparece em nenhuma parte do conteúdo e todo
  record de audit no payload tem `plan_id` == o do report; OFF
  (default): nenhum diretório `reports/` nasce e o plano completa
  normalmente (bit-a-bit).

**Baseline (pós-11I):** **989 passed / 5 skipped / 0 failed (994
coletados)** — suíte completa (medida 2026-08-31). Baseline pré-11I
preservada: 987/5/0 (992 coletados, pós-11H).

---

## Histórico

- **2026-08-31 — Sincronização com a implementação entregue (11I).**
  Status DRAFT → **IMPLEMENTADA + TESTADA**: módulo puro
  `app/tools/report_export.py`, hook best-effort em `_final`, flag
  `export_execution_reports` (Settings/env) e wiring no `main.py`; +2
  testes (export ON c/ nome sanitizado + segredo ausente / OFF bit-a-
  bit); baseline pós-11I 989/5/0 (994 coletados) — baseline do DRAFT
  (987/5/0, 992) preservada. §7 passou a "Decisões e pontos restantes"
  (flag/env, naming e limite de audit RESOLVIDOS; formato md,
  rotacionamento, limite configurável e export manual via UI seguem
  TBD).
- **2026-08-31 — DRAFT inicial (11I).** Mapeamento de relatórios/evidências
  (COMANDO 064 1/3): `ExecutionReport.to_dict()` já cobre todo o dado;
  `_final` é o único funil terminal; audit JSONL já correlaciona por
  `plan_id` (filtro viável); bundles 9B opt-in e **não** acoplados ao 11I.
  Decisões do DRAFT: novo `app/tools/report.py` (build/export puros);
  hook best-effort em `_final`; flag `export_execution_reports` (default
  OFF) + `reports_dir` (default `data_dir/"reports"`); sanitização
  reutilizando o execution_store; export **não** concede permissão, **não**
  executa e é fail-closed por default. Baseline de referência: 987/5/0
  (pós-11H).
