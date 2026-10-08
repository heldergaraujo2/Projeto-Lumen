# RELATÓRIO FINAL — LUMEN como agente autônomo local

**Data:** 2026-10-08
**Branch:** `arena/59a23416-projeto-lumen` (base `19764fc`)
**Commits:** 8 fases + revisão do PR #33 (ver [`REVISAO_PR_33.md`](REVISAO_PR_33.md))
**Suíte de testes:** **1375 passed / 0 failed / 7 skipped** (11,99 s, revisão PR #33)

---

## 1. Resultado da suíte (números exatos)

```
$ PYTHONIOENCODING=cp1252 python -m pytest -q --no-header
1375 passed, 7 skipped in 11.99s
```

**Antes desta trilha:** 1393 passed + **2 falhando**.
**Depois da Fase 0** (limpeza): 991 passed / 7 skipped / **0 falhando**.
**Agora:** 1375 passed / 7 skipped / 0 falhando (revisão PR #33).

Os 373 testes originais vêm das fases 1–6; a revisão do PR #33 acrescentou
11 testes de regressão (6 MCP, 3 Unreal, 2 pesquisa). O salto 1393 → 991 é a Fase 0
removendo ~8.819 LOC de código morto **junto com os testes dele** — a
diferença é exatamente o código arquivado, não cobertura perdida. As duas
falhas que existiam antes eram do `tkinter` ausente e foram resolvidas com
`importorskip`, não com `--ignore`.

**Os 7 skipped são todos ambientais**, nenhum é funcionalidade não testada:

| Arquivo | Motivo |
| --- | --- |
| `test_gemini_integration.py:15` | sem `tkinter` no sandbox |
| `test_post_approval_ui.py:13` | sem `tkinter` no sandbox |
| `test_settings_dialog.py:16` | sem `tkinter` no sandbox |
| `test_tools_dialog.py:16` | sem `tkinter` no sandbox |
| `test_tools_correction.py:323, 360` | sem `tkinter` no sandbox |
| `test_ui_smoke.py:12` | sem `tkinter` no sandbox |

No Windows (e em CI com `python3-tk`) eles rodam.

### Testes por fase

| Fase | Arquivo | Testes |
| --- | --- | --- |
| 1 | `tests/test_research_client.py` | 31 |
| 1 | `tests/test_research_tool.py` | 16 |
| 1 | `tests/test_research_integration.py` | 10 |
| 2 | `tests/test_planning.py` | 77 |
| 2 | `tests/test_planning_e2e.py` | 14 |
| 3 | `tests/test_mcp_server.py` | 70 |
| 4 | `tests/test_unreal_bridge.py` | 85 |
| 6 | `tests/test_bootstrap_script.py` | 58 |
| — | demais (ajustes de inventário, `create_directory`) | ~12 |
| revisão PR #33 | MCP (6), Unreal (3), pesquisa (2) | 11 |
| | **total desde a Fase 0** | **384** |

---

## 2. O que está implementado e testado

### Fase -1 — pesquisa de projetos MCP-Unreal existentes

**Entregável:** [`PESQUISA_MCP_EXISTENTES.md`](PESQUISA_MCP_EXISTENTES.md)
**Commit:** `a69c221`

Levantamento de mais de 20 repositórios, organizados em duas famílias:
(A) exigem **plugin C++ compilado** — ChiR24/Unreal_mcp (909★ MIT),
db-lyon/ue-mcp (385★ MIT), tumourlove, kvick-games, GenOrca (145★
Apache-2.0, o único Python); (B) **sem plugin C++** — usam Remote Control
API + Python Editor Script Plugin, como FFZackFair92/unreal-engine-mcp
(MIT) e edi3on/py-ue5-mcp-server (MIT).

**Decisão: implementar do zero em Python.** Justificativa em §4.

### Fase 0 — limpeza de código morto e correção de docs

**Entregável:** [`archive/README.md`](archive/README.md)
**Commit:** `4a47ea2` — ~8.819 LOC movidos, 162 arquivos no total

- Arquivados 8 pacotes sem nenhum caminho a partir de `main.py`/`app/ui/`:
  `evolution` (4.719 LOC), `computer_control` (1.908), `computer` (708),
  `unreal` (409), `workflows` (364), `experience` (355), `autonomy` (224),
  `learning` (132) + 38 arquivos de teste.
- `app/validation/` (64 LOC) **mantido de propósito**: é o gate fail-closed
  do workflow `f23-validation`.
- `StackLayer` foi extraída de `app/evolution/` para `app/ai/stack_layer.py`
  antes do arquivamento — dependência invertida (código vivo → morto).
- `pytest.ini` criado com `norecursedirs = archive`.
- Docs corrigidos: versão no README, contagem de testes, menção ao Ollama,
  e os cabeçalhos duplicados do `LUMEN_STATE.md`.

**Testado:** a suíte inteira roda a partir da raiz sem `--ignore`.

### Fase 1 — camada de pesquisa web

**Commit:** `5817b69` — `app/research/` (773 LOC) + 57 testes

- Tavily e Brave via `urllib` da stdlib (nenhuma dependência nova), no
  mesmo padrão de transporte injetável já usado no projeto. **Nenhum teste
  toca a rede.**
- `WebSearchTool` no contrato `ToolDefinition`/`ParameterDefinition`.
- **Fail-closed:** sem chave configurada, `web_search` não existe — não
  entra no registry nem no catálogo do Planner. Habilitar **não** concede
  permissão; a chave nunca aparece em `ToolResult.data` nem em mensagem de
  erro.
- Tetos de resposta (2 MB), timeout máximo, e recusa de URL não-http(s).

### Fase 2 — camada de planejamento com aprovação

**Commit:** `b7f37f0` — `app/planning/` (1.143 LOC) + 102 testes

- `FeaturePlan` **imutável** (`frozen`) com `PlanArtifact` (arquivo a
  criar/sobrescrever, conteúdo completo) e `PlanCommand` (argv em **lista**,
  nunca string de shell).
- **Digest sha256** do conteúdo revisado: muda se o conteúdo mudar depois
  da aprovação (anti-TOCTOU), e **não** muda ao aprovar.
- `ApprovalGate`: `submit`/`approve`/`reject`/`expire`, teto de pendentes,
  rejeita reenvio do mesmo `plan_id` e aprovação cruzada entre planos.
- **`to_planner_plan()` levanta `PlanNotApprovedError` sem aprovação
  explícita** — este é o portão, e ele é testado nos dois lados.
- `render.py`: o plano legível que o usuário aprova. Não despeja conteúdo
  de arquivo no terminal por padrão.
- Caminhos validados por regex: sem absoluto, sem `..`, sem drive letter.

**Testes de ponta a ponta** (`test_planning_e2e.py`): um plano aprovado
**cria arquivos reais** (`.h`/`.cpp` de um sistema de inventário) num
workspace temporário, passando pela cadeia de segurança existente — e
**nenhum arquivo aparece sem aprovação**, nem quando o checkpoint é
recusado.

### Fase 3 — servidor MCP

**Commit:** `53aced1` — `app/mcp_server/` (1.328 LOC) + 70 testes

- **JSON-RPC 2.0 sobre stdio**, o transporte oficial da spec para servidores
  locais. Implementado sobre `app/tools/protocol.py`, sem dependência nova.
- `initialize` (negociação de versão + `capabilities` + `serverInfo`),
  `notifications/initialized`, `tools/list`, `tools/call`, `ping`.
- Serializer `ToolDefinition` → schema oficial de tool MCP, com
  `additionalProperties: false` porque o LUMEN **rejeita** parâmetro
  desconhecido: o schema diz a verdade em vez de deixar o LLM adivinhar.
- A chamada entra por `run_tool_call()` → `Plan` → `run_plan()`.
  **Nunca** `registry.execute()` direto: permissões, sandbox, checkpoint e
  auditoria continuam ativos.
- `mcp_config.json` na raiz, com os dois perfis prontos.

**Testado, inclusive subindo o servidor como subprocesso real** e falando
MCP por stdio — é o que pega um entry point quebrado, e pegou um
(`ToolsController` exige `workspaces_file`/`audit_file`).

### Fase 4 — ponte com o Unreal Editor

**Commit:** `70c1a63` — `app/unreal_bridge/` (1.786 LOC) + 85 testes

- `RemoteControlClient` sobre `urllib`, transporte injetável. Rotas
  conforme a referência HTTP oficial da Epic (5.8, consultada em
  2026-10-08): `/remote/info`, `/remote/object/call`,
  `/remote/object/property`, `/remote/object/describe`,
  `/remote/search/assets`, `/remote/batch`, `/remote/object/thumbnail`,
  `/remote/object/event`.
- **O corpo de cada requisição é comparado com os exemplos da
  documentação** nos testes, campo a campo. Se a forma mudar, o teste
  quebra.
- 7 ferramentas `unreal_*`, todas exigindo permissão `WRITE`, todas
  desligadas por padrão.

### Fase 5 — documentação e guia de teste local

**Commit:** `05f205b` — [`TESTE_LOCAL.md`](TESTE_LOCAL.md)

Pré-requisitos exatos, como habilitar os dois plugins, o bloco completo do
`DefaultRemoteControl.ini`, comandos de execução, configuração do Claude
Desktop e do Cline, teste mínimo passo a passo para validar a Fase 4, e
troubleshooting organizado por área.

### Fase 6 — bootstrap para Windows

**Commit:** `ec96415` — [`bootstrap.ps1`](bootstrap.ps1) (684 linhas) + 58 testes

As 11 etapas documentadas, sem nenhum caminho fixo, com `Read-Host` quando o
parâmetro não vem. Falha na suíte é fatal; editor fora do ar **não** é (o
resumo diz "Pronto para uso PARCIAL" e explica o que funcionou).

---

## 3. O que precisa de validação manual no seu PC

**Item por item. Nada desta lista foi executado** — não há Windows, Unreal
ou chave de API real neste ambiente. `bootstrap.ps1` **não sobe um servidor
stdio persistente**: gera o JSON para o cliente MCP iniciar o subprocesso.
As camadas ainda não formam um único fluxo de chat autônomo integrado.

### 3.1 Sem Unreal (dá para validar hoje, só com o repo)

| # | Item | Como validar |
| --- | --- | --- |
| 3.1.1 | `bootstrap.ps1` roda no PowerShell 5.1 | `.\bootstrap.ps1 -SkipTests` e conferir as etapas 1–4 |
| 3.1.2 | Descoberta do Python e do `.uproject` | rodar sem parâmetros e responder aos `Read-Host` |
| 3.1.3 | Parada correta quando falta plugin | apontar para um `.uproject` sem `RemoteControlAPI` e conferir a mensagem |
| 3.1.4 | Cliente MCP carrega o servidor | configurar Claude Desktop/Cline e ver `lumen` na lista de servidores |
| 3.1.5 | `tools/list` no cliente real | deve listar as ferramentas de leitura |
| 3.1.6 | Leitura de arquivo pelo cliente | pedir para ler um arquivo do workspace |
| 3.1.7 | Escrita **sem** `--allow-write` recusada | pedir uma escrita e conferir a recusa |
| 3.1.8 | Escrita **com** `--allow-write` pausa no checkpoint | conferir a resposta "⏸ aguardando aprovação" e que **nada** foi escrito; não há UI compartilhada no servidor MCP separado: para efetivar escrita, reiniciar com `--auto-approve` após revisar o risco |
| 3.1.9 | Pesquisa web com chave real | `TAVILY_API_KEY` no `.env`, pedir uma busca |
| 3.1.10 | Fluxo com LLM real | todo o desenvolvimento usou `FakeProvider`/`MockProvider`; o caminho com OpenAI/Gemini/Groq ainda não foi exercitado de ponta a ponta |
| 3.1.11 | Testes de `tkinter` | rodar a suíte no Windows: os 7 skips devem virar passes |

### 3.2 Com Unreal aberto — RC API pura (maior confiança)

| # | Item | Como validar |
| --- | --- | --- |
| 3.2.1 | Porta 30010 responde | `Invoke-RestMethod http://127.0.0.1:30010/remote/info`; para ver `unreal_*` no MCP, configurar `--enable-unreal-bridge --allow-write` |
| 3.2.2 | `unreal_get_info` | deve reportar `connected: true` e a contagem de rotas |
| 3.2.3 | `unreal_describe_object` | num ator do nível; conferir propriedades e funções |
| 3.2.4 | `unreal_search_assets` | buscar um asset que você sabe que existe |
| 3.2.5 | `unreal_call_function` | numa função `BlueprintCallable`; conferir a entrada no Undo History |
| 3.2.6 | `unreal_set_property` | mudar uma propriedade **visível** e desfazer com Ctrl+Z |
| 3.2.7 | Nome real das rotas | comparar a saída com a lista da doc da Epic |

### 3.3 Com Unreal aberto — Python no editor (**menor confiança**)

Estes dependem de APIs que mudaram bastante entre 5.0 e 5.5, e **nunca
rodaram dentro de um Unreal**:

| # | Item | Risco específico |
| --- | --- | --- |
| 3.3.1 | Os **dois portões** do `DefaultRemoteControl.ini` | `bEnableRemotePythonExecution` libera o *objeto*; `CustomAllowedRemoteFunctionCalls` libera a *chamada*. Falhar em cada um dá erro **diferente** |
| 3.3.2 | Formato da resposta de `ExecutePythonCommandEx` | o parser aceita `CommandResult`/`LogOutput` e é **tolerante**; confirme se os campos batem na sua versão |
| 3.3.3 | `unreal_create_blueprint_class` | `AssetTools.create_asset` + `BlueprintFactory`; conferir se `parent_class` é aplicado |
| 3.3.4 | `unreal_add_component` | **o mais volátil.** `BlueprintEditorLibrary.add_component` pode exigir o editor de Blueprint aberto para persistir |
| 3.3.5 | Nome de `BlueprintEditorLibrary.open_blueprint` | pode não existir em versões antigas — o script trata, mas não foi testado |
| 3.3.6 | Persistência após `compile_blueprint` + `save_asset` | confirmar que o componente sobrevive a reabrir o projeto |

O roteiro completo está em **`TESTE_LOCAL.md` §4** (teste mínimo com
`BP_TestConnection`) e **§7** (por que criar Blueprint exige Python).

### 3.4 Como as ferramentas avisam sobre isso

As duas ferramentas de Python marcam a saída com
`needs_manual_validation: true` e carregam `metadata["validation"]` na
`ToolDefinition`. Quando o editor não confirma sucesso, elas **falham** —
`parse_execution_result()` devolve `ok=False` com `unrecognized=True` em
vez de inventar sucesso. Você vê o `Output Log` do Unreal (filtro
`LUMEN:`), não um "deu certo" sem base.

---

## 4. Fase -1: reaproveitou ou implementou do zero?

**Implementou do zero — e o motivo principal é jurídico, não técnico.**

### O achado que decide

O projeto mais popular da área, `chongdashu/unreal-mcp` (**2.091 ★**), **não
tem arquivo `LICENSE`**. O README traz um badge "MIT", mas o badge não é a
licença. Verificado pela API do GitHub: o campo de licença vem vazio, e a
listagem de `contents/` não tem `LICENSE`. Um fork ou uma cópia de código
sem licença explícita é **juridicamente inutilizável**, independentemente
de quantas estrelas tenha. (E o projeto está parado desde 2025-04.)

### Os demais candidatos sérios não encaixam

| Projeto | ★ | Licença | Linguagem | Por que não |
| --- | --- | --- | --- | --- |
| ChiR24/Unreal_mcp | 909 | MIT | **TypeScript + plugin C++** | toolchain C++ no bootstrap; reescrita completa |
| kvick-games/UnrealMCP | 613 | **sem licença** | C++ | inutilizável |
| db-lyon/ue-mcp | 385 | MIT | C++ plugin | idem ChiR24 |
| GenOrca/unreal-mcp | 145 | Apache-2.0 | Python, **mas com plugin C++** | único Python permissivo, e ainda exige `Plugins/` compilado |
| remiphilippe/mcp-unreal | 75 | Apache-2.0 | **Go** | binário Go; 49 tools; não integra ao modelo de permissões |

Ou seja: os maduros são TypeScript/Go/C++, e o único Python sob licença
permissiva ainda exige compilar um plugin C++.

### Por que "do zero" é a escolha certa aqui

1. **Licença.** Dois dos três mais populares não têm licença. Os que têm
   são MIT/Apache-2.0 — compatíveis, mas em outra linguagem.
2. **Custo de toolchain.** Todos os maduros exigem compilar um plugin C++
   dentro do projeto do usuário. O `bootstrap.ps1` teria de orquestrar
   Visual Studio + UBT antes de qualquer coisa funcionar. O caminho
   "RC API + Python Editor Script Plugin" não exige compilar nada.
3. **Modelo de segurança.** O requisito é uma ponte **fina e auditável**
   que entre pela cadeia já existente do LUMEN (permissões → sandbox →
   checkpoint → auditoria). Adotar um servidor de terceiros significaria
   reimplementar essa integração de qualquer forma — e sem controle sobre
   ela.
4. **Superfície de dependência.** 5.030 LOC novos em Python, sem
   dependência nova nenhuma (só `urllib` da stdlib), contra trazer um
   runtime Node ou um binário Go.

**Mas o trabalho de pesquisa não foi perdido.** A Fase -1 não terminou em
"ninguém serve" — terminou no **achado técnico que define a arquitetura da
Fase 4**, validado de forma independente:

> A Remote Control API **não tem rota para criar assets**. A lista de
> `/remote/info` é completa e não inclui criação de asset. Todo projeto que
> cria Blueprint precisa de plugin C++ **ou** de executar Python no editor.

Isso está confirmado na documentação oficial da Epic e reaparece no código
(§5.1). Foi o achado que evitou projetar uma Fase 4 que só falharia no PC do
usuário.

---

## 5. Bloqueios, decisões técnicas e o porquê

### 5.1 Bloqueio real: a RC API não cria assets

**Não há contorno.** Não existe `/remote/asset/create`. Consequência
assumida explicitamente no código:

- `unreal_set_property` e `unreal_call_function` → RC API pura;
- `unreal_create_blueprint_class` e `unreal_add_component` → **executam
  Python dentro do editor**, e falham com mensagem explícita quando o
  transporte é `rc`.

Em vez de esconder, cada `ToolDefinition` carrega
`metadata["validation"]`, e a saída marca `needs_manual_validation: true`.

### 5.2 Dois portões, não um

Aprovar o **plano** (Fase 2) não aprova as **operações**. Cada escrita e
cada comando pausa de novo no checkpoint do `PlanExecutor`. São gates
independentes, e a camada nova **não** encurta a cadeia existente — isso é
testado (`test_planning_e2e.py` verifica que nada é escrito antes do
checkpoint, e que recusar o checkpoint não deixa arquivo para trás).

Um cliente MCP não tem como clicar "aprovar" quando roda como subprocesso
do Claude Desktop. `--auto-approve` resolve isso sendo o que de fato é: o
consentimento **prévio, nomeado e auditado** do humano que inicia o
processo. Sem ele, a resposta é "⏸ aguardando aprovação" com
`isError: false` — não falhou, nada rodou. O servidor MCP separado **não
compartilha o controlador da UI**, portanto não há como aprovar aquele
checkpoint pela janela da LUMEN; repetir a chamada criaria outro checkpoint.
`--auto-approve` cobre só o checkpoint de *operação*, não o
`ApprovalGate` de *FeaturePlan*. **Não há orquestrador único de chat** que
conecte automaticamente as fases 1–4.

### 5.3 Fail-closed em tudo que é novo

| Recurso | Default | Para ligar |
| --- | --- | --- |
| `web_search` | ausente | `enable_web_search()` + chave; no CLI MCP: `--enable-web-search` |
| ferramentas `unreal_*` | ausentes | `enable_unreal_bridge()`; no CLI MCP: `--enable-unreal-bridge --allow-write` |
| ferramentas destrutivas no MCP | não listadas | `--allow-write` |
| escrita automática no MCP | não | `--auto-approve` (exige `--allow-write`) |
| terminal | desabilitado | allowlist explícita + permissão `TERMINAL` |

E **expor não é conceder**: `--allow-write` sem permissão `WRITE` continua
bloqueado, e `enable_unreal_bridge()` não concede `WRITE`. Testado nos
dois casos.

### 5.4 Defeitos reais encontrados pelos testes (não por inspeção)

Vale registrar, porque é o argumento para o esforço de teste:

| # | Defeito | Como apareceu | Correção |
| --- | --- | --- | --- |
| 1 | **Nada no LUMEN criava diretórios.** `create_file` exige o pai existente — nenhum plano com `Source/Jogo/Public/X.h` conseguiria executar | teste de ponta a ponta da Fase 2 | `CreateDirectoryTool` + expansão automática dos pais em `to_planner_plan()` |
| 2 | `Plan.validate()` **não existe** em `app/planner/models.py` | primeira execução de `to_planner_plan()` | validação movida para a camada que pode garantir o que promete |
| 3 | `TaskRun` não tem `.ok`; comparar status com literal minúsculo dava falso negativo | teste do modo `auto_approve` | comparação com o **enum**, não com string |
| 4 | `stdio.py` passava um `dict` para `_write()`, que espera string — `TypeError` no meio do laço | teste de linha oversized | `dumps_line()` aplicado |
| 5 | `ToolsController` exige `workspaces_file`/`audit_file`; o entry point do MCP não os passava | teste com **subprocesso real** | `--data-dir` reusando a pasta do LUMEN |
| 6 | Resumo do MCP mostrava "executado" sem o conteúdo lido (JSON escapado) | inspeção do resultado | `_decode()` do `ToolResult` serializado |

### 5.5 O guard test foi **reforçado**, não afrouxado

`tests/test_planner_integration.py` proibia a substring `"unreal"` em
`app/planner/` — um proxy grosseiro para "o planner não executa nada".
A Fase 4 precisa **descrever** ferramentas `unreal_*` no catálogo (que é
justamente a allowlist que impede o Planner de inventar nomes).

Em vez de remover a proibição, ela virou uma verificação por **AST**: o
pacote `app/planner/` não pode **importar** `app.tools`, `app.executor`,
`app.unreal_bridge` nem `app.mcp_server`. Descrever continua permitido;
importar o código que executa, não. É uma garantia mais forte que a
anterior.

### 5.6 Ambiente

`tkinter` não está disponível no sandbox (sem `apt` com root), então os
testes de UI são pulados com `importorskip` — não com `--ignore`, que
esconderia arquivos quebrados. No Windows rodam.

Versão do MCP: implementada contra a **2025-06-18**, a versão cujo schema
de tools foi conferido linha a linha. A spec mais recente já é a
**2026-07-28**; o servidor **negocia** versão (ecoa a do cliente quando
suportada) e a lista de suportadas está isolada em
`SUPPORTED_PROTOCOL_VERSIONS`. Migrar é uma mudança localizada.

---

## 6. Estado do repositório

```
1375 passed / 0 failed / 7 skipped (tkinter; revisão PR #33)

a69c221  fase -1: pesquisa de projetos MCP-Unreal existentes
4a47ea2  fase 0: limpeza de codigo morto e correcao de docs
5817b69  fase 1: camada de pesquisa web
b7f37f0  fase 2: camada de planejamento
53aced1  fase 3: servidor MCP
70c1a63  fase 4: ponte com Unreal via Remote Control API
05f205b  fase 5: documentação e guia de teste local
ec96415  fase 6: bootstrap automatizado para Windows
```

**Código novo:** 5.030 LOC em `app/` (research 773, planning 1.143,
mcp_server 1.328, unreal_bridge 1.786) + 4.019 LOC de testes.
**Dependências novas:** nenhuma.

### Entregáveis

| Arquivo | O que é |
| --- | --- |
| [`PESQUISA_MCP_EXISTENTES.md`](PESQUISA_MCP_EXISTENTES.md) | Fase -1: panorama, top 3, decisão |
| [`archive/README.md`](archive/README.md) | Fase 0: o que foi arquivado e por quê |
| [`mcp_config.json`](mcp_config.json) | Fase 3: modelo para Claude Desktop/Cline |
| [`TESTE_LOCAL.md`](TESTE_LOCAL.md) | Fase 5: guia para validar no seu PC |
| [`bootstrap.ps1`](bootstrap.ps1) | Fase 6: um comando no Windows |
| `RELATORIO_FINAL.md` | este relatório |

---

## 7. Próximo passo concreto

1. `git pull` e `.\bootstrap.ps1 -UnrealProjectPath "C:\...\SeuProjeto.uproject" -LaunchUnreal`
2. Siga **`TESTE_LOCAL.md` §1 e §4** — configure o cliente MCP com
   `--enable-unreal-bridge --allow-write`; para testar escrita no processo
   separado, revise o risco de `--auto-approve` em projeto descartável.
   Comece por `unreal_get_info` e só depois tente `BP_TestConnection`.
3. **Valide primeiro os itens de §3.2** (RC API pura): são os de maior
   confiança e os que mais valor entregam.
4. Só depois teste §3.3 (criação de Blueprint). Se algo falhar ali, o
   `Output Log` do Unreal com o filtro `LUMEN:` diz exatamente em que ponto
   — e `TESTE_LOCAL.md` §7 explica o que é limitação documentada e o que
   seria defeito.

Se algo de §3 falhar, o motivo mais provável está em
`TESTE_LOCAL.md` §8, que cobre os erros de conexão um por um.
