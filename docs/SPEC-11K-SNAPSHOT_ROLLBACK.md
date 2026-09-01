# Spec 11K — Snapshot/rollback mínimo para operações destrutivas (filesystem)

**Status:** **IMPLEMENTADA + TESTADA** (entregue em 2026-09-01) —
baseline oficial pós-11K: **1000 coletados — 995 passed / 5 skipped /
0 failed**. Status anterior (DRAFT / EM DISCUSSÃO) preservado no
Histórico.

**Escopo:** criar o **snapshot mínimo** do "antes" antes de cada operação
destrutiva de filesystem, registrar **somente metadados** na auditoria e
propor (TBD até aprovação) uma tool de **rollback manual com checkpoint** —
sem conceder permissões, sem bypass, sem execução escondida e preservando a
coleira (checkpoint/permissões/políticas inalteradas).

**Fora do escopo (MVP):** snapshot de diretórios; rollback de terminal;
restauração automática; retenção/limpeza além de teto simples (TBD §9);
mudança de permissões/checkpoints/tetos/Planner.

> Baseline da suíte na data do DRAFT: **990 passed / 5 skipped / 0 failed**
> (995 coletados) — baseline pós-11J (commit `129a0ea`).

---

## 1. Status

- **IMPLEMENTADA + TESTADA** (entregue em 2026-09-01) — ver "Evidências
  (implementação e testes)" abaixo. Status anterior (DRAFT / EM
  DISCUSSÃO — planejada, não implementada) preservado no Histórico.
- Pré-requisitos entregues: 0.5 (Filesystem Tools), 11C (`edit_file`), 11D
  (`run_pytest`), 11E/11F/11G (verificação/auto-anexo/evidência), 11H
  (toggles persistentes + UI), 11I (export de relatório), 11J (conselho com
  evidência) — todos commitados.
- As decisões de fluxo/UX/política do DRAFT foram resolvidas na entrega
  (ver §9); seguem abertas apenas as evoluções futuras (fora do MVP).

## Evidências (implementação e testes) — 2026-09-01

**Implementação:**

- `app/tools/snapshot_store.py` — `SnapshotStore` + `SnapshotManifest`
  (frozen, `version: 1`) + backup `before.bin`; nomes sanitizados
  (`_safe_name`); **best-effort**: qualquer erro vira manifest com
  `skipped_reason` (sem exceção para o chamador).
- `app/tools/handler.py` + `app/tools/control.py` — wiring do snapshot
  "before" **opt-in** (`enable_snapshots`, **default OFF** — bit-a-bit;
  `snapshots_dir` default `data/snapshots`; `snapshot_max_bytes` 1 MiB;
  store sem efeitos colaterais no startup): o handler snapshota o alvo
  de cada tool destrutiva **depois do checkpoint aprovado e antes da
  tool**; audit `operation="snapshot_before"` com **somente
  metadados** (sem conteúdo).
- `app/tools/restore_snapshot.py` — tool `restore_snapshot` (permissão
  **WRITE**; **sem terminal/subprocess** — stdlib):
  `existed_before=True` → restaura os bytes do `before.bin`
  (`bytes_restored` no resultado); `existed_before=False` → desfaz o
  create (delete idempotente — `already_gone`); manifest
  ausente/inválido ⇒ falha honesta (sem restore especulativo); destino
  sempre via `sandbox.resolve` do `requested_path` do manifest
  (anti-traversal).
- `app/tools/control.py` — registro no registry
  **independentemente do terminal** + **checkpoint pré-validado** para
  `restore_snapshot`: pausa somente quando viável (WRITE concedida +
  parâmetros + manifest existe + `sandbox.resolve` +
  `check_operation` WRITE/DELETE); inviável ⇒ a task **falha direto**
  com o motivo (sem aprovação decorativa).

**Testes:**

- `tests/test_tools_control.py` — snapshot OFF/ON (com OFF bit-a-bit:
  nada criado; com ON manifest/backup + audit metadados) e
  `restore_snapshot` com **rollback real** (ANTES→DEPOIS→ANTES sob
  checkpoint) + `snapshot_not_found` **sem checkpoint decorativo**
  (084/087).
- `tests/test_tools_correction.py` — snapshots em root e em sucessor
  `#C1` (084).
- `tests/test_terminal_integration.py` — inventário de tools
  atualizado: `restore_snapshot` presente no registry mesmo **sem
  terminal** (091).

**Baseline oficial pós-11K:** **1000 coletados — 995 passed / 5
skipped / 0 failed** (regressão completa).

## 2. Evidência do estado atual (mapeamento — COMANDO 080 1/3)

- **Tools destrutivas** (`app/tools/filesystem.py ::
  FILESYSTEM_DESTRUCTIVE_TOOLS`): `write_file`, `create_file`,
  `delete_file`, `edit_file` — candidatas a checkpoint/consentimento.
  Terminal **não** tem lista por nome (checkpoint é por comando, via
  `AllowedCommand.requires_approval` — default True).
- **Escrita/remoção direta (sem atomicidade, sem backup):**
  - `WriteFileTool._perform`: `resolved.write_text(content)` (sobrescreve se
    existir; devolve `overwritten`);
  - `CreateFileTool._perform`: falha se existe; mesmo `write_text`;
  - `DeleteFileTool._perform`: `resolved.unlink()`;
  - `EditFileTool` (11C): `resolved.write_text(new_content)`.
  - O padrão de escrita atômica (`.tmp` + `os.replace`) existe **só** em
    stores internos (`WorkspaceStore`/`TerminalStore`/`RecordStore`) — sem
    helper público reutilizável.
- **Checkpoint hoje é consentimento, não restore:** `CheckpointRequest`
  (frozen: `id`/`task_id`/`reason`/`status`/`note`/`decided_at`/
  `created_at`) pausa **antes** de executar (`PlanExecutor._maybe_checkpoint`);
  aprovar ⇒ executa; recusar ⇒ plano `FAILED` controlado — **não existe
  "desfazer"** de nada que já tenha sido executado.
- **Ponto "antes" já disponível:** `_WriteBaseTool.execute` tem o caminho
  **resolvido e validado** antes de `_perform` (choke point natural); o
  handler/controller é o ponto com **`plan_id`/`task_id`** visíveis.
- **Auditoria:** `FilesystemTool._audit_record` → `AuditRecord` (frozen;
  `detail: dict` = **metadados apenas** — "conteúdo de arquivos nunca é
  armazenado") → `JsonlAuditSink` (JSONL); as tools já passam `_audit` →
  `detail` (`bytes_written`, `overwritten`); export 11I já carrega `detail`
  sanitizado.
- **9B:** persiste bundle plan/report/correction (opt-in) — **não** é
  snapshot de arquivo.

## 3. Objetivo (MVP)

- Antes de cada operação destrutiva de filesystem (que já passou no
  checkpoint vigente, i.e., **já aprovada**), criar o **snapshot do "antes"**:
  - arquivo **existe** ⇒ copiar o conteúdo atual para
    `data_dir/snapshots/…` (backup real dos bytes);
  - arquivo **não existe** (`create_file`) ⇒ manifest com
    `existed_before=False` (sem cópia — o rollback é **deletar** o que foi
    criado);
  - falha do snapshot: best-effort (default no DRAFT) — ver TBD §9.1.
- **Registrar metadados na auditoria (sem conteúdo):** `snapshot_id`,
  `backup_path` (relativa), `bytes_before`, `existed_before`, motivo de
  skip/erro — via o canal existente `_audit` → `AuditRecord.detail` (JSONL +
  relatório 11I).
- **Rollback manual mínimo** (proposto neste DRAFT — TBD até aprovação):
  tool `restore_snapshot` (§7) — **sempre WRITE + checkpoint + auditoria**.

## 4. Princípios de segurança (normativo)

1. **Snapshot/restore não concede permissões:** snapshot é leitura+cópia de
   bytes do arquivo **já validado** (resolve + `check_operation` passaram);
   nada de nova capacidade. Restore exige as mesmas regras de uma escrita
   comum (`WRITE`; `allow_delete` quando envolver exclusão).
2. **Restore é sempre WRITE + checkpoint:** `restore_snapshot` é destrutiva
   (sobrescreve/deleta) ⇒ entra em `FILESYSTEM_DESTRUCTIVE_TOOLS` ⇒
   **checkpoint obrigatório** — **nunca** "desfazer" sem aprovação
   explícita do usuário.
3. **Sem execução escondida:** snapshot e restore são **cópia local de
   bytes** (stdlib — `shutil`/leitura+escrita) — **sem terminal, sem
   subprocess**, sem tool externa, sem shell.
4. **Fail-closed por default:** feature **OFF por default** (opt-in do
   integrador via controller/Settings — padrão 11F/11H); com OFF a
   operação é **bit-a-bit idêntica** à atual (sem snapshot, sem campo no
   audit). Com ON e snapshot falhando: best-effort vs required — TBD §9.1.
5. **Sem vazamento de conteúdo:** auditoria/JSONL/relatório 11I carregam
   **somente metadados** (ids, caminhos relativos, tamanhos, flags) — o
   conteúdo fica apenas em `data_dir/snapshots/` (fora do Git, padrão
   `data/`); limites de tamanho/retenção: §6 + TBD §9.2.

## 5. Proposta técnica (recomendada)

- **`SnapshotStore`** (módulo `app/tools/snapshot_store.py`, sem
  importar engine/UI):
  - `snapshot_before(...)` → **manifest JSON** (frozen dataclass +
    serialização `version: 1`):
    - `snapshot_id` (`SN-<plan>-<task>-<seq>`), `created_at`, `plan_id`,
      `task_id`, `tool`, `requested_path`, `resolved_path` (forma segura —
      base name/relativa ao workspace),
    - `existed_before: bool`, `bytes_before: int | None`,
    - `backup_relpath: str | None` (relativa a `data_dir/snapshots/`;
      `null` quando não houve cópia — novo/limite/erro),
    - `skipped_reason: str | None` (`"size"`, `"error: …"`, `null`).
  - Armazenamento: `data_dir/snapshots/<plan_id_sanitized>/<task_id>/<seq>-
    <nome>.bak` + manifest JSON ao lado (mesma sanitização de path do 11I;
    `data/` já é o padrão do projeto — workspaces/audit/terminal/toggles/
    reports).
- **Local de inserção (recomendado): handler/controller level** —
  `ToolTaskHandler.execute` (antes de `registry.execute`) ou wrapper do
  controller no ponto de execução: é o único ponto que conhece **ao mesmo
  tempo** `plan_id`/`task_id` (contexto de auditoria) e o conjunto
  `FILESYSTEM_DESTRUCTIVE_TOOLS`, **sem a tool precisar saber de plan/task**:
  - se `task.tool` ∈ destrutivas **E** `path` existe **E** feature ON ⇒
    `SnapshotStore.snapshot_before(…)`;
  - `snapshot_id`/metadados anexados à auditoria da operação via `detail`;
  - **alternativa (rejeitada neste DRAFT):** dentro de
    `_WriteBaseTool._perform` — "antes" mais próximo da mutação, porém as
    tools não recebem `plan_id`/`task_id` como parâmetros (só via contexto
    escopado da auditoria) — acoplamento maior.
- **Restore (MVP):** `RestoreSnapshotTool` (`restore_snapshot`, permissão
  **WRITE**, destrutiva ⇒ checkpoint; §7): lê o manifest (relativo a
  `data_dir/snapshots/`, validado; schema `version: 1`), aplica a ação
  correspondente e audita metadados (`snapshot_id`, destino,
  `bytes_restored`) — **sem conteúdo**.

## 6. Política de limites (MVP)

- **`max_snapshot_bytes`** (default TBD §9.4 — proposta **1 MiB**, coerente
  com o limite de leitura do `read_file` e a recusa de `edit_file` para
  >1 MiB): acima ⇒ **sem cópia** (manifest com `existed_before` e
  `skipped_reason="size"` — a operação segue normalmente).
- **Binário:** proposta = **permitido** (cópia de bytes, sem interpretação
  de conteúdo; o teto é o único limite); alternativa = bloquear
  (`skipped_reason="binary"`) — TBD §9.4.
- **Falha do snapshot:** best-effort (operação **prossigue**; audit com
  `skipped_reason="error: …"`) vs required (operação **bloqueada**) — TBD
  §9.1 (default no DRAFT: **best-effort**).
- **Retenção:** teto de quantidade/tamanho em `data_dir/snapshots/` — TBD
  §9.2 (proposta MVP: **sem GC automático**; warning no audit ao estourar o
  teto).

## 7. Rollback (MVP)

- Tool **`restore_snapshot`** (entregue — ver "Evidências" acima):
  - Parâmetro: `snapshot_id` (ou `manifest_path` relativa a
    `data_dir/snapshots/`) — exatamente 1; manifest deve existir e ser
    válido (schema `version: 1`; corrompido ⇒ falha controlada, **nunca**
    escrita parcial).
  - Matriz de comportamento:
    | Cenário | Manifest | Ação do restore |
    | ------- | -------- | --------------- |
    | arquivo existia (write/edit) | `existed_before=True` + backup | sobrescreve o conteúdo atual com o backup |
    | arquivo foi **criado** (create) | `existed_before=False` | **deleta** o arquivo (política `allow_delete` vale) |
    | arquivo foi **deletado** (delete) | backup do `unlink` | **recria** o arquivo a partir do backup |
  - **Sempre checkpoint** (destrutiva) + auditoria (metadados); destino
    fora do workspace ⇒ bloqueado pelo sandbox existente
    (`resolve`/`check_operation`); manifest apontando para caminho inválido
    ⇒ falha controlada.
  - **Sem auto-restore:** rollback nunca é automático (nem pós-execução,
    nem via correção) — sempre ação explícita do usuário.

## 8. Plano de testes (executado em 2026-09-01 — ver "Evidências")

- **Unit (SnapshotStore):** criação do manifest (campos completos),
  caminhos seguros (traversal/absoluto fora de `data_dir` ⇒ rejeitado),
  limite de tamanho (`skipped_reason="size"`), `existed_before=False`
  (sem cópia), manifest corrompido ⇒ erro controlado, feature OFF ⇒
  **nada** criado em `data_dir/snapshots/`.
- **Integração (snapshot):** com ON, `write_file`/`edit_file`/
  `create_file`/`delete_file` ⇒ snapshot + manifest + `snapshot_id`/
  `backup_path` na auditoria JSONL (e relatório 11I) **sem conteúdo**;
  com OFF ⇒ bit-a-bit (sem diretório, sem campo no audit).
- **Integração (restore):** os 3 cenários da matriz §7 revertem
  corretamente **com checkpoint** (aprovar restaura; recusar não muda
  nada); manifest inválido ⇒ falha sem escrita parcial; destino fora do
  workspace ⇒ bloqueado; sem auto-restore em nenhum fluxo.
- **Regressão completa:** suíte inteira sem regressão; baseline pós-11J
  (990/5/0) como piso.

## 9. Questões abertas (TBD)

**RESOLVIDAS na entrega (2026-09-01):**

- **Best-effort vs required (falha do snapshot):** entregue como
  **best-effort** (não bloqueia; erro registrado no audit com
  `skipped_reason`) — o modo "required" segue como evolução (TBD 1).
- **Binário e tamanho:** entregue **permitindo** cópia de binário
  (cópia de bytes, sem interpretação de conteúdo) com
  `max_snapshot_bytes` = **1 MiB** (coerente com read/edit) — ajuste
  de teto segue aberto (TBD 1).
- **Opt-in OFF por default + pré-validação de checkpoint:** entregues
  (OFF bit-a-bit; `restore_snapshot` pausa só quando viável, senão
  falha direto).

**ABERTAS (evoluções futuras — NÃO IMPLEMENTADAS):**

1. **Modo "required"** (falha do snapshot bloqueia a operação) e/ou
   ajuste de `max_snapshot_bytes` (1 MiB vs 5 MiB).
2. **Retenção/GC:** quantos snapshots manter/limpar (por plano? por
   arquivo? teto em MiB?); apenas o "último" por arquivo? GC explícito
   vs automático; migração/limpeza de planos antigos — o MVP **não
   tem GC automático** (uma cópia por plano/task, sem limpeza).
3. **UI:** botão "rollback do último snapshot" na tela 🛡 — o MVP é
   tool (plano/programático) apenas.
4. **Rollback robusto/contínuo:** snapshots de diretório, rollback em
   massa, "snapshot só quando viável" (hoje: snapshot sempre que a
   feature está ON, antes da tool) e restauração automática — todos
   fora do MVP (fora do escopo preservado).

---

## Histórico

- **2026-08-31 — DRAFT inicial (11K).** Mapeamento do estado atual
  (COMANDO 080 1/3): destrutivas via `FILESYSTEM_DESTRUCTIVE_TOOLS`;
  escrita/remoção direta (sem atomicidade/backup); checkpoint =
  consentimento (sem restore); ponto "antes" em `_WriteBaseTool` e
  `plan_id`/`task_id` no handler/controller; auditoria metadados-somente
  via `detail`. Decisões do DRAFT: `SnapshotStore` em
  `data_dir/snapshots/` com manifest JSON (snapshot_id/created_at/
  plan_id/task_id/tool/caminhos/existed_before/bytes_before/
  backup_relpath); inserção em handler/controller level (evita tool saber
  plan/task); `restore_snapshot` manual, **sempre WRITE + checkpoint**;
  OFF por default; **sem bypass, sem execução escondida, sem vazamento de
  conteúdo**. Baseline de referência: 990/5/0 (pós-11J, commit `129a0ea`).
- **2026-09-01 — IMPLEMENTADA + TESTADA (11K entregue).** Snapshot
  "before" opt-in (default OFF — bit-a-bit) em
  `app/tools/snapshot_store.py` + wiring em `handler.py`/`control.py`
  (audit metadados); tool `restore_snapshot` (WRITE, sem
  terminal/subprocess) em `app/tools/restore_snapshot.py` com registro
  no registry independente do terminal + checkpoint pré-validado em
  `control.py`; +5 testes focados (084/087) + inventário de tools em
  `test_terminal_integration.py` (091). Hotfix: cópia do backup sem
  `shutil` (guard AST de `app/tools/`). Baseline oficial pós-11K:
  **1000 coletados — 995 passed / 5 skipped / 0 failed**. Status
  anterior (DRAFT / EM DISCUSSÃO) preservado na entrada acima.
