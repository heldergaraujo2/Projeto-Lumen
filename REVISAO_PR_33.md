# Revisão crítica do PR #33 — 2026-10-08

**Estado final: PR #33 merged em `master` após cinco checks verdes.**
Commit de merge: `7f7f58ddc79abd9f5096145e7fe8c26609aa2c16`.
O repositório usa `master` como branch padrão; `main` não existe. O
proprietário autorizou explicitamente o destino `master`. Os parágrafos
sobre bloqueios anteriores abaixo documentam a investigação em ordem
cronológica; o resultado pós-merge está em §4–6.

## 1. Revisão final do diff

Comparei o PR com `origin/master` (`git diff --find-renames origin/master...HEAD`, 163 arquivos), distinguindo pacotes movidos para `archive/` de código vivo. Verifiquei diffs de código/configuração/documentação, varri linhas adicionadas à procura de chaves/segredos e TODO/FIXME/HACK, executei `ruff check --select F401` sobre os pacotes novos e validei JSON/whitespace com `python -m json.tool` e `git diff --check`.

- **Credenciais hardcoded reais:** nenhuma encontrada. Strings `tvly-SECRET123`, `sk-...` etc. são *fixtures* dos testes; `.env.example` tem valores vazios e o `.env` real é ignorado pelo Git.
- **Import não utilizado:** `typing.Iterator` em `app/research/client.py`, removido.
- **TODOs esquecidos nos novos pacotes:** nenhum encontrado. Avisos de validação manual no Unreal e PowerShell continuam explícitos.
- **Falha grave de segurança:** `app/tools/control.py:tool_protocol()` reconstruía as `ToolDefinition` do Unreal e descartava `destructive=True` e `metadata["validation"]`. Assim, `tools/list` podia mostrar todas as `unreal_*` sem `--allow-write`. Além disso, operações Unreal não tinham política de checkpoint: mesmo com WRITE, podiam atingir o editor sem aprovação. Corrigido: definição original da ferramenta preservada; `_UnrealCheckpoints` protege as quatro operações mutáveis (set_property, call_function, create_blueprint_class, add_component); teste confirma **zero chamadas HTTP antes da aprovação e após recusa**. O sandbox de caminhos locais não restringe objetos do Unreal; o gate é permissão WRITE + checkpoint + endpoint local. `run_command`/`run_pytest` também foram classificados como destrutivos para filtragem no MCP.
- **Inconsistência de permissão:** `LUMEN_MCP_ALLOW_WRITE=true` expunha escrita, mas não concedia WRITE nem tornava o workspace gravável em `app/mcp_server/__main__.py`. Corrigido e coberto por subprocesso MCP real.
- **Inconsistência de integração:** o entry point MCP não tinha ativação explícita das tools de pesquisa/Unreal, embora o guia mandasse chamá-las. Incluídas `--enable-web-search` e `--enable-unreal-bridge`, com teste `tools/list` em subprocesso real; o padrão continua fail-closed.
- **`.env` prometido mas não lido:** `app/research/client.py` e `app/unreal_bridge/config.py` liam só `os.environ`; corrigido para usar o parser existente de `.env`, com precedência do ambiente real. O parser em `app/config/settings.py` registrava linhas malformadas literalmente no log (risco de revelar uma chave); agora omite valores, com teste.
- **Documentação imprecisa:** README/TESTE_LOCAL tinham contagens antigas; `bootstrap.ps1` dizia "iniciar MCP" mas só imprime a configuração (correto para servidor stdio lançado pelo cliente). Corrigidas mensagens/script/docs. O processo MCP separado **não compartilha a UI de aprovação**: sem `--auto-approve`, não é possível concluir uma escrita por esse cliente; com ele, a operação ocorre sem confirmação interativa. O `ApprovalGate` do plano continua separado. Também esclarecido que não existe ainda um orquestrador único que encadeie pesquisa → aprovação → UBT → Unreal numa solicitação de chat; simular esse fluxo seria enganoso.

As correções e seus testes estão na branch do PR; não houve mudança de dependências de runtime. A execução real do PowerShell e do Unreal continua pendente no computador do usuário.

## 2. Conflitos

`git fetch origin master` e `git merge-base HEAD origin/master` retornaram o mesmo commit-base `19764fce0be9ed1080a77df439eb699d9e54a42a`. O GitHub reportou `mergeable=MERGEABLE` para o PR #33 contra `master`: **nenhum conflito com a branch-base real**. Após o push da revisão, `gh pr checks 33` mostrou cinco jobs **pendentes** (`test`, `validate`, `validation` Linux/Windows e `windows`); ainda não há confirmação verde de CI. Antes de qualquer merge autorizado, é necessário confirmar que terminaram sem falhas. `git ls-remote --heads origin main master` retornou **somente `master`**, e `gh repo view` confirmou `master` como branch padrão. Não há como verificar conflitos com `main` inexistente.

## 3. Suíte completa pré-merge

Comando: `/tmp/venv/bin/python -m pytest -q --no-header` na raiz.

**1375 passed / 7 skipped / 0 failed (11,99 s).** Os 7 skips continuam sendo apenas `tkinter` ausente no sandbox. Diferença em relação ao relatório original (**1364 / 7 / 0**): **+11 testes de regressão desta revisão** — 6 em `tests/test_mcp_server.py`, 3 em `tests/test_unreal_bridge.py`, 2 em `tests/test_research_client.py`. Nenhum teste antigo foi removido ou passou a falhar. `RELATORIO_FINAL.md`, `TESTE_LOCAL.md`, `README.md` e `LUMEN_STATE.md` registram agora a nova contagem; os números por fase no relatório permanecem marcados como históricos.

## 4. Merge — CONCLUÍDO

Na revisão final do commit `a2991d9` do PR #33, os cinco checks estavam
**passando**: `test`, `validate`, `validation (ubuntu-latest)`,
`validation (windows-latest)` e `windows`. O GitHub reportou
`mergeable=MERGEABLE`, `mergeStateStatus=CLEAN`. Com a autorização do
proprietário, `gh pr merge 33 --merge` incorporou o PR a `master` no commit
**`7f7f58ddc79abd9f5096145e7fe8c26609aa2c16`** (pais:
`19764fc` e `a2991d9`). Sem push direto para `master`.

## 5. Verificação pós-merge — CONCLUÍDA

A suíte foi executada **na árvore exata do commit de merge de
`origin/master`**, extraída com `git archive` para diretório temporário
(sem trocar a branch fixa desta sessão):

```text
PYTHONIOENCODING=cp1252 /tmp/venv/bin/python -m pytest -q --no-header
1375 passed, 7 skipped in 13.97s
```

Os cinco arquivos estão presentes no tree de `master`:
`bootstrap.ps1`, `TESTE_LOCAL.md`, `mcp_config.json` (JSON válido),
`RELATORIO_FINAL.md` e `PESQUISA_MCP_EXISTENTES.md`.

`git log --oneline -10 origin/master` (a referência remota local da branch
`master`, sem checkout):

```text
7f7f58d Merge pull request #33 from heldergaraujo2/arena/59a23416-projeto-lumen
a2991d9 ci: remove gate F27 de modulo arquivado no Windows
36f024e corrige encoding UTF-8 no cliente subprocesso de testes MCP
4ae593d corrige MCP stdio UTF-8 sob codepage Windows e testa subprocesso
ae43590 revisao: registra checks pendentes e perfis MCP distintos
0ab781c revisao final: corrige gates MCP/Unreal e alinha documentacao
69c24ee entrega final: relatorio
ec96415 fase 6: bootstrap automatizado para Windows
05f205b fase 5: documentação e guia de teste local
70c1a63 fase 4: ponte com Unreal via Remote Control API
```

As fases mais antigas não cabem nas dez linhas por causa dos commits de
revisão; os oito commits das fases (`a69c221`, `4a47ea2`, `5817b69`,
`b7f37f0`, `53aced1`, `70c1a63`, `05f205b`, `ec96415`) foram confirmados
como **ancestrais** de `origin/master` com `git merge-base --is-ancestor`.

## 6. Resumo para teste local

[`PRONTO_PARA_TESTE.md`](PRONTO_PARA_TESTE.md) traz hash real do merge,
comando PowerShell para um clone de `master`, link a `TESTE_LOCAL.md` §1 e
os 24 itens de validação manual ordenados por precedência e risco.

## Adendo — falha do check Windows em `Tests`

O check `windows` no commit `ae43590` falhou em `Tests` (os outros 4
passaram). O log bruto do GitHub não pôde ser baixado neste ambiente: o
redirecionamento da API para o armazenamento de logs termina em EOF.
Portanto, **não se afirma ter visto o traceback do CI**.

Foi reproduzido localmente um erro da mesma classe, com o entry point real e
`PYTHONIOENCODING=cp1252`: chamada MCP `create_file` sem auto-aprovação →
`UnicodeEncodeError: 'charmap' codec can't encode character '\u23f8'` em
`app/mcp_server/stdio.py:108`, exit code 1, sem escrita no workspace.
`app/mcp_server/__main__.py` agora reconfigura `sys.stdin`, `sys.stdout` e
`sys.stderr` para UTF-8 **no começo de `main()`**, antes de qualquer saída.
Dois testes de regressão sob `cp1252` comprovam saída UTF-8 com checkpoint e
entrada UTF-8 com acentos; a suíte completa passou com **1375 passed / 7
skipped / 0 failed**. O check Windows **precisa ficar verde no commit novo**
antes de qualquer merge. A etapa F27 no workflow Windows continua pendente
de execução após `Tests` e importa um módulo movido para `archive/`: será
necessário observar o check real; nenhuma correção especulativa foi feita.

## Adendo — encoding no helper de subprocesso (Windows)

Após o conserto de produção, o check `windows` do commit `4ae593d`
**continuou falhando em `Tests`**; os outros quatro passaram. O download
do traceback de CI ainda é bloqueado pelo redirecionamento do GitHub,
então **não se afirma conhecer a lista exata de testes que falharam**.
Uma segunda causa foi identificada no helper `TestRealSubprocess._run()`:
`subprocess.run(text=True)` sem `encoding` usa o locale do processo **pai**
(cp1252 no Windows), tanto para `input=payload` quanto para `stdout`/`stderr`.
Agora usa `encoding="utf-8", errors="strict"`. Um novo teste força
`subprocess._text_encoding` do pai a cp1252 e o filho a
`PYTHONIOENCODING=cp1252`, verificando roundtrip MCP com nome e conteúdo
acentuados. Varredura AST do projeto: outros dois `subprocess.Popen`
(`app/tools/terminal.py`, `app/tools/run_pytest.py`) operam em **bytes**,
sem `text=True`, e não exigem conversão de encoding. `bootstrap.ps1`
usa `Start-Process` do PowerShell, não `subprocess` Python.

Suíte **com `PYTHONIOENCODING=cp1252` no processo pytest pai**:
**1375 passed / 7 skipped / 0 failed**. A causa do check Windows só será
considerada eliminada quando **os cinco checks do novo commit** ficarem
verdes; merge continua bloqueado até lá.

## Adendo — gate F27 obsoleto no CI Windows

No commit `36f024e`, o job `windows` passou **`Tests`** e falhou somente em
`F27 physical gate policy`. O workflow importava
`app.computer_control.windows_driver`, movido para `archive/` na Fase 0;
reproduzido localmente com `ModuleNotFoundError`. Antes de remover a etapa,
foram inspecionados todos os quatro arquivos em `.github/workflows/`:
nenhum outro job/workflow usa o módulo, a etapa, outputs dela ou `needs:`.
Os scripts manuais legados `scripts/f27_windows_smoke.py` e
`scripts/f28_vision_smoke.py` não são invocados pelo CI. A etapa foi
removida com comentário explicativo; `Compile` e `Tests` permanecem.
**Merge ainda condicionado aos cinco checks verdes no novo commit.**
