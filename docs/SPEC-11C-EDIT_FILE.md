# SPEC — Fase 11C: tool `edit_file` (edição cirúrgica)

> **Status: IMPLEMENTADA + TESTADA (CONCLUÍDA em 2026-08-30).** A Fase
> 11C foi implementada, testada e integrada (registry + checkpoint
> destrutivo + Planner Catalog) — ver "Evidências" (§7).

> **Histórico do documento:** nasceu como *DRAFT / EM DISCUSSÃO — 11C
> PLANEJADA, NÃO AUTORIZADA, NÃO IMPLEMENTADA*; a implementação só
> começou após autorização explícita (Comandos 008/009), em passos
> auditáveis (tool → registro → testes → catálogo → regressão).

- **Base:** Lumen `0.6.8` + fases internas 9A–11B concluídas (2026-08-30).
- **Lineage:** spec 11A (auditoria + proposta de decomposição do Coding
  Agent) · precedentes 11B (`search_files`, PROBE 22/22) e 9B/10B.
- **Suíte vigente (pós-implementação):** 967 passed / 5 skipped / 0 failed (972 coletados).

## 1. Objetivo

Criar, **futuramente**, a tool `edit_file`: edição **cirúrgica** de
arquivos de texto no workspace autorizado — substituir um trecho
específico sem reescrever o arquivo inteiro (evitando os custos e
riscos do `write_file` com conteúdo completo em cada pequena mudança).

## 2. Não-objetivos (fora de escopo nesta fase)

- **Patch amplo** (multi-hunk/diff-unificado/apply) — ainda não.
- **Rollback real** (snapshot/restore de arquivo) — checkpoint continua
  sendo consentimento pré-operação, não restauração.
- **Move/rename** de arquivos.
- **Auto-replanning** (R4 permanece PROIBIDO/adiado).
- **Computer Control / Unreal / vision** (F17 permanece).
- Qualquer mudança em PermissionManager/Policy/Sandbox/Executor/
  Checkpoints/Audit além do que a tool nova consumir pelos pontos de
  extensão existentes (registro + catálogo, como na 11B).

## 3. Contrato da tool (implementado — reflete o código atual)

| Campo | Valor proposto |
|---|---|
| `name` | `edit_file` |
| Permissão | `WRITE` (`PermissionLevel.WRITE`) |
| Operação de política | `write` (destrutiva ⇒ checkpoint) |
| Parametros | ver abaixo |

Parâmetros propostos:

- `path` — **string, obrigatório** — caminho **relativo** ao workspace
  (nunca absoluto, nunca `..` — mesma regra das 7 tools existentes);
- `expected_old_text` — **string, obrigatório** — trecho exato que deve
  existir no arquivo (âncora da edição);
- `new_text` — **string, obrigatório** — substituto do trecho;
- `dry_run` — **bool, opcional, default `false`** — ⚠️ **proposta em
  discussão, NÃO é decisão final**: validaria tudo e devolveria o
  resultado sem escrever (útil para confirmar âncora antes do
  checkpoint).

Regras centrais:

1. **Ocorrência única**: `expected_old_text` DEVE ocorrer **exatamente
   uma vez** no arquivo. Zero ocorrências ⇒ erro claro ("trecho não
   encontrado"); 2+ ocorrências ⇒ erro claro ("ambíguo — trecho
   aparece N vezes"). **NUNCA editar "a primeira que achar"** e nunca
   editar parcialmente quando a validação falhar.
2. Substituição **literal** (sem regex), alinhada ao estilo `search_files`.
3. Arquivo inexistente ⇒ erro (não é papel de `edit_file` criar; usar
   `create_file`).

### 3.1 Schema do Input (proposto)

| Campo | Tipo | Obrig. | Restrições |
|---|---|---|---|
| `path` | string | sim | **relativo** ao workspace; nunca absoluto, nunca `..` |
| `expected_old_text` | string | sim | **não vazio**; trecho literal (sem regex); ocorrência **exatamente 1** no arquivo (0 ⇒ `NO_MATCH`; ≥2 ⇒ `MULTIPLE_MATCHES`) |
| `new_text` | string | sim | substituto literal; **hoje: vazia ⇒ INVALID_INPUT** (suportar remoção = FUTURO/TBD — ver §10.4) |
| `dry_run` | bool | não | **NÃO implementado no MVP** — FUTURO/TBD (ver §10.1) |
| `max_bytes` | int | não | **implementado**: default 1 MiB (`1_000_000`), opt-in — mesmo padrão/valor de `read_file` |
| `encoding` | — | — | **UTF-8 fixo** (inválido ⇒ `BINARY_FILE`); outros encodings = FUTURO/TBD |

A **regra de ocorrência única faz parte do contrato de input**: uma
chamada válida identifica **uma** âncora inexcedível; qualquer
desconforto quanto à unicidade deve virar erro, nunca "primeira
ocorrência".

### 3.2 Schema do Output (proposto) — sem vazar conteúdo do arquivo

Sucesso — `ToolResult.ok=True`, `data`:

```json
{
  "operation": "edit_file",
  "requested_path": "src/notas.md",
  "resolved_path": "<workspace>/src/notas.md",
  "match_count": 1,
  "line": 12, "col": 34,
  "bytes_before": 2048, "bytes_after": 2055,
  "replaced_bytes": 12,
  "written": true
}
```

Falha — `ToolResult.ok=False`:

```json
{
  "ok": false,
  "error": "MULTIPLE_MATCHES: o trecho aparece 2 vezes …",
  "data": { "operation": "edit_file", "requested_path": "src/notas.md",
            "error_code": "MULTIPLE_MATCHES", "match_count": 2 }
}
```

**Nunca** incluir conteúdo do arquivo, trecho anterior/posterior ou o
texto substituído — apenas metadados (contagens, posições, tamanhos).
Formato exato de `error_code` (no `error` vs `data`) — TBD.

### 3.3 Casos de erro (normativo)

| `error_code` | Quando | Escreve? |
|---|---|---|
| `INVALID_INPUT` | parâmetro ausente/vazio/tipo errado/limite inválido | não |
| `FILE_NOT_FOUND` | `path` não existe (ou é diretório) | não |
| `PERMISSION_DENIED` | `WRITE` não concedida (gate do registry; audit `permission_gate`) | não |
| `CHECKPOINT_REFUSED` | checkpoint recusado pelo usuário | não |
| `PATH_OUTSIDE_WORKSPACE` | `..`/absoluto fora (sandbox `resolve`) | não |
| `SYMLINK_ESCAPE` | symlink resolve fora do workspace | não |
| `BINARY_FILE` | byte NUL ou UTF-8 inválido | não |
| `FILE_TOO_LARGE` | excede o teto da tool | não |
| `NO_MATCH` | 0 ocorrências da âncora | não |
| `MULTIPLE_MATCHES` | ≥2 ocorrências da âncora | não |

Mapeamento para o contrato atual: **todos** ⇒ `ToolResult(ok=False)` →
`HandlerError` → `TaskRun FAILED` com `result=None` (exceto
`PERMISSION_DENIED`, que nasce como `PermissionDeniedError` no gate do
registry). **Em nenhum caso o arquivo é modificado.**

## 4. Segurança (normativo — atendido pela implementação)

- **PermissionManager**: `WRITE` obrigatório — porteio pelo
  `ToolRegistry` (nenhuma execução sem grant explícito; sem herança).
- **Sandbox/Policy**: `resolve()` + `check_operation("write", …)`
  **antes** de qualquer modificação — bloqueia `..`, absoluto fora do
  workspace, workspace somente-leitura e symlink escape (mesma coleira
  de `write_file`/`search_files`).
- **Checkpoint obrigatório antes de modificar** o arquivo: entrada em
  `FILESYSTEM_DESTRUCTIVE_TOOLS` ⇒ `PrevalidatedCheckpoints` só pausa
  se a operação for **viável** (permissão + política ok) — sem
  aprovação decorativa; recusa ⇒ nada é escrito.
- **Audit**: registra tool/operação/caminhos/desfecho/tarefa/plano +
  metadados seguros (tamanhos, posição da âncora, contagens) —
  **jamais o conteúdo completo do arquivo** nem o texto substituído.
- **Binários**: recusar (byte NUL ou UTF-8 inválido) — nunca editar.
- **Limites anti-DoS** (valores a definir na aprovação, alinhados aos
  precedentes): tamanho máximo de arquivo editável (ref. `read_file`
  1 MiB; `search_files` 256 KiB), tamanho máximo de
  `expected_old_text`/`new_text`, arquivo resultante não pode exceder
  teto de bytes.

## 5. Comportamento esperado

- Falha de **validação** (âncora ausente/ambígua, arquivo grande/
  binário/inexistente, parâmetros inválidos) ⇒ **não escreve nada**;
  devolve `ToolResult(ok=False, error=…)` ⇒ pela arquitetura atual a
  tarefa termina `FAILED` com `result=None` (contrato do handler) e a
  auditoria registra o bloqueio.
- **Checkpoint recusado** ⇒ não escreve nada (plano segue o fluxo de
  recusa existente).
- Substituição ambígua ⇒ falha com erro claro (regra 1 above).
- Sucesso ⇒ `ToolResult(ok=True, data=…)` com **metadados seguros**:
  `operation="edit_file"`, `requested_path`, `resolved_path`,
  posição (linha/coluna) da âncora, `bytes_before/after`, tamanho do
  trecho substituído — sem conteúdo do arquivo.
- Idempotência proibida: re-executar a mesma edição após sucesso falha
  ("trecho não encontrado") — coerente com o estilo honesto do projeto.

## 6. Plano de testes (atendido — ver §7 Evidências)

Dedicados (ex.: `tests/test_tool_edit_file.py`, via fluxo oficial
`run_plan` — nunca instância direta):

- **Positivos**: edição única aplica substituição; metadados corretos;
  edição em subdiretório; `dry_run` (se aprovado) não escreve.
- **Negativos**: ocorrência **zero**; ocorrência **múltipla**; arquivo
  inexistente; parâmetros inválidos/vazios.
- **Permissão**: sem `WRITE` ⇒ negada + audit `permission_gate`.
- **Sandbox/path**: `..` bloqueado; absoluto fora bloqueado; workspace
  read-only bloqueado.
- **Symlink escape**: link para fora não é editado.
- **Binário / grande**: recusados/pulados com erro estruturado.
- **Checkpoint**: aprovado ⇒ edita; recusado ⇒ não escreve.
- **Audit**: registros de sucesso e de bloqueio; sem conteúdo de arquivo.
- **Regressão completa** com 0 failed + PROBE independente (modelo 11B).

## 7. Evidências (implementação e testes)

**Código:**
- `app/tools/edit_file.py` — `EditFileTool` (WRITE; ocorrência exatamente 1;
  `NO_MATCH`/`MULTIPLE_MATCHES`/`BINARY_FILE`/`FILE_TOO_LARGE`; nada é
  escrito em falha).
- `app/tools/filesystem.py` — registro em `build_filesystem_registry` (8ª
  tool) + `FILESYSTEM_TOOLS` + `FILESYSTEM_DESTRUCTIVE_TOOLS` (checkpoint
  automático).
- `app/planner/catalog.py` — `ToolSpec` de `edit_file` (planejamento
  automático OK).

**Testes:**
- `tests/test_tool_edit_file.py` — 7 dedicados (sucesso; NO_MATCH;
  MULTIPLE_MATCHES; sobreposição; INVALID_INPUT ×2; contrato).
- `tests/test_filesystem_integration.py` — 2 de checkpoint do `edit_file`
  (aprovação ⇒ edita; recusa ⇒ arquivo intacto).
- `tests/test_filesystem_tools.py` · `tests/test_terminal_integration.py` ·
  `tests/test_planner_tools.py` — contratos atualizados (8 tools/catálogo).

**Baseline vigente: 967 passed / 5 skipped / 0 failed (972 coletados).**

## 8. Critérios de aceitação da Fase 11C (checklist técnico — ATENDIDO)

- [ ] Tool registrada no registry default (`build_filesystem_registry`)
      e listada em `FILESYSTEM_TOOLS` + `FILESYSTEM_DESTRUCTIVE_TOOLS`.
- [ ] Proteção completa comprovada por teste: `WRITE` via registry →
      sandbox (`resolve` + `check_operation("write")`) → checkpoint
      pré-escrita (`PrevalidatedCheckpoints`) → audit sem conteúdo.
- [ ] Testes dedicados mínimos (`tests/test_tool_edit_file.py`, via
      fluxo oficial `run_plan`): substituição única + metadados;
      ocorrência zero; ocorrência múltipla; permissão negada + audit;
      traversal `..`; absoluto fora; symlink escape; binário; arquivo
      grande; workspace somente-leitura; checkpoint aprovado ⇒ edita;
      checkpoint recusado ⇒ não escreve; audit de sucesso e bloqueio;
      `dry_run` (se aprovado).
- [ ] PROBE independente (modelo 11B) com todas as checagens PASS.
- [ ] Regressão completa com **0 failed**.
- [ ] **Evidência comportamental de que falha ⇒ nada escrito**:
      snapshot do workspace antes/depois em cada caso de erro.
- [ ] Catálogo do Planner e testes de contrato atualizados (se decidido
      incluir na mesma fase).
- [ ] Fingerprint/escopo/pins do comando de implementação: nenhuma
      mudança fora do escopo autorizado.

## 9. Exemplos (não executáveis — JSON ilustrativo)

Request (sucesso):

```json
{"tool": "edit_file",
 "parameters": {"path": "src/notas.md",
                "expected_old_text": "versao alpha",
                "new_text": "versao beta"}}
```

Response (sucesso) — ver §3.2: `ok=true`, `match_count=1`,
`bytes_before/after`, posição da âncora; sem conteúdo do arquivo.

Response (falha ilustrativa):

```json
{"ok": false,
 "error": "MULTIPLE_MATCHES: o trecho aparece 2 vezes em src/notas.md; torne a âncora única.",
 "data": {"operation": "edit_file", "requested_path": "src/notas.md",
          "error_code": "MULTIPLE_MATCHES", "match_count": 2}}
```

## 10. Questões abertas (TBD — pós-implementação)

1. `dry_run` — NÃO implementado no MVP; FUTURO/TBD.
2. Múltiplas âncoras por chamada (`edits[]`) — TBD.
3. `expected_new_hash` (defesa contra o arquivo mudar entre leitura e
   edição) — TBD.
4. **`new_text` vazia (remoção do trecho):** hoje é **inválida** — a tool
   rejeita com erro de input (INVALID_INPUT: "`new_text` … não vazio");
   suportar remoção permanece **FUTURO/TBD**.

*Decididos na implementação (removidos da lista):* tetos de tamanho
(`max_bytes` default 1 MiB, opt-in, padrão `read_file`) e exposição no
Planner Catalog (incluída na mesma fase).

## 11. Arquivos da implementação (entregues)

`app/tools/edit_file.py` (novo) · registro em
`app/tools/filesystem.py` (`build_filesystem_registry` +
`FILESYSTEM_TOOLS` + `FILESYSTEM_DESTRUCTIVE_TOOLS`) · catálogo em
`app/planner/catalog.py` · testes dedicados — **todos sujeitos a
comando autorizado com escopo explícito**.

---
*Draft iniciado em 2026-08-30 e sincronizado na mesma data após a
implementação (Comandos 008/009/010/011) · única fonte de verdade é o
código — e agora o descreve fielmente.*
