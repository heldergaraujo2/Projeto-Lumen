# SPEC — Fase 11D: Build/Test estruturado + verificação real

> **Status: IMPLEMENTADA + TESTADA (MVP entregue em 2026-08-31).** A
> Fase 11D foi autorizada em etapas e o MVP descrito em §4/§5 está
> entregue e coberto por testes — ver "Evidências (implementação e
> testes)" abaixo.

- **Base da discussão:** `0.6.8` + fases internas 9A–11C concluídas.
- **Suíte vigente na data deste draft:** 967 passed / 5 skipped / 0 failed
  (972 coletados).
- **Leituras complementares:** `docs/ROADMAP.md` (trilha 0.7),
  `docs/SPEC-11C-EDIT_FILE.md` (padrão de entrega por passos),
  `docs/ARCHITECTURE.md` (terminal/policy), `app/tools/terminal.py`.

## Evidências (implementação e testes) — MVP entregue em 2026-08-31

**Implementação:**

- `app/tools/run_pytest.py` — `RunPytestTool` (permissão **TERMINAL**):
  subprocesso `[sys.executable, -m pytest …]` **sem shell**; `path`
  relativo confinado no `WorkspaceSandbox` (absoluto/`..` rejeitados);
  `-k` com charset estrito; `maxfail` 1..10; `timeout_s` 10..600
  (default 60); saída combinada com teto de 200 KiB + flag
  `truncated`; `summary_line`, `output_head`/`output_tail`; caches fora
  do repo (`-p no:cacheprovider`, `--basetemp` e pycache em
  temporário do sistema). `ok=False` **só** para falha da tool — se o
  pytest rodou, a evidência vai em `exit_code`/`summary_line`.
- `app/tools/control.py` — registro condicional em
  `ToolsController.build_registry` **somente com o terminal
  habilitado** (mesma condição de `run_command`).
- `app/tools/terminal.py` — `PrevalidatedTerminalCheckpoints` inclui
  `run_pytest`: **checkpoint obrigatório antes de executar**, sem
  aprovação decorativa (só tasks viáveis pausam — inputs válidos +
  path no sandbox); recusa ⇒ tarefa SKIPPED, nada executa.
- `app/planner/catalog.py` — `ToolSpec("run_pytest", …,
  terminal=True)` no Planner Catalog **somente quando o terminal está
  habilitado** (`include_terminal=True`).

**Testes (novos/ajustados na 11D):**

- `tests/test_terminal_integration.py` — 2 testes de integração
  (checkpoint aprovado executa a mini-suite real e devolve
  `exit_code==0`; recusado ⇒ SKIPPED sem executar) + guard anti-futuro
  atualizado.
- `tests/test_planner_tools.py` — catálogo condicional omite/inclui
  `run_pytest` com `include_terminal` + 4 casos na matriz de validação
  de protocolo + `spec_for`.
- `tests/test_agent_bridge.py`, `tests/test_chat_multitask.py`,
  `tests/test_filesystem_integration.py` — guards AST atualizados:
  `subprocess`/`shutil`/`Popen` permitidos **apenas** em
  `app/tools/terminal.py` + `app/tools/run_pytest.py`.

**Baseline atual (regressão completa, 2026-08-31):** 978 coletados —
**973 passed / 5 skipped / 0 failed** (5 skips ambientais; registro
anterior, pós-11C: 967/5/0 — 972 coletados — preservado).

## 1. Problema e motivação

Hoje a **verificação de trabalho é majoritariamente simulada**:

- As ferramentas de escrita (`create_file`, `write_file`, `edit_file`)
  confirmam bytes gravados, mas nada **executa** o resultado.
- A CorrectionEngine e os fluxos de reparo operam sobre diff/heurística,
  sem evidência de execução real.
- Os testes do próprio Lumen só rodam **manualmente** (`python -m pytest`)
  pelo usuário, fora da coleira do agente — o agente não pode produzir
  evidência de verificação.

Para a trilha Coding Agent (0.7) fazer sentido, o agente precisa de
**verificação real com evidência**: rodar a suíte de testes do workspace
de forma controlada e receber **output estruturado** (exit code, duração,
resumo, primeiros erros) — não texto bruto gigante.

## 2. Não-objetivos (fora de escopo nesta fase)

- **NÃO** liberar interpretador/shell genérico (F17 permanente).
- **NÃO** alterar `FORBIDDEN_COMMANDS`, allowlist ou `TerminalPolicy`.
- **NÃO** introduzir auto-replanning (R4 permanece: sem re-planejamento
  automático; correção só sob aprovação explícita).
- **NÃO** rodar builds de terceiros/multi-linguagem (make/cargo/npm…) —
  escopo inicial: **pytest** no workspace (ver §8.3).
- **NÃO** criar CI externo, watchers ou processos de longo prazo.

## 3. Restrição de segurança atual (e evidência)

`run_command` **não pode** executar pytest/python — por design:

- `app/tools/terminal.py` define `FORBIDDEN_COMMANDS` (~L88): inclui
  `python`, `python3`, `py`, `pip` (~L99) e ferramentas de build
  (`make`, `cmake`, `dotnet`, `cargo`, `go`… ~L104). Entradas
  allowlistadas **jamais** podem colidir com a denylist
  (`CommandNotAllowlistedError` / validação de `make_entry`).
- A allowlist é **runtime e começa vazia** (`TerminalPolicy`); não existe
  caminho legítimo para allowlistar `python` — e **não deve existir**:
  interpretadores rodam código arbitrário.

**Portanto: 11D NÃO é "habilitar python na allowlist".** A proposta segue
o padrão do projeto — **capacidade específica, não interpretador
genérico**: uma tool dedicada que encapsula *um* runner conhecido
(pytest) com parâmetros fechados, sandbox, checkpoint e audit.

## 4. Proposta de solução (base do MVP implementado)

> **Nota de implementação (2026-08-31):** o MVP seguiu esta proposta
> com as decisões do §8 e estas diferenças factuais: `path` default
> `tests` (não `.`); `maxfail` 1..10 (não 1–50); sem parâmetro `quiet`
> (sempre `-q`); timeout default 60 s (não 120); sem `first_failures`
> ainda (item 4 do §8 — evolução futura). A fonte de verdade é o
> código (`app/tools/run_pytest.py`).

Nova tool **`run_pytest`** (nome alternativo: `run_tests` — definido
como `run_pytest` no §8.6):

a) **Execução controlada** — subprocesso dedicado
   (`[sys.executable, "-m", "pytest", …]`; argv direto, **sem shell**),
   nunca via `run_command`/TerminalPolicy. Detalhes: §8.2.

b) **Parâmetros allowlisted** (conjunto fechado, tudo opcional exceto
   `path`):
   - `path`: **relativo** ao workspace, resolvido e confinado (mesmo
     padrão das tools de filesystem); default `.` (o workspace).
   - `keyword` (`-k`): expressão simples validada (sem `;`, `(`, `)`
     …?) — TBD o quanto liberar (§8.7).
   - `maxfail`: int 1–50 (default 1? TBD).
   - `quiet`: bool (default `true` → `-q`).
   - **Proibido**: `-p <plugin>`, `--rootdir` arbitrário, `conftest`
     override, `PYTHONPATH`/env arbitrário, opções de escrita
     (`--cache`, `--basetemp` dentro do repo) — fixados pela tool.

c) **Timeout próprio** — o teto de 60 s do terminal é insuficiente para
   suítes reais; a tool teria `default_timeout_s` e `max_timeout_s`
   próprios (ex.: default 120 s, teto 600 s) — **TBD** (§8.1).

d) **Output estruturado** (payload da tool):
   - `exit_code`, `duration_s`, `timed_out`;
   - `summary`: `{passed, failed, skipped, deselected?, errors}` parseado
     da linha final do pytest;
   - `first_failures`: primeiros **N** erros (N=3?) com **teto de bytes
     por erro** (ex.: 2.000 B) — sem despejar log inteiro (§8.4);
   - saída bruta truncada com teto total (ex.: 64 KiB) apenas para audit.

e) **Checkpoint SEMPRE** — execução de código é intrinsecamente
   destrutiva/risco: `requires_approval=True` incondicional (mesmo com
   "testes verdes" não há isenção — TBD se path de leitura poderia ser
   isento; default NÃO).

f) **Audit sem secrets** — evento de audit com comando argv, cwd, exit
   code, duração e resumo; saída passa pelo mesmo sanitizador de secrets
   do terminal (`_SECRET_MARKERS`); env do subprocesso **mínimo e
   fixado** (ver §5).

g) **Isolamento de caches** — nada de sujeira no workspace alvo:
   - `PYTHONDONTWRITEBYTECODE=1` **e** `PYTHONPYCACHEPREFIX` apontando
     para temporário fora do repo;
   - `-p no:cacheprovider` (sem `.pytest_cache`);
   - `--basetemp` em temporário fora do repo (TBD: tmpdirs do próprio
     pytest já são fora do cwd — confirmar).

## 5. Segurança (normativo para a futura implementação)

- **Permissão:** reutilizar `TERMINAL` **ou** criar permissão nova
  (`BUILD`/`EXEC_TESTS`) — **TBD** (§8.5). Em ambos os casos a tool é
  registrada como destrutiva ⇒ checkpoint obrigatório.
- **Sandbox/cwd:** cwd do subprocesso = workspace autorizado
  (`WorkspaceSandbox`/`MultiWorkspaceSandbox`); paths do usuário só
  relativos e resolvidos contra o sandbox; fora ⇒ erro controlado.
- **Bloqueio de paths:** qualquer caminho absoluto/`..`/symlink-escape
  no `path` ⇒ rejeição antes de spawnar processo.
- **Limites de output:** tetos de bytes (resumo + failures + bruto)
  definidos na tool; overflow ⇒ truncamento marcado
  (`truncated: true`), nunca silencioso.
- **Ambiente/segredos:** subprocesso herda **env sanitizado mínimo**
  (PATH, SYSTEMROOT/TEMP necessários no Windows; **sem** vars de
  API keys/keyring — lista allowlistada de vars, TBD); nenhum segredo
  em argv (sanitização igual à do terminal).
- **Plugins:** proposta `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` — evita que
  plugins instalados no máquina do usuário mudem semântica/vazem dados
  (TBD: confirmar que a suíte Lumen não depende de plugins de terceiros).
- **Rede:** permanece inexistente para ferramentas; suítes-alvo devem
  ser offline (mesma regra da suíte Lumen).

## 6. Integração com verificação

- Planos poderão incluir etapa de **verificação real** após tarefas de
  escrita (ex.: `edit_file` → `run_pytest -k test_tool_edit_file`) —
  cada execução passa pelo checkpoint normalmente.
- **Sem auto-replanning:** resultado vermelho NÃO dispara re-planejamento
  automático; o relatório estruturado volta ao usuário/controlador e a
  correção (se pedida) é um **novo plano sob aprovação** (R4/F17).
- Entrada no **Planner Catalog**: **FEITA na mesma fase** (ritual
  11B/11C: `ToolSpec` com `terminal=True` + contratos de teste
  atualizados; ver "Evidências") — `run_pytest` só aparece com o
  terminal habilitado.

## 7. Plano de testes da própria 11D (quando implementada)

- **Unitários da tool:** validação de args (conjunto fechado; `maxfail`
  bounds; `keyword` seguro); confinamento de path (absoluto/`..`/fora ⇒
  erro); clamp de timeout; parse do summary (saída verde/vermelha/sem
  testes/timeout); truncamento marcado; env sanitizado (assert: sem
  vars de segredo).
- **Integração:** subset rápido real (ex.: `tests/test_tool_edit_file.py`)
  verde; **falha controlada** (fixture que falha ⇒ exit≠0, summary
  correto, `first_failures` preenchido); timeout forçado (suíte dorme ⇒
  `timed_out` e nada escrito no repo); caches ausentes no workspace
  após execução.
- **Contratos:** contagens de tools atualizadas (se registrada) +
  regressão completa com nova baseline explícita.

## 8. Questões abertas (TBD) — decisões da implementação (2026-08-31)

1. **Timeout máximo** — **RESOLVIDO/IMPLEMENTADO:** clamp 10..600 s,
   default 60 s.
2. **Subprocess vs pytest in-process** — **RESOLVIDO/IMPLEMENTADO:**
   subprocess isolado (`[sys.executable, -m pytest]`, sem shell) —
   crash/timeout não derrubam o agente.
3. **Escopo** — **RESOLVIDO/IMPLEMENTADO:** qualquer workspace do
   sandbox, via `path` relativo confinado no `WorkspaceSandbox`
   (suítes devem ser offline).
4. **Report de falhas sem log gigante** — **parcialmente
   implementado:** teto de 200 KiB + `truncated`, `summary_line`,
   `output_head`/`output_tail` (4 KiB cada). **Ainda aberto
   (evolução):** `first_failures` estruturado (N erros com teto de
   bytes por erro) e tracebacks completos sob demanda (segunda
   chamada).
5. **Permissão** — **RESOLVIDO/IMPLEMENTADO:** reutiliza `TERMINAL`
   (sem permissão nova).
6. **Nome da tool** — **RESOLVIDO/IMPLEMENTADO:** `run_pytest`
   (explícito).
7. **`-k` liberar quanto?** — **RESOLVIDO/IMPLEMENTADO:** charset
   estrito `[A-Za-z0-9_ .-]`, até 100 chars (sem expressões
   compostas).
8. **Planner Catalog** — **RESOLVIDO/IMPLEMENTADO:** entrou na mesma
   fase (`ToolSpec` com `terminal=True`; visível somente com terminal
   habilitado).
9. **`--basetemp`/caches** — **RESOLVIDO/IMPLEMENTADO:** fora do repo
   (`-p no:cacheprovider`, `--basetemp` em temporário do sistema,
   `PYTHONPYCACHEPREFIX` fora do workspace).
10. **`requires_approval`** — **RESOLVIDO/IMPLEMENTADO:** checkpoint
    sempre, sem isenção (default conservador).

**Ainda aberto (futuro, NÃO AUTORIZADO):** report de falhas rico
(item 4), endurecimento de env (allowlist estendida de vars /
`PYTEST_DISABLE_PLUGIN_AUTOLOAD` — §5), verificação real completa
integrada aos planos (§6) e repair-loop (R4/F17 preservados).

---

## Histórico do documento

- 2026-08-31 — draft criado para discussão (status original: "DRAFT /
  EM DISCUSSÃO — 11D PLANEJADA, NÃO AUTORIZADA, NÃO IMPLEMENTADA";
  suíte vigente na época: 967/5/0 — 972 coletados).
- 2026-08-31 — MVP implementado e testado em etapas (tool, registro
  condicional, checkpoint, Planner Catalog, testes, guards AST, doc
  sync) e baseline atualizada para 973/5/0 (978 coletados).

---

*Única fonte de verdade é o código — ver "Evidências (implementação e
testes)" acima. Esta spec descreve o MVP entregue; itens marcados
"aberto" são futuros e não autorizados.*
