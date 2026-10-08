# Revisão crítica do PR #33 — 2026-10-08

**Estado: revisão e testes concluídos; merge NÃO realizado.** O repositório usa `master` como branch padrão; `main` não existe. O PR #33 tem base `master`. A solicitação exige merge e teste pós-merge **em `main`**. Não criei nem forcei uma branch diferente; preciso que o proprietário confirme explicitamente se aceita o merge em `master` (branch padrão existente). Até lá, o PR permanece aberto.

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

**1374 passed / 7 skipped / 0 failed (12,61 s).** Os 7 skips continuam sendo apenas `tkinter` ausente no sandbox. Diferença em relação ao relatório original (**1364 / 7 / 0**): **+10 testes de regressão desta revisão** — 5 em `tests/test_mcp_server.py`, 3 em `tests/test_unreal_bridge.py`, 2 em `tests/test_research_client.py`. Nenhum teste antigo foi removido ou passou a falhar. `RELATORIO_FINAL.md`, `TESTE_LOCAL.md`, `README.md` e `LUMEN_STATE.md` registram agora a nova contagem; os números por fase no relatório permanecem marcados como históricos.

## 4. Merge — BLOQUEADO

**Não executar `gh pr merge` antes de esclarecer o destino.** O pedido menciona `main` em todas as verificações pós-merge, mas o PR tem base `master` e não existe `main` no remoto. Fazer merge em `master` por conta própria não satisfaria a instrução literal de testar diretamente em `main`. Também não é aceitável inventar um hash de merge. O PR permanece aberto para revisão.

**Decisão necessária do proprietário:** autoriza merge do PR #33 na branch padrão **`master`** e teste pós-merge do conteúdo de `master`? Se a exigência for literalmente `main`, será necessário ajustar a estratégia de branch fora desta sessão antes do merge.

## 5. Verificação pós-merge — NÃO EXECUTADA

Sem merge em `main` (inexistente), não é possível afirmar que `bootstrap.ps1`, `TESTE_LOCAL.md`, `mcp_config.json`, `RELATORIO_FINAL.md` e `PESQUISA_MCP_EXISTENTES.md` estejam em `main`, nem rodar `git log --oneline -10` ali. Esses cinco arquivos **existem na branch do PR**, mas isso não substitui a verificação pedida após o merge.

## 6. `PRONTO_PARA_TESTE.md` — NÃO CRIADO

O arquivo solicitado exigiria **confirmação e hash de um merge bem-sucedido**, que ainda não ocorreu. Criá-lo agora com essa afirmação seria falso. Depois da autorização para usar a branch de destino real e do teste pós-merge, ele poderá incluir o comando `./bootstrap.ps1` do Windows (com caminho `.uproject` preenchido pelo usuário), o link direto a [`TESTE_LOCAL.md` §1 — Pré-requisitos](TESTE_LOCAL.md#1-pré-requisitos) e os 24 itens de validação manual de `RELATORIO_FINAL.md` §3 reordenados por risco/precedência (sem Unreal → conexão/RC API pura → Python no editor, componente por último).

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
entrada UTF-8 com acentos; a suíte completa passou com **1374 passed / 7
skipped / 0 failed**. O check Windows **precisa ficar verde no commit novo**
antes de qualquer merge. A etapa F27 no workflow Windows continua pendente
de execução após `Tests` e importa um módulo movido para `archive/`: será
necessário observar o check real; nenhuma correção especulativa foi feita.
