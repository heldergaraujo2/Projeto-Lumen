# SPEC — Fase 11D: Build/Test estruturado + verificação real

> **Status: DRAFT / EM DISCUSSÃO — 11D PLANEJADA, NÃO AUTORIZADA,
> NÃO IMPLEMENTADA.** Este documento é uma proposta para discussão.
> Nada aqui foi implementado; nenhuma autorização de execução foi dada.
> A Fase 11D só começa por comando explícito do proprietário do projeto.

- **Base da discussão:** `0.6.8` + fases internas 9A–11C concluídas.
- **Suíte vigente na data deste draft:** 967 passed / 5 skipped / 0 failed
  (972 coletados).
- **Leituras complementares:** `docs/ROADMAP.md` (trilha 0.7),
  `docs/SPEC-11C-EDIT_FILE.md` (padrão de entrega por passos),
  `docs/ARCHITECTURE.md` (terminal/policy), `app/tools/terminal.py`.

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

## 4. Proposta de solução (DRAFT)

Nova tool **`run_pytest`** (nome alternativo: `run_tests` — TBD, §8.6):

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
- Entrada no **Planner Catalog**: TBD — se entrar, segue o ritual 11B/11C
  (ToolSpec + contratos atualizados) **na mesma fase** (§8.8).

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

## 8. Questões abertas (TBD — decidir antes da implementação)

1. **Timeout máximo** adequado (600 s? por projeto?) e default (120 s?).
2. **Subprocess vs pytest in-process** — subprocess isolado (preferido:
   crash/timeout não derrubam o agente) vs in-process (mais rápido,
   mas compartilha estado/importações).
3. **Escopo:** só o repo Lumen vs qualquer workspace do sandbox
   (proposta: qualquer workspace confinado; suítes devem ser offline).
4. **Report de falhas sem log gigante** — N de failures, bytes por
   failure, incluir tracebacks completos sob demanda (segunda chamada)?
5. **Permissão:** `TERMINAL` nova-entrada vs permissão dedicada
   (`BUILD`) — impacta Settings/Controller/grants.
6. **Nome da tool:** `run_pytest` (explícito) vs `run_tests` (genérico
   p/ futuro build) — premature-generalization vs clareza.
7. **`-k` liberar quanto?** só `[A-Za-z0-9_ ]`? expressão completa?
8. **Planner Catalog** na mesma fase ou adiar (como quase ocorreu em 11B)?
9. `--basetemp` dentro ou fora do repo (e no Windows do usuário real)?
10. Se `requires_approval` pode ser `False` para algum caso (default NÃO).

---

*Rascunho criado em 2026-08-31 para discussão. Única fonte de verdade é o
código; enquanto 11D não for autorizada, este documento não descreve nada
existente — e não autoriza nada.*
