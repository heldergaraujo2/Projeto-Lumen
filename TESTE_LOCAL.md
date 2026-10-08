# TESTE LOCAL — LUMEN como agente no seu PC

Guia para testar a LUMEN **na sua máquina**. Há dois caminhos distintos:

1. A **janela da Lumen**, que usa o planner do chat e pode consultar pesquisa
   web e Unreal em modo somente leitura — veja **“Testar pela UI”** abaixo.
   Este caminho não precisa de Claude Desktop, Cline nem servidor MCP.
2. Um **cliente MCP** (Claude Desktop/Cline), documentado nas seções 2–4,
   com permissões e ciclo de vida próprios. A UI da Lumen não compartilha
   aprovações com o subprocesso MCP.

O teste pela UI cobre as integrações de consulta; criação de Blueprint e
outras alterações no editor são um fluxo separado e continuam marcadas como
**[NÃO VALIDADO]** quando dependem de um Unreal real.

---

## 0. O que já foi testado e o que não foi

Isso importa antes de você gastar tempo.

| Área | Status | Evidência |
| --- | --- | --- |
| Camada de pesquisa (Tavily/Brave) | ✅ testes automatizados | Provedor e HTTP mockados; nenhuma chamada a uma API de busca real nesta validação |
| Planner + permissões/checkpoints | ✅ testes automatizados | Incluem validação do plano JSON, execução controlada e arquivos em workspace temporário |
| Integrações do planner pela UI | ✅ testes automatizados | Web e três tools Unreal read-only testadas com fakes; JSON malformado/tool desconhecida aparecem como erro controlado, sem execução |
| Servidor MCP (JSON-RPC/stdio) | ✅ testado | 76 testes; inclui subprocessos reais do servidor |
| Ponte RC API (rotas HTTP) | ✅ testada contra a documentação | Corpos das requisições comparados aos exemplos da API; não é um Unreal Editor real |
| Interface visual com provedor real / busca externa / Unreal real | ⚠️ **NÃO VALIDADO neste ambiente** | Os testes da UI usam toolkit falso; siga “Testar pela UI” neste guia na sua máquina |
| Criar Blueprint / adicionar componente | ⚠️ **NÃO VALIDADO** | Exige Unreal real; ver §7 |
| Bootstrap no Windows | ⚠️ **NÃO VALIDADO** | Escrito para PowerShell 5.1; sem Windows aqui |

Suíte completa executada nesta revisão: **1382 passed / 7 skipped / 0 failed**.

---

## 1. Pré-requisitos

### 1.1 Versões

| Item | Exigência |
| --- | --- |
| Windows | 10 ou 11 (o `bootstrap.ps1` usa PowerShell 5.1, que já vem no sistema) |
| Python | **3.10 ou superior** (`python --version`) |
| Unreal Engine | **5.0+**; recomendado **5.3+** (a Remote Control API existe desde 4.27, mas as ferramentas de edição de Blueprint mudaram bastante entre 5.0 e 5.5) |
| Git | qualquer versão recente |
| Claude Desktop **ou** Cline | **Opcional**: necessário apenas se for testar o caminho MCP (§§2–4); não é usado no teste pela UI |

> O Unreal **não** é obrigatório para testar pesquisa web, planejamento,
> arquivos ou o servidor MCP. As consultas Unreal pela UI e as operações da
> Fase 4 exigem o editor aberto com a Remote Control API.

### 1.2 Habilitar os plugins no Unreal

Você precisa de **dois** plugins, e eles fazem coisas diferentes:

- **Remote Control API** — abre o servidor HTTP na porta 30010. Sem ele, a
  ponte nem enxerga o editor.
- **Python Editor Script Plugin** — permite executar Python dentro do
  editor. **Sem ele é impossível criar Blueprint**, porque a Remote Control
  API não tem rota para criar assets (ver §7).

**Pelo editor:**

1. Abra o projeto no Unreal Editor.
2. `Edit` → `Plugins`.
3. Procure **"Remote Control API"** → marque `Enabled`.
4. Procure **"Python Editor Script Plugin"** → marque `Enabled`.
5. **Reinicie o editor** quando ele pedir.

**Pelo arquivo `.uproject`** (alternativa, dá para conferir depois):

```json
{
	"FileVersion": 3,
	"EngineAssociation": "5.3",
	"Plugins": [
		{ "Name": "RemoteControlAPI", "Enabled": true },
		{ "Name": "PythonScriptPlugin", "Enabled": true }
	]
}
```

O nome no `.uproject` é `RemoteControlAPI` (sem espaços) — o rótulo
"Remote Control API" que aparece no editor é o nome amigável.

### 1.3 Liberar a execução remota de Python [NÃO VALIDADO]

Esta é a etapa que mais gente esquece, e ela tem **dois portões
separados** — um libera o *objeto*, o outro libera a *chamada de função*.
Falhar em cada um dá um erro diferente (§8).

Crie (ou edite) o arquivo **`Config/DefaultRemoteControl.ini`** na raiz do
seu projeto Unreal:

```ini
[/Script/RemoteControlCommon.RemoteControlSettings]
bAutoStartWebServer=True
bAutoStartWebSocketServer=True
RemoteControlHttpServerPort=30010
bEnableRemotePythonExecution=True
bAllowAnyRemoteFunctionCall=False
+CustomAllowedRemoteFunctionCalls=(ClassPath="/Script/PythonScriptPlugin.PythonScriptLibrary")
bAllowConsoleCommandRemoteExecution=False
```

Pontos que importam:

- o arquivo é **`DefaultRemoteControl.ini`**, não `DefaultEngine.ini`. A
  classe de settings é declarada com `config = RemoteControl`, e é isso que
  o runtime lê;
- `bAllowAnyRemoteFunctionCall=False` com uma entrada **específica** em
  `CustomAllowedRemoteFunctionCalls` é melhor que liberar tudo. A LUMEN só
  precisa da biblioteca do Python;
- `bAllowConsoleCommandRemoteExecution=False` fica desligado — não
  precisamos disso;
- **reinicie o editor** depois de salvar. O valor é lido no início;
- em versões antigas do engine essas chaves podem simplesmente ser
  ignoradas — nesses casos a execução remota de Python não era bloqueada.

### 1.4 Variáveis de ambiente

Crie um arquivo **`.env`** na raiz do repositório clonado (copie de
`.env.example`). O mínimo:

```ini
# Pesquisa web (Fase 1) — escolha UM dos dois provedores
LUMEN_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=tvly-sua-chave-aqui

# Ponte com o Unreal (Fase 4)
LUMEN_UNREAL_RC_HOST=127.0.0.1
LUMEN_UNREAL_RC_PORT=30010
LUMEN_UNREAL_TRANSPORT=auto
LUMEN_UNREAL_TIMEOUT=30
```

- **Tavily**: cadastre-se em <https://app.tavily.com> e pegue a chave (tem
  plano gratuito). Alternativa: `LUMEN_SEARCH_PROVIDER=brave` +
  `BRAVE_API_KEY` (<https://brave.com/search/api/>).
- Sem chave nenhuma, a pesquisa web simplesmente **não aparece** como
  ferramenta. O resto continua funcionando — o sistema é fail-closed, não
  quebra.

> **Nunca** comite o `.env`. Ele já está no `.gitignore`.

## Testar pela UI (sem cliente MCP)

Este roteiro testa a integração do planner com pesquisa web e as **três
consultas Unreal read-only** pela própria janela da Lumen. Não inicia
`app.mcp_server`, não usa Claude Desktop/Cline e não chama as quatro tools
mutáveis de Unreal.

### Preparar e abrir a janela

1. Se ainda não existir, crie o ambiente virtual; depois instale as dependências:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Configure um provedor de IA real/local e um modelo que siga instruções e
   produza o JSON pedido pelo planner. Faça isso em **Configurações** na UI
   ou configure `LUMEN_PROVIDER`, `LUMEN_MODEL` e as credenciais no `.env`.
   `MockProvider` é offline e útil para testar a janela, mas não escolhe
   `web_search` nem ferramentas Unreal para objetivos livres; não o use para
   validar estas duas integrações.
3. Para pesquisa, configure no `.env` **um** provedor: `LUMEN_SEARCH_PROVIDER=tavily`
   com `TAVILY_API_KEY`, ou `LUMEN_SEARCH_PROVIDER=brave` com `BRAVE_API_KEY`.
   Salve o `.env` antes de abrir a Lumen. A chave de busca é independente da
   chave do provedor de IA.
4. Para Unreal, abra o editor e habilite o plugin **Remote Control API**.
   Aponte `LUMEN_UNREAL_RC_HOST` e `LUMEN_UNREAL_RC_PORT` para a RC API
   (por padrão `127.0.0.1:30010`). Para estas consultas **não** é necessário
   habilitar Python remoto nem o Python Editor Script Plugin: o teste apenas
   consulta informações, assets e descrições de objetos.
5. Na raiz do repositório, abra a janela:

   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```

6. Clique em **🛡 Ferramentas**. Em **INTEGRAÇÕES OPCIONAIS (planner da UI)**,
   clique em `Pesquisa web: OFF` e `Unreal (somente leitura): OFF` conforme
   o teste que pretende fazer. Os botões passam a `ON`. Para uma ativação
   normal, o topo da janela do diálogo deve mostrar, respectivamente,
   `🟢 Pesquisa web ativada (<provedor>); READ continua necessária para executar.`
   e/ou `🟢 Consultas Unreal ativadas (somente leitura; READ continua necessária).
   Nenhum pedido foi enviado ao editor.` A ativação só adiciona tools ao
   planner; ainda não faz busca nem chama o editor.
7. Na seção **PERMISSÕES**, clique **Conceder** na linha `READ`. Deve aparecer
   `🟢 Permissão READ concedida.` e o estado passa a `● concedida`. Não conceda
   `WRITE` para este teste. READ é independente dos toggles e precisa ser
   concedida explicitamente. Integrações e permissões são opt-in da sessão;
   confirme/ative novamente se reiniciar a Lumen.
8. Feche o diálogo e envie um objetivo em linguagem natural no chat.
   Uma consulta bem-sucedida aparece na conversa como uma mensagem `Lumen`,
   precedida por `✔ Plano ... concluído`; abaixo, a UI mostra
   `Resultados das consultas (dados para você revisar):` e os dados
   formatados da tool. Durante o pedido, o status da janela mostra
   `● Pensando…` e volta a `● Pronta` ao terminar.

### Objetivos de teste e o que deve aparecer

Faça os testes um de cada vez. Substitua nomes/caminhos de exemplo por algo
que exista no seu projeto.

**Pesquisa web** — com a integração web ligada:

> Pesquise na web boas práticas atuais de organização de inventário em jogos
> feitos na Unreal Engine e mostre títulos, links e trechos encontrados.

Na conversa, espere `Pesquisa web — <consulta>`, títulos numerados (`[1]`),
URLs e trechos. Podem aparecer até cinco resultados formatados. Não é uma
resposta garantida sobre a qualidade das fontes; revise os links apresentados.

**Estado da conexão Unreal** — com o editor aberto e Unreal read-only ligado:

> Verifique se o Unreal Editor está conectado e me informe o endereço e as
> rotas disponíveis.

A resposta deve começar por `Unreal Editor — conectado`, seguida de
`Endereço:` e `Rotas disponíveis:`. Este probe não altera o projeto.

**Busca de asset Unreal**:

> Procure no Content Browser assets cujo nome contenha `BP_` e liste os
> caminhos encontrados.

A resposta deve começar por `Assets Unreal — busca: BP_` e indicar
`Encontrados: <n>`, com nomes, classes e caminhos quando existirem resultados.

**Descrição de objeto Unreal** — use o caminho completo de um ator que esteja
carregado no nível aberto. Em projetos com o mapa de exemplo, um caminho
possível é `/Game/Maps/ThirdPersonExampleMap.ThirdPersonExampleMap:PersistentLevel.CubeMesh_5`:

> Descreva o objeto Unreal `<caminho completo do ator>` e liste sua classe,
> propriedades e funções.

A resposta deve conter `Objeto Unreal —`, `Caminho:`, `Classe:`,
`Propriedades (...)` e `Funções (...)`. Se o caminho não existir ou o ator
não estiver carregado, a falha aparece como resposta no chat; nada é alterado.

**Permissões e limites:** se READ não estiver concedida, a execução deve
falhar de forma controlada e explicar a permissão ausente; se a chave de busca
faltar, o toggle web fica `OFF` e o diálogo mostra uma mensagem vermelha de
configuração. Nenhum desses casos deve executar a consulta. A UI não mostra as
quatro tools Unreal mutáveis (`unreal_create_blueprint_class`,
`unreal_add_component`, `unreal_set_property`, `unreal_call_function`) no
catálogo read-only. Se o modelo devolver JSON malformado ou um nome de tool
fora do catálogo, o chat mostra um aviso controlado terminado em
`Nada foi executado.`. Para pesquisa/Unreal não é necessário cadastrar um
workspace; workspaces continuam necessários para tools de arquivo.

---

## 2. Rodar o servidor MCP

### 2.1 O caminho recomendado: o bootstrap

```powershell
.\bootstrap.ps1 -UnrealProjectPath "C:\MeuProjeto\MeuProjeto.uproject"
```

Ele verifica Python, cria o virtualenv, instala as dependências, roda os
testes, confere os plugins no `.uproject` e (com `-LaunchUnreal`) abre o
editor e testa a porta 30010. Detalhes em §6.

### 2.2 Rodar à mão (para entender o que acontece)

Na raiz do repositório, **somente leitura** — o mais seguro para começar.
Este perfil registra pesquisa e as consultas Unreal, mas não ativa ferramentas
mutáveis:

```powershell
.\.venv\Scripts\python.exe -m app.mcp_server `
    --workspace "C:\MeuProjeto" `
    --allow-read `
    --enable-unreal-bridge --enable-web-search
```

Sem `--allow-write`, o MCP filtra as quatro tools Unreal mutáveis. Com
`--allow-read`, as três consultas (e `web_search`, se houver chave e opt-in)
podem ser executadas; elas continuam exigindo READ.

Com tools mutáveis expostas, mas sem pré-aprovação automática (mais restritivo;
o servidor stdio pode deixar uma operação pendente porque não compartilha a
UI para confirmar):

```powershell
.\.venv\Scripts\python.exe -m app.mcp_server `
    --workspace "C:\MeuProjeto" `
    --allow-read `
    --allow-write `
    --enable-unreal-bridge --enable-web-search
```

`--enable-unreal-bridge` registra as sete tools Unreal. Sem `--allow-write`,
o gateway MCP expõe somente as três consultas (`unreal_get_info`,
`unreal_search_assets`, `unreal_describe_object`); as quatro mutáveis ficam
filtradas. `--enable-web-search` registra a busca somente se houver chave
válida no ambiente ou no `.env`. As duas opções são **opt-in** e não concedem
permissões adicionais: READ continua necessária para executar consultas;
WRITE é necessária para as operações mutáveis. Sem os respectivos opt-ins,
as tools não aparecem no `tools/list`, mesmo com plugins e chave configurados.

Com escrita **pré-autorizada** (o cliente MCP escreve sem confirmar):

```powershell
.\.venv\Scripts\python.exe -m app.mcp_server `
    --workspace "C:\MeuProjeto" `
    --allow-read --allow-write --auto-approve
```

Com terminal allowlistado (para compilar via UnrealBuildTool):

```powershell
.\.venv\Scripts\python.exe -m app.mcp_server `
    --workspace "C:\MeuProjeto" `
    --allow-read --allow-write --auto-approve `
    --terminal "UnrealBuildTool,git" --allow-terminal
```

**O que as flags significam** (e por que o default é restritivo):

| Flag | Efeito |
| --- | --- |
| `--workspace <pasta>` | autoriza uma pasta (pode repetir) |
| `--allow-read` | concede READ (ler/buscar arquivos e executar consultas web/Unreal) |
| `--allow-write` | **expõe** ferramentas mutáveis de arquivo e Unreal; a execução continua sob as demais políticas/checkpoints |
| `--auto-approve` | resolve os checkpoints sozinho — **exige** `--allow-write` |
| `--terminal <CMDs>` | allowlist de comandos que podem rodar |
| `--allow-terminal` | concede permissão de terminal (só faz sentido com `--terminal`) |
| `--enable-unreal-bridge` | registra as 7 tools; sem `--allow-write`, o gateway expõe só as 3 consultas read-only. Executá-las exige READ. |
| `--enable-web-search` | registra `web_search` somente com chave Tavily/Brave configurada; executar exige READ |

Sem nenhuma flag, o servidor expõe **zero** ferramentas. Ele vai ficando
mais capaz conforme você autoriza — e nunca concede nada sozinho.

> **`--auto-approve` é uma decisão sua, não um detalhe técnico.** O cliente
> MCP não compartilha a janela da aplicação LUMEN quando roda como
> subprocesso do Claude Desktop. Sem a flag, a escrita pausa **e não há
> interface para aprovar nesse processo**: não repita a chamada (criaria um
> novo checkpoint). Para testar escrita pelo cliente, revise o risco e
> inicie o perfil com `--auto-approve`. Isso **pula a confirmação por
> operação**; restringa o workspace e use um projeto descartável.

### 2.3 Testar sem cliente nenhum

Dá para conversar com o servidor direto, colando JSON no terminal:

```powershell
@'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","clientInfo":{"name":"eu","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
'@ | .\.venv\Scripts\python.exe -m app.mcp_server --workspace "C:\MeuProjeto" --allow-read
```

Você deve ver duas linhas JSON: a primeira com `protocolVersion`, a
segunda com a lista de ferramentas. Se aparecer isso, o servidor MCP está
de pé — o resto é configuração de cliente.

---

## 3. Configurar o cliente

### 3.1 Claude Desktop

Arquivo: **`%APPDATA%\Claude\claude_desktop_config.json`**
(cole `%APPDATA%\Claude` na barra do Explorer).

```json
{
  "mcpServers": {
    "lumen": {
      "command": "C:\\Projeto-Lumen\\.venv\\Scripts\\python.exe",
      "args": [
        "-m", "app.mcp_server",
        "--workspace", "C:\\MeuProjetoUnreal",
        "--allow-read"
      ],
      "cwd": "C:\\Projeto-Lumen",
      "env": {
        "LUMEN_MCP_LOG_LEVEL": "WARNING",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

Depois de salvar: **feche o Claude Desktop completamente** (inclusive na
bandeja do sistema) e abra de novo. Ele só lê esse arquivo na inicialização.

### 3.2 Cline (VS Code)

1. Abra o Cline no VS Code.
2. Clique no ícone de **MCP Servers** → **Configure MCP Servers** (ou
   `Ctrl+Shift+P` → `Cline: Open MCP Settings`).
3. Cole o mesmo bloco `mcpServers` de §3.1 no arquivo
   `cline_mcp_settings.json`.

### 3.3 Caminhos: não invente

| O quê | Onde fica |
| --- | --- |
| `python.exe` do venv | `<repo>\.venv\Scripts\python.exe` |
| Raiz do repositório (`cwd`) | onde está o `main.py` |
| `--workspace` | a pasta do **seu projeto Unreal** |

No JSON do Windows, **toda barra invertida é dupla** (`\\`). Esquecer isso
é o erro de configuração mais comum.

O `mcp_config.json` na raiz é um modelo com dois perfis. O perfil
`lumen-com-escrita` inclui `--enable-unreal-bridge` e `--enable-web-search`,
mas **não inclui `--auto-approve`**: até você optar por essa flag, operações
mutáveis não são executadas no subprocesso MCP. Copie apenas um perfil,
troque os caminhos e **não cole o campo `_comment`** no arquivo do cliente.
Para incluir as consultas Unreal no perfil somente leitura, acrescente
`--enable-unreal-bridge` e mantenha `--allow-read`; o gateway então expõe
`unreal_get_info`, `unreal_search_assets` e `unreal_describe_object`, sem
expor as quatro ferramentas mutáveis. A busca web também precisa de
`--enable-web-search` e uma chave válida.

---

## 4. Teste mínimo — valide a Fase 4 passo a passo

Objetivo: pedir um Actor Blueprint `BP_TestConnection` e **ver com os
próprios olhos** no Content Browser. [NÃO VALIDADO]

### Passo 0 — o editor está no ar?

Com o Unreal Editor aberto, no PowerShell:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:30010/remote/info" | ConvertTo-Json -Depth 4
```

Ou, se preferir `curl`:

```powershell
curl.exe http://127.0.0.1:30010/remote/info
```

✅ **Esperado**: um JSON com `"HttpRoutes"` listando caminhos como
`/remote/object/call`, `/remote/object/property`, `/remote/search/assets`.

❌ Se der *connection refused*: o editor está fechado, ou o plugin Remote
Control API não está habilitado, ou o servidor web não subiu. No console do
editor (tecla `` ` ``), rode `WebControl.StartServer`.

### Passo 1 — o agente enxerga o editor?

Antes dos passos 1 e 3, configure o cliente com `--allow-read` e
`--enable-unreal-bridge` e reinicie-o; não é necessário `--allow-write` para
consultas. Para a busca web, acrescente `--enable-web-search` e configure a
chave. O passo 2 e a alteração de propriedade no passo 4 são mutáveis:
executá-los pelo cliente MCP exige `--allow-write` e, para realmente aplicar
sem uma UI de aprovação (este servidor stdio não a oferece),
`--auto-approve`. Use essa combinação somente após revisar o risco, em um
projeto de teste. Para testes pela janela da Lumen, siga a seção “Testar pela
UI”; não use `--auto-approve`.

Peça ao agente (no chat do cliente MCP):

> Use `unreal_get_info` e me diga se o editor está conectado.

✅ **Esperado**: `connected: true`, com a URL base e a contagem de rotas.
Este passo **não muda nada** no seu projeto — é só um probe. Se ele falhar,
não siga adiante: resolva a conexão primeiro (§8).

### Passo 2 — criar o Blueprint

> Crie um Actor Blueprint chamado `BP_TestConnection` em `/Game/Blueprints`,
> com classe pai `Actor`.

Por baixo, o agente chama `unreal_create_blueprint_class` com
`asset_name="BP_TestConnection"`, `parent_class="Actor"`.

⚠️ **Este passo depende do Python no editor** (§1.3). Se o agente responder
com a mensagem sobre "Python Editor Script Plugin", é a configuração que
falta — não um bug.

✅ **Esperado**: no **Content Browser**, em `Content/Blueprints`, aparece o
asset `BP_TestConnection`.

### Passo 3 — confirmar pela busca de assets

> Procure o asset `BP_TestConnection` com `unreal_search_assets`.

✅ **Esperado**: um resultado com
`path = "/Game/Blueprints/BP_TestConnection.BP_TestConnection"`.

Esse passo é útil porque consulta o editor por um caminho **diferente** do
que criou o asset — se os dois concordam, o asset existe de verdade.

### Passo 4 — (opcional) chamar uma função sem criar nada

Para validar a RC API pura sem depender de Python, abra o nível
`ThirdPersonExampleMap` (ou qualquer nível com um ator no mundo) e peça:

> Descreva o objeto `/Game/Maps/ThirdPersonExampleMap.ThirdPersonExampleMap:PersistentLevel.CubeMesh_5`.

✅ **Esperado**: listas de propriedades e funções, com tipos.

Depois, para uma mudança **visível e desfazível** (Ctrl+Z no editor):

> Use `unreal_set_property` para definir `bHidden = true` no mesmo objeto.

✅ **Esperado**: o cubo desaparece na viewport e aparece uma entrada
"Remote Set Object Property" no **Undo History**.

### Resultado

Se os passos 1–3 funcionaram, a Fase 4 está validada no seu PC: a LUMEN
alcança o editor, cria asset e confirma pela API. Anote o que falhou, se
algo falhar — §8 tem as causas.

---

## 5. Fluxo completo (o objetivo original)

Há um fluxo de consulta **conectado ao chat da UI**, mas ele não equivale ao
pipeline completo de geração de uma feature C++/Blueprint.

| Caminho | O que está conectado |
| --- | --- |
| Janela Lumen | O chat usa `app/planner/` e o `ToolCallingBridge` para validar e executar planos JSON. Com os toggles opt-in ligados, o catálogo pode incluir `web_search` e somente `unreal_get_info`, `unreal_search_assets` e `unreal_describe_object`. Os resultados aparecem na conversa. READ continua obrigatória; as quatro tools Unreal mutáveis são excluídas desse caminho. |
| Cliente MCP | Processo separado, configurado nas seções 2–4. A exposição depende das flags MCP e não compartilha aprovações com a janela Lumen. |
| Pipeline completo de feature | Ainda não há um fluxo único do chat que encadeie pesquisa → `FeaturePlanner`/`ApprovalGate` → escrita de C++ → UnrealBuildTool → aplicação de alterações no editor. `app/planning/` não foi usado para substituir o planner da UI. |

O fluxo de consulta pela UI é:

```text
objetivo em linguagem natural
  → planner JSON da UI + catálogo opt-in
  → validação / permissões existentes (READ para consultas)
  → web_search ou consulta Unreal somente leitura
  → saída formatada na conversa
```

A seleção depende do modelo e do catálogo que você ativou. Para pesquisa, a
UI apresenta os títulos, URLs e trechos recebidos; revise as fontes. Uma
consulta Unreal lê informações do editor, assets ou descrição de objeto —
não cria nem altera assets. A ativação dos toggles não concede READ e não
substitui as verificações da execução.

Escrita de arquivos, comandos e operações mutáveis continuam sujeitas às
permissões, workspaces, allowlists e checkpoints do respectivo caminho.
`--auto-approve` vale apenas para o subprocesso MCP e pula sua confirmação
por operação; não o confunda com uma aprovação interativa na UI.

**`unreal_create_blueprint_class` não compila C++.** Ele cria a *classe
Blueprint* e não faz parte do catálogo Unreal read-only do chat. Compilar C++
é uma etapa separada, por exemplo `run_command` com UnrealBuildTool (§6).

---

## 6. Bootstrap no Windows

```powershell
.\bootstrap.ps1 -UnrealProjectPath "C:\MeuProjeto\MeuProjeto.uproject"
```

O que ele faz, em ordem:

1. confere **Python 3.10+**;
2. verifica o repositório existente e tenta `git pull --ff-only` (não faz clone);
3. cria e ativa o **virtualenv** em `.venv`;
4. `pip install -r requirements.txt`;
5. roda o **pytest** e reporta a contagem;
6. confere que o arquivo passado em `-UnrealProjectPath` existe e é `.uproject`;
7. lê o JSON do `.uproject` e verifica se **`RemoteControlAPI`** e
   **`PythonScriptPlugin`** estão habilitados — se não estiverem, diz
   exatamente o que editar;
8. se você passou **`-LaunchUnreal`**, abre o editor;
9. espera a porta **30010** responder;
10. gera o comando e o JSON do MCP; **o cliente MCP inicia o subprocesso** depois que você configura o cliente;
11. imprime `✅ Pronto para uso após configurar o cliente MCP` ou `❌ Falhou na etapa X, motivo Y`.

**O bootstrap NÃO inicia um servidor stdio persistente**, nem habilita
`--auto-approve`. Com `-AllowWrite` e um `.uproject`, o JSON gerado inclui
`--enable-unreal-bridge`, mas operações mutáveis ficam pendentes até você
reiniciar o cliente com `--auto-approve` (consentimento antecipado). Não há
aprovação compartilhada com a UI.

Opções:

| Parâmetro | Para que serve |
| --- | --- |
| `-UnrealProjectPath <arquivo.uproject>` | obrigatório para os passos 6–9 |
| `-LaunchUnreal` | abre o editor automaticamente |
| `-SkipTests` | pula a suíte (bootstrap mais rápido) |
| `-AllowWrite` | inclui escrita no JSON gerado (não aprova checkpoints nem inicia servidor) |

Se você não passar `-UnrealProjectPath`, ele **pergunta** (`Read-Host`) em
vez de adivinhar um caminho.

---

## 7. Por que criar Blueprint precisa de Python

Esta é a limitação central da Fase 4, e ela não tem contorno:

**A Remote Control API não tem rota para criar assets.** A lista completa
de rotas é a que aparece em `/remote/info`:
`/remote/info`, `/remote/object/call`, `/remote/object/property`,
`/remote/object/describe`, `/remote/object/thumbnail`,
`/remote/search/assets`, `/remote/batch`, `/remote/object/event`. Não
existe `/remote/asset/create` — nenhuma.

O que **funciona** com a RC API pura:

| Ferramenta | Rota | Observação |
| --- | --- | --- |
| `unreal_get_info` | `GET /remote/info` | |
| `unreal_describe_object` | `PUT /remote/object/describe` | |
| `unreal_search_assets` | `PUT /remote/search/assets` | |
| `unreal_set_property` | `PUT /remote/object/property` | propriedade precisa ser pública, sem `BlueprintGetter`/`BlueprintSetter`, e `EditAnywhere` (editor) ou `BlueprintVisible` (PIE) |
| `unreal_call_function` | `PUT /remote/object/call` | função precisa ser **chamável por Blueprint** |

**Limite do planner da UI:** nessa integração, apenas `unreal_get_info`,
`unreal_search_assets` e `unreal_describe_object` são registradas. As quatro
tools de mutação abaixo continuam fora do catálogo/registry read-only da UI,
mesmo se a permissão WRITE existir. O caminho MCP é separado e segue as
flags/permissões descritas nas seções 2–4.

O que **exige Python no editor**:

| Ferramenta | Por quê |
| --- | --- |
| `unreal_create_blueprint_class` | não existe rota para criar asset |
| `unreal_add_component` | não existe rota para editar grafo de Blueprint |

Essas duas executam `ExecutePythonCommandEx` na biblioteca do Python
Editor Script Plugin (`/Script/PythonScriptPlugin.Default__PythonScriptLibrary`).
São exatamente os dois portões de §1.3.

**O que ainda não foi validado [NÃO VALIDADO]:** os scripts Python gerados
foram escritos contra a API pública do módulo `unreal` e contra o padrão
usado pelos projetos pesquisados na Fase -1, mas **nunca rodaram dentro de
um Unreal real** — não havia Unreal no ambiente de desenvolvimento. Podem
precisar de ajuste:

- nomes exatos dos métodos de `BlueprintEditorLibrary` (mudaram entre 5.0 e
  5.5);
- se `add_component` exige o editor de Blueprint aberto para persistir;
- o formato exato do dicionário devolvido por `ExecutePythonCommandEx`.

Quando alguma dessas ferramentas roda, ela devolve
`needs_manual_validation: true` na saída — de propósito, para que o
resultado não pareça mais firme do que é. Os scripts ficam no
`Output Log` do editor (aba `Output Log`, filtro `LogPython`), com o
prefixo `LUMEN:` nas mensagens. **É lá que você confirma o que aconteceu de
verdade.**

---

## 8. Troubleshooting

### 8.1 Conexão com a porta 30010

| Sintoma | Causa provável | O que fazer |
| --- | --- | --- |
| Sem resposta em `http://127.0.0.1:30010` | editor fechado, ou servidor web não subiu | no console do editor (`` ` ``): `WebControl.StartServer` |
| Sem resposta, editor aberto | plugin **Remote Control API** não habilitado | `Edit` → `Plugins` → habilitar → reiniciar |
| `404` em `/remote/object/call` | plugin Remote Control API não habilitado | idem acima |
| Funciona no navegador, falha no agente | `--workspace` ou `cwd` errados na config do cliente | confira §3.3; barra invertida **dupla** no JSON |
| `Connection refused` no `unreal_get_info` | porta diferente da configurada | veja `RemoteControlHttpServerPort` em `DefaultRemoteControl.ini` e ajuste `LUMEN_UNREAL_RC_PORT` |

### 8.2 Execução de Python (as duas mensagens que confundem)

| Erro no log do editor | Portão que falta |
| --- | --- |
| `Object Default__PythonScriptLibrary cannot be accessed remotely` | falta **`bEnableRemotePythonExecution=True`** |
| `Executing function 'ExecutePythonCommandEx' is not allowed by remote control settings` | falta a entrada em **`+CustomAllowedRemoteFunctionCalls`** |
| `NameError: name 'unreal' is not defined` | **Python Editor Script Plugin** não habilitado |
| Alterou o `.ini` e nada mudou | não reiniciou o editor |

Os dois primeiros são **portões diferentes** e dão erros diferentes. Se você
corrigir um e o outro aparecer, é progresso, não retrocesso. Lembre que o
arquivo é **`DefaultRemoteControl.ini`**, não `DefaultEngine.ini`.

### 8.3 Objetos, propriedades e funções

| Sintoma | Causa provável |
| --- | --- |
| `Unable to find object` / path não resolve | caminho errado, ou o ator **não está carregado no editor** |
| Em PIE, o path não funciona | atores em PIE vivem sob o pacote `UEDPIE_0_` — use o caminho que o editor reporta |
| Propriedade recusada na escrita | é `private`/`protected`, tem `BlueprintGetter`/`BlueprintSetter`, ou não é `EditAnywhere`/`BlueprintVisible` |
| Função recusada | não é **chamável por Blueprint** (`BlueprintCallable`) |
| Nome não encontrado | nomes em C++ divergem dos rótulos do Blueprint — use `unreal_describe_object` |

### 8.4 Servidor MCP e cliente

| Sintoma | Causa provável |
| --- | --- |
| Cliente não lista nenhuma ferramenta | faltam `--allow-read`/`--allow-write`: sem flag, o servidor expõe zero |
| "Ferramenta X não está exposta" | ela é destrutiva e você não passou `--allow-write` |
| "⏸ aguardando aprovação" | comportamento **correto**: este processo MCP não compartilha a UI; para testar escrita, reinicie o cliente com `--auto-approve` **depois de revisar o risco** |
| Escrita bloqueada mesmo com `--allow-write` | permissão `WRITE` não foi concedida — expor ≠ conceder |
| Cliente não vê o servidor | `claude_desktop_config.json` só é lido na inicialização: feche o Claude **por completo** e reabra |
| JSON inválido na config | barra invertida simples no Windows — use `\\` |
| Nada funciona e o log está vazio | rode o comando à mão (§2.2); os erros aparecem no **stderr** |

### 8.5 Pesquisa web

| Sintoma | Causa provável |
| --- | --- |
| `web_search` não aparece | sem `TAVILY_API_KEY`/`BRAVE_API_KEY` no `.env`, ou `LUMEN_SEARCH_PROVIDER` apontando para o outro |
| "chave ausente" na resposta | chave não carregada — confira o `.env` na **raiz do repositório** |
| 401/403 do provedor | chave inválida, expirada ou sem crédito |

### 8.6 Como pedir ajuda

Antes de abrir uma issue, junte:

1. a saída de `python --version` e `python -m app.mcp_server --version`;
2. o resultado de `Invoke-RestMethod http://127.0.0.1:30010/remote/info`;
3. o **stderr** do servidor MCP (é onde os logs saem — o stdout é reservado
   ao protocolo);
4. as últimas linhas do `Output Log` do Unreal, filtrando por `LUMEN:` e
   `LogRemoteControl`.

Isso cobre 90% dos casos sem ida e volta.

---

## 9. Referências

- Remote Control API — HTTP: <https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-api-http-reference-for-unreal-engine>
- MCP — transporte stdio: <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>
- MCP — ciclo de vida: <https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle>
- MCP — ferramentas: <https://modelcontextprotocol.io/specification/2025-06-18/server/tools>
- Projetos MCP-Unreal pesquisados (Fase -1): [`PESQUISA_MCP_EXISTENTES.md`](PESQUISA_MCP_EXISTENTES.md)
