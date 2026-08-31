# SPEC — Fase 11E: Verificação real via run_pytest (sem bypass)

> **Status: IMPLEMENTADA + TESTADA (MVP entregue em 2026-08-31).** A
> Fase 11E foi autorizada em etapas e o MVP descrito em §3/§4 está
> entregue e coberto por testes — ver "Evidências (implementação e
> testes)" abaixo.

- **Base da discussão:** `0.6.8` + fases internas 9A–11D concluídas
  (11D entregou a tool `run_pytest` — registro condicional, checkpoint
  e Planner Catalog; ver `docs/SPEC-11D-BUILD_TEST.md`).
- **Suíte vigente na data deste draft:** 973 passed / 5 skipped /
  0 failed (978 coletados).
- **Leituras complementares:** `docs/SPEC-11D-BUILD_TEST.md` (runner),
  `docs/ARCHITECTURE.md` (executor/checkpoints),
  `app/executor/verification.py`, `app/executor/executor.py`,
  `app/tools/control.py`.

## Evidências (implementação e testes) — MVP entregue em 2026-08-31

**Implementação:**

- `app/executor/verification.py` — `VerificationResult` ganha o campo
  `applied: bool = True` (compatibilidade: chamadas antigas e
  `to_dict()` inalterados) + `PytestResultVerifier`
  (**interpretativo — não executa nada**: sem subprocess/shell;
  `task.tool != "run_pytest"` ⇒ `applied=False` "not applicable";
  `run_pytest` ⇒ `passed = (data.exit_code == 0)`, `detail =
  summary_line`; `timed_out` ⇒ `passed=False`; JSON inválido ⇒ falha
  honesta com motivo claro).
- `app/executor/executor.py` — `PlanExecutor._execute_with_retry`
  respeita `applied`: `False` ⇒ `verified=None` e sem rejeição (mesmo
  fluxo de "sem verifier"); `True` ⇒ comportamento anterior
  (`DONE`+`verified=True` / `REJECTED`+plano falha).
- `app/tools/control.py` — `ToolsController.enable_verification(
  "pytest_result")` / `disable_verification()` (opt-in; default
  `verifier=None`) + wiring: `run_plan` passa o verifier ao
  `PlanExecutor`.

**Testes:**

- `tests/test_executor_retry_verify.py` — 2 testes da flag `applied`
  (não aplicável ⇒ `DONE` + `verified is None`; aplicável+passado ⇒
  `verified is True`).
- `tests/test_terminal_integration.py` — 2 testes E2E no caminho real
  do `ToolsController`: `enable_verification` + `run_pytest` em
  mini-suite **verde** ⇒ `DONE` + `verified=True` (plano `COMPLETED`)
  e mini-suite **vermelha** ⇒ `REJECTED` + `verified=False` (plano
  `FAILED`, fail-fast) — com checkpoint da 11D preservado.

**Baseline atual (regressão completa, 2026-08-31):** 982 coletados —
**977 passed / 5 skipped / 0 failed** (5 skips ambientais; registro
anterior, pós-11D: 973/5/0 — 978 coletados — preservado).

## Estado atual (evidência — auditoria read-only, 2026-08-31)

- **Ponto de verificação:** `PlanExecutor._execute_with_retry()`
  (`app/executor/executor.py`, ~L668–670): após `handler.execute(task)`
  com sucesso, `if self._verifier is not None: outcome =
  self._verifier.verify(task, result)`.
- **Contrato:** `TaskVerifier.verify(task: PlannedTask, result: str)
  -> VerificationResult(passed: bool, detail: str)`
  (`app/executor/verification.py`). Para tools reais, `result` é o JSON
  de `ToolResult.to_dict()` (`ok`, `data`, `error`).
- **Default em produção:** `None` — `ToolsController.run_plan`
  (`app/tools/control.py`, ~L698) constrói o `PlanExecutor` **sem
  verifier**; `TaskRun.verified` fica `None`. Não há config/env/flag de
  verificação; a escolha é injeção de dependência
  (`PlanExecutor(verifier=…)` / `Agent.execute_plan(verifier=…)` /
  `CorrectionEngine(verifier_factory=…)`).
- **Única implementação hoje:** `SimulatedVerifier` (determinístico,
  in-memory) — usado apenas em testes.
- **Semântica:** `passed=True` ⇒ task `DONE` + `verified=True`;
  `passed=False` ⇒ task `REJECTED` + `verified=False` (não consome
  retry) e o plano falha (fail-fast: restantes `SKIPPED`).

## 1. Problema

A verificação de trabalho é hoje **simulada ou inexistente** no caminho
de produção:

- Em `ToolsController.run_plan` (o caminho real do chat/UI) **nenhum
  verifier é instanciado** — tarefas terminam `DONE` sem `verified`
  (evidência: ~L698 de `app/tools/control.py`).
- O único verificador existente (`SimulatedVerifier`) é um
  deterministic in-memory usado **somente em testes** — não confere
  nada do mundo real.
- A 11D já deu ao agente a capacidade de **produzir evidência real**
  (`run_pytest` como tarefa: subprocesso controlado, sandbox, timeout,
  saída estruturada) — mas nada **interpreta** essa evidência no
  ciclo EXECUTOU → VERIFICOU.

Objetivo: **verificação real com evidência e sem bypass** — o ciclo
`EXECUTOU → VERIFICOU → SUCESSO/FALHOU` passa a usar o resultado
estruturado de uma execução de pytest real, mantendo intacta a cadeia
de segurança do projeto.

## 2. Não-objetivos (fora de escopo nesta fase)

- **NÃO** criar tool nova (a execução real é a `run_pytest` da 11D).
- **NÃO** dar ao verifier nenhum poder de execução (ver §3).
- **NÃO** alterar `FORBIDDEN_COMMANDS`, allowlist, `TerminalPolicy`,
  permissões, sandbox ou o contrato de checkpoint.
- **NÃO** introduzir auto-replanning (R4: correção só sob aprovação
  explícita; F17 preservado).
- **NÃO** criar "modo sempre rodar testes após escrita" (TBD §7.2).

## 3. Princípio de segurança (normativo para a implementação)

1. **O Verifier NÃO executa nada.** `PytestResultVerifier` não pode
   importar/usar `subprocess`, shell, `os.system`, `Popen` ou qualquer
   caminho de execução — **apenas interpreta o `result` já produzido**
   pela tarefa (auditoria AST, no padrão dos guards existentes).
2. **A execução real é sempre uma TASK do plano:** `run_pytest` roda
   como tarefa normal com **permissão `TERMINAL` + checkpoint
   obrigatório** (11D) — aprovação executa, recusa não executa. O
   verifier jamais dispara execução por conta própria: não há segundo
   subprocesso escondido fora da coleira.
3. **O Verifier só valida resultados:** lê o JSON `ToolResult` da
   tarefa (`data.exit_code`, `data.summary_line`, `data.timed_out`) e
   devolve `VerificationResult` — sem efeito colateral (sem escrita,
   sem rede, sem spawn).
4. **A cadeia permanece intacta e na mesma ordem:**
   `PermissionManager → TerminalPolicy → WorkspaceSandbox →
   Checkpoint → Tool → Audit → Verifier (interpretação)`. O verifier é
   o último elo — leitura de evidência, nunca porta de entrada.

## 4. Proposta (MVP implementado)

Novo verificador **`PytestResultVerifier(TaskVerifier)`**
(`app/executor/verification.py` ou módulo dedicado — TBD de
localização, sem impacto em segurança):

Comportamento de `verify(task: PlannedTask, result: str)`:

- **`task.tool != "run_pytest"`** ⇒ `passed=True`, `detail="not
  applicable"` — o verifier só opina sobre evidência de pytest;
  tarefas de outras tools seguem o comportamento de hoje (sem
  rejeição decorativa).
- **`task.tool == "run_pytest"`** ⇒ parse do JSON `ToolResult`:
  - `passed = (data.exit_code == 0)`;
  - `detail = data.summary_line` (fallback: `f"exit_code=
    {data.exit_code}"` + `timed_out` quando aplicável);
  - `data.timed_out == True` ⇒ `passed=False` com detail explícito
    (timeout = nenhum resultado válido).
- **`result` inválido / sem JSON / campos ausentes** ⇒ `passed=False`
  com `detail` claro (ex.: "verificador falhou: resultado não é um
  ToolResult de run_pytest") — falha honesta, nunca aprovação
  silenciosa (o executor já trata exceção do verifier como `passed=
  False`, mas o contrato aqui é ser explícito).

Semântica resultante (já implementada no executor, inalterada):

- suíte verde ⇒ task `DONE` + `verified=True`;
- suíte vermelha ⇒ task `REJECTED` + plano `FAILED` (fail-fast;
  restantes `SKIPPED`) — o desfecho estruturado (exit_code/
  summary_line) continua disponível em `TaskRun.result` para o
  usuário/controlador analisar.

## 5. Integração proposta

- **`ToolsController` ganha toggle opt-in:** `enable_verification(
  "pytest")` / `disable_verification()` — espelhando o padrão
  `enable_corrections`/`disable_corrections` (verbo explícito do
  integrador; default OFF = comportamento atual, `verifier=None`).
  O valor `"pytest"` seleciona `PytestResultVerifier` (extensível a
  outros verificadores no futuro, se autorizados).
- **`ToolsController.run_plan` passa o verifier ao `PlanExecutor`**
  quando habilitado (~L698); default continua `None`.
- **Sem nova UI, sem nova permissão, sem novo checkpoint** — o
  checkpoint da execução continua sendo o da 11D (tarefa
  `run_pytest`).
- **Opcional futuro (fora do MVP, exige autorização própria):**
  encaminhar o mesmo verifier ao `CorrectionEngine` via
  `verifier_factory` (`app/executor/correction.py`, ~L292–296) — a
  falha real de verificação (`REJECTED`) passaria a alimentar o ciclo
  controlado de correção (ANALISAR→PROPOR→APROVAR→APLICAR→RETRY→
  VERIFICAR) com limites rígidos e **sem auto-replanning** (R4).

## 6. Plano de testes da própria 11E (quando implementada)

- **Unitários de `PytestResultVerifier`:**
  - `exit_code == 0` ⇒ `passed=True`, detail = `summary_line`;
  - `exit_code != 0` ⇒ `passed=False`, detail com `summary_line`/
    fallback;
  - `timed_out=True` ⇒ `passed=False` com detail explícito;
  - `result` sem JSON / JSON inválido / campos ausentes ⇒
    `passed=False` com detail claro (nunca `passed=True`);
  - `task.tool != "run_pytest"` ⇒ `passed=True` "not applicable".
- **Integração (caminho `ToolsController` real):**
  - plano com tarefa `run_pytest` em mini-suite **verde** +
    `enable_verification("pytest")` ⇒ task `DONE` + `verified=True`;
  - mini-suite **vermelha** (fixture que falha) ⇒ task `REJECTED`,
    plano `FAILED` (fail-fast; task seguinte `SKIPPED`) e evidência
    (`exit_code`/`summary_line`) preservada em `TaskRun.result`;
  - com `disable_verification()` (default) o comportamento de hoje
    não muda (regressão: `verified=None`).
- **Sem execução escondida (guard):** teste AST/anti-futuro — o
  módulo do verifier **não importa/usar** `subprocess`/`shutil`/
  `Popen`/shell (estender o guard existente de `app/tools` ou criar
  equivalente para o novo módulo).
- **Contratos:** contagens de tools inalteradas (nenhuma tool nova) +
  regressão completa com nova baseline explícita.

## 7. Questões abertas (TBD) — decisões da implementação (2026-08-31)

**RESOLVIDO/IMPLEMENTADO nesta entrega (MVP):**

- **Toggle opt-in** — `enable_verification("pytest_result")` /
  `disable_verification()` no `ToolsController` (default OFF =
  `verifier=None`, comportamento anterior preservado).
- **Verificador interpretativo** — sem subprocess/shell (princípio
  §3); a execução real é sempre a task `run_pytest` (11D) com
  TERMINAL + checkpoint.
- **Flag `applied`** — `VerificationResult.applied` (default `True`);
  `applied=False` ⇒ `verified=None` e sem rejeição (coberto por
  testes).
- **E2E** — verde ⇒ `DONE` + `verified=True`; vermelho ⇒ `REJECTED`
  + plano `FAILED` (fail-fast) — coberto por testes no caminho real
  do `ToolsController`.
- **Localização do módulo** (item 4 do draft) —
  `app/executor/verification.py`, junto do contrato.

**Ainda aberto (futuro, NÃO AUTORIZADO):**

1. **Como incentivar o Planner a incluir `run_pytest` ao final do
   plano quando houver tarefas de escrita** (`write_file`/
   `create_file`/`edit_file`)? Opções: regra no prompt do catálogo
   (texto, sem força) vs. validação de protocolo sugerindo a etapa
   (rejeitar? nunca — apenas sugerir) vs. nada (o integrador compõe
   o plano programaticamente, como hoje).
2. **Modo "always run tests after write"** — automação de
   verificação após escrita (ex.: anexar `run_pytest`
   automaticamente). **Futuro, separado, NÃO incluído nesta
   entrega.**
3. **Suites/paths padrões e heurística de `-k`** — o plano segue
   declarando `path`/`k` explicitamente; sugestão padrão no
   catálogo e/ou derivação do `-k` pela tool que escreveu o arquivo
   (ex.: `test_tool_edit_file`) seguem abertos.
4. **Integração com repair-loop** — `verifier_factory` no
   `CorrectionEngine` (spec §5, opcional): `REJECTED` alimentando o
   ciclo controlado de correção (limites rígidos, aprovação
   explícita — **sem auto-replanning**, R4 preservado).
5. **Extensibilidade do toggle** — verificadores além de
   `pytest_result` (ex.: linter) e o contrato do parâmetro
   `verifier_name` para nomes futuros (hoje: qualquer outro valor ⇒
   `ValueError("unknown verifier")`).

---

## Histórico do documento

- 2026-08-31 — draft criado para discussão (status original: "DRAFT /
  EM DISCUSSÃO — 11E PLANEJADA, NÃO AUTORIZADA, NÃO IMPLEMENTADA";
  suíte vigente na época: 973/5/0 — 978 coletados).
- 2026-08-31 — MVP implementado e testado em etapas (verifier +
  `applied`, toggle opt-in, executor, testes, doc sync) e baseline
  atualizada para 977/5/0 (982 coletados).

---

*Única fonte de verdade é o código — ver "Evidências (implementação e
testes)" acima. Esta spec descreve o MVP entregue; itens marcados
"aberto" são futuros e não autorizados.*
