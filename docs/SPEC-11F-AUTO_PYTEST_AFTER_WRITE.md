# SPEC — Fase 11F: auto-anexo de run_pytest após WRITE (auto-append)

> **Status: IMPLEMENTADA + TESTADA (entregue em 2026-08-31).** A Fase
> 11F foi autorizada em etapas (mapeamento read-only, spec,
> implementação e testes focados) e o MVP descrito em §3–§6 está
> entregue e coberto por testes — ver "Evidências (implementação e
> testes)" abaixo. O status original (DRAFT / em discussão) fica
> preservado em "Histórico do documento".

- **Base da discussão:** `0.6.8` + fases internas 9A–11E concluídas
  (11D: tool `run_pytest`; 11E: verificação real opt-in; ver
  `docs/SPEC-11D-BUILD_TEST.md` e `docs/SPEC-11E-REAL_VERIFICATION.md`).
- **Suíte vigente após a entrega:** 980 passed / 5 skipped /
  0 failed (985 coletados); baseline na data do draft: 977 passed / 5
  skipped / 0 failed (982 coletados, pós-11E) — preservada como
  histórico.
- **Evidência de base:** mapeamento read-only (COMANDO 039, parte
  1/3, 2026-08-31) — os arquivos/linhas citados em §2 vêm dessa
  auditoria.
- **Leituras complementares:** `docs/SPEC-11D-BUILD_TEST.md` (runner),
  `docs/SPEC-11E-REAL_VERIFICATION.md` (verifier),
  `docs/ARCHITECTURE.md` (executor/checkpoints),
  `app/tools/control.py`, `app/planner/planner.py`,
  `app/executor/executor.py`.

## Evidências (implementação e testes) — entregue em 2026-08-31

**Implementação:**

- `app/tools/control.py` — auto-anexo em `ToolsController.run_plan`
  (antes dos ramos CorrectionEngine/PlanExecutor): helpers puros de
  módulo `_needs_auto_pytest` / `_attach_run_pytest` /
  `_auto_pytest_limit_report`. O anexo ocorre apenas quando terminal
  habilitado + verificação 11E habilitada + plano contém WRITE e não
  contém `run_pytest`; usa `replace(plan, tasks=…)` (`Plan` é frozen)
  e atualiza `self._plan` para a persistência 9B. Guardrail: plano em
  12/12 tasks + anexo necessário ⇒ `ExecutionReport` `FAILED` com
  tudo `SKIPPED` **antes de qualquer execução** (sem chamadas de
  tool, sem checkpoints).

**Testes:**

- `tests/test_tools_control.py` — 3 testes 11F: (1) anexo após WRITE
  (task final `T2` com `tool="run_pytest"`, `{"path": "tests"}`,
  `dependencies=("T1",)`, presente no relatório); (2) sem anexo com
  verificação OFF / terminal OFF / `run_pytest` já no plano
  (idempotência); (3) 12/12 tasks ⇒ `FAILED` antes de executar (tudo
  `SKIPPED`, sem checkpoint, zero execuções de tool na auditoria).

**Baseline:** 985 coletados — 980 passed / 5 skipped / 0 failed
(anterior, pós-11E: 977/5/0 (982) — preservada).

## 2. Premissas (evidência do estado atual)

- **11D (entregue):** a tool `run_pytest` existe
  (`app/tools/run_pytest.py`) — subprocesso estruturado **sem shell**,
  permissão `TERMINAL` + checkpoint obrigatório, parâmetros
  `path`/`k`/`maxfail`/`timeout_s` (defaults: `"tests"`, `maxfail=1`,
  `timeout=60s`). Registro **condicional** em
  `ToolsController.build_registry` (`app/tools/control.py` L671–685):
  só quando o terminal está habilitado. O catálogo do Planner é
  condicional no mesmo gatilho (`build_catalog(include_terminal=…)`,
  `app/planner/catalog.py` L188) — o Planner só "conhece" `run_pytest`
  quando o terminal está ligado.
- **11E (entregue):** verificação real **opt-in** —
  `enable_verification("pytest_result")` / `disable_verification()` /
  property `verification_enabled` (`app/tools/control.py` L502–528);
  `PytestResultVerifier` é **interpretativo** (não executa nada);
  wiring em `run_plan` via `verifier=self._verifier` (L731). Verde ⇒
  `verified=True`; vermelho ⇒ task `REJECTED` + plano `FAILED` com
  evidência.
- **`max_tasks=12`** (`PlannerLimits`, `app/planner/planner.py` L171)
  é aplicado **apenas** em `Planner._parse_plan` (L598–601). O
  `PlanExecutor._validate_plan` (`app/executor/executor.py` L278)
  **não** checa contagem de tarefas (só READY, não vazio, deps
  existentes, acíclico). Consequência: uma task anexada pelo sistema
  passa pelo executor sem erro — a proteção contra estouro precisa
  vir da regra de anexo (§5).
- **`Plan` é dataclass frozen** (`app/planner/models.py` L115):
  qualquer ajuste de plano exige `dataclasses.replace(plan, tasks=…)`.
- **Funil real de execução:** `ToolCallingBridge.process`
  (`app/core/bridge.py` L126) → `ToolsController.run_plan`
  (`app/tools/control.py` L686) → `build_registry()` (L696–697) →
  ramo `CorrectionEngine` (L715) ou ramo `PlanExecutor` (L731) →
  `_drive()` (L744).
- **Finalização de plano:** `Planner.create_tool_plan` →
  `_finalize(READY)` (`app/planner/planner.py` L447). **Não existe
  hook de pós-processamento de plano antes da execução** —
  `_refine_plan` (L761) é opt-in e seu contrato proíbe adicionar/
  remover tarefas.
- **Tools WRITE do catálogo:** `write_file`, `create_file`,
  `delete_file`, `edit_file` (`app/planner/catalog.py` L66–134).
- **9B (persistência):** `ToolsController._final` grava o bundle da
  execução a partir de `self._plan` em estado terminal — por isso o
  anexo deve atualizar `self._plan` (§6).

## 3. Objetivo (MVP)

- **Auto-anexo:** se (a) terminal habilitado **AND** (b) verificação
  11E habilitada **AND** (c) o plano contém ao menos 1 task WRITE
  (§5), então `run_plan` anexa **exatamente 1** task final
  `run_pytest` com `parameters={"path": "tests"}` antes de começar a
  executar.
- A task anexada **depende de todas as tasks anteriores** (executa
  por último).
- Se o pytest falhar: o plano falha **com evidência** — já coberto
  pela 11E (task `REJECTED`, `verified=False`, plano `FAILED`); a 11F
  só garante que a task exista.
- Sem as condições: o plano executa **inalterado** (zero diferença de
  comportamento vs. estado atual).

**Não-objetivos do MVP (fora de escopo):** repair-loop;
auto-replanning; alterar a allowlist de `run_command`; criar nova
permissão; mudança de UI (UX fica em §8); anexar em planos sem
WRITE; anexo quando a verificação 11E está desligada.

## 4. Princípios de segurança (normativo para a implementação)

1. **Não liberar `python`/`pytest` no `run_command`** — a allowlist do
   terminal permanece inalterada; pytest só roda via `run_pytest`
   (subprocesso estruturado, sem shell, saída limitada).
2. **Não executar pytest "escondido"** — o anexo é SEMPRE uma task
   visível do plano, sujeita a permissão `TERMINAL` + checkpoint
   obrigatório (aprovação do usuário). Nunca efeito colateral
   interno de outra task.
3. **Não exceder `max_tasks` silenciosamente** — plano com 12/12
   tasks + necessidade de anexo ⇒ falha **antes de executar** (§5).
4. **Não anexar se `run_pytest` já estiver no plano** (idempotência —
   1 run_pytest por plano, LLM ou sistema).
5. **Nunca executar parcialmente** — qualquer falha do anexo ⇒ nada
   executa, com motivo claro.
6. O anexo **não altera** permissões, sandbox, auditoria nem políticas
   de checkpoint de nenhuma outra task.

## 5. Regras / guardrails (decisão explícita)

- **Detecção de WRITE (MVP):** a task conta como WRITE quando
  `tool ∈ {write_file, create_file, delete_file, edit_file}`.
  (`run_command` — aberto em §8; MVP: **não** conta.)
- **Limite de tasks:** se `len(tasks) == 12` **e** o anexo é
  necessário ⇒ `run_plan` **FALHA ANTES DE EXECUTAR** com mensagem
  clara (executor/engine não são montados; nenhuma task roda). O
  mecanismo exato (exceção controlada × relatório `FAILED`) é detalhe
  de implementação; o comportamento observável é invariante: **nada
  executa** + motivo claro.
- **Parâmetros (MVP):** `{"path": "tests"}` — estáticos, **sem
  referências de dataflow** (`${Tn.data.…}`) ⇒ sem problema de
  consistência de dataflow no parse/executor.
- **ID do anexo:** `T{n+1}` (n = nº de tasks atuais); regra
  defensiva: se o id estiver ocupado, incrementar até achar um livre.
- **Dependencies:** `tuple(t.id for t in tasks)` (todas as tasks
  anteriores) — mantém o DAG acíclico (a nova task só tem arestas de
  saída); profundidade da cadeia +1 no máximo (a checagem de
  profundidade do Planner já rodou no parse; o executor não checa
  profundidade — documentado e aceito no MVP).
- **Order:** `n+1`.
- **Descrição:** texto explícito de que a task é automática, ex.:
  `"Verificação: rodar pytest (task anexada automaticamente — 11F)"`.
- **Duplicidade:** se existir qualquer task com
  `tool == "run_pytest"` ⇒ **não** anexar.
- **Ramos:** o anexo ocorre **antes dos dois ramos** (CorrectionEngine
  e PlanExecutor) — com correções ativas, o motor recebe o plano já
  ajustado.
- **Persistência 9B:** `self._plan` é atualizado com o plano ajustado
  para o bundle refletir o que efetivamente executou.

## 6. Integração proposta (Opção B — controller)

- **Local:** `app/tools/control.py`, `ToolsController.run_plan`
  (L686), **após** `build_registry()` (L696–697) e **antes** dos ramos
  (L715/L731).
- **Helper puro:** função isolada, ex.:
  `attach_pytest_task(plan: Plan, *, can_attach: bool) -> Plan`
  (local de alocação a decidir na implementação — módulo próprio
  `app/tools/` ou dentro de `control.py`) — retorna o plano inalterado
  ou `replace(plan, tasks=…)`; sem efeito colateral; testável sozinha.
- **Condição (short-circuit):**
  `can_attach = (self._terminal_policy is not None)
  and self.verification_enabled
  and has_write_task(plan)
  and not has_pytest_task(plan)`.
- **Falha de limite:** `can_attach AND len(plan.tasks) >= 12` ⇒ falha
  controlada antes de executar (§5).
- **Por que Opção B (e não no Planner):** o controller tem as
  condições de runtime (`terminal_policy`, `verification_enabled`) que
  o Planner estruturalmente não tem; é o funil único da execução real
  (cobre planos montados programaticamente); e o
  `PlanExecutor._validate_plan` revalida o plano ajustado (READY/deps/
  acíclico) de graça. **Custo aceito:** o plano é ajustado "em voo" —
  o log da bridge antes de executar mostra N tasks (UX: §8).

## 7. Plano de testes (quando implementada)

**Unit — `attach_pytest_task(plan)`:**

- não anexa quando: plano sem WRITE; plano já contém `run_pytest`;
  `can_attach=False` (terminal off; verification off — variantes).
- anexa quando: plano com WRITE + `can_attach=True` ⇒ task final
  `T{n+1}`, `tool="run_pytest"`, `parameters={"path": "tests"}`,
  `dependencies` = todas as anteriores, `order = n+1`.
- `len(tasks) == 12` + anexo necessário ⇒ falha controlada
  (nada executa).
- sem anexo ⇒ o plano volta **inalterado** (igualdade/identidade,
  sem efeito colateral).

**Integração — `ToolsController.run_plan`:**

- plano com WRITE + `enable_verification("pytest_result")` + terminal
  on ⇒ o relatório contém a task extra **no final** e a execução
  **pausa no checkpoint** da task (aprovação exigida).
- pytest verde ⇒ plano `COMPLETED` com a task final
  `verified=True`; pytest vermelho ⇒ plano `FAILED` com evidência
  (11E).
- `len(tasks) == 12` + anexo necessário ⇒ falha **antes de executar**
  (motivo claro; zero chamadas de ferramenta).
- sem verificação (default) ⇒ zero diferença de comportamento
  (nenhuma task anexada).

**Regressão:** suíte completa — baseline vigente 977/5/0 (982) +
novos testes.

## 8. Questões abertas (TBD) — decisões (2026-08-31)

**RESOLVIDO / IMPLEMENTADO (entregue):**

- **Gatilhos e idempotência** — implementado em `_needs_auto_pytest`
  (terminal habilitado + verificação 11E habilitada + plano com
  WRITE; não anexa se `run_pytest` já estiver no plano).
- **Guardrail 12/12** — implementado: falha **antes de executar** com
  `FAILED` e tudo `SKIPPED`, sem nenhuma execução (provado em teste).
- **Ponto de integração (Opção B)** — implementado em
  `ToolsController.run_plan`, antes dos dois ramos, com persistência
  9B via `self._plan`.
- **Ramificação de correções** — anexo feito uma vez no `run_plan`;
  ciclos do CorrectionEngine **não** re-anexam (conforme MVP).

**Ainda aberto (evoluções futuras — NÃO AUTORIZADAS):**

- **`run_command` conta como "mutável"?** MVP: não (detecção restrita
  às 4 tools WRITE). Comandos allowlisted podem modificar estado —
  reavaliar em fase futura.
- **`path` padrão e workspace sem `tests/`:** o default `"tests"`
  existe no repo atual; em workspace sem `tests/` o `run_pytest`
  falha com evidência clara (comportamento já coberto pela tool).
  Definir se o path será configurável em fase futura.
- **UX:** como exibir "task anexada automaticamente" (log da bridge
  mostra N tasks antes de executar; UI de checkpoint/relatório).
- **Metadado:** registrar o anexo em `analysis` do plano
  (informativo) — opcional.
- **Parâmetros ampliados:** `-k`/`maxfail`/`timeout_s` na task anexada
  (MVP: apenas `path`).

## Histórico do documento

- **2026-08-31 — sincronizado com a implementação entregue:** status
  DRAFT / em discussão → IMPLEMENTADA + TESTADA; adicionada seção
  "Evidências (implementação e testes)"; §8 reestruturado
  (RESOLVIDO / IMPLEMENTADO × ainda aberto); suíte atualizada para
  980/5/0 (985 coletados).
- **2026-08-31 — DRAFT criado** (COMANDO 039, parte 2/3), com base no
  mapeamento read-only da parte 1/3 (pontos de validação/limite/handoff
  e ausência de hooks pré-execução). 11F **planejada, não
  implementada**.
