# PESQUISA — Projetos MCP + Unreal Engine existentes

**Data:** 2026-10-08
**Fase:** -1 (pesquisa e decisão arquitetural)
**Objetivo:** decidir entre reutilizar um projeto open-source maduro ou implementar do zero.

---

## 1. Panorama encontrado

Busca via API do GitHub (`search/repositories?q=unreal+mcp&sort=stars`) e web. Foram identificados **mais de 20 repositórios**. Classificados em duas famílias arquiteturais conforme **como se conectam ao Unreal**:

### Família A — Exigem plugin C++ customizado compilado no projeto

| Repo | ★ | Licença | Linguagem | Último push |
| --- | --- | --- | --- | --- |
| `chongdashu/unreal-mcp` | 2091 | **NENHUMA** | C++ + Python | 2025-04-22 |
| `ChiR24/Unreal_mcp` | 909 | MIT | C++ + TypeScript | **2026-10-08** |
| `kvick-games/UnrealMCP` | 613 | **NENHUMA** | C++ + Python | 2025-06-22 |
| `db-lyon/ue-mcp` | 385 | MIT | C++ + TS | **2026-10-08** |
| `tumourlove/monolith` | 325 | MIT | C++ | 2026-09-09 |
| `GenOrca/unreal-mcp` | 145 | Apache-2.0 | C++ + **Python** | 2026-07-07 |
| `DeVoe09/UnrealMCP` | — | MIT | C++ | — |

### Família B — Sem plugin C++ (usam plugins que já vêm com o engine)

| Repo | ★ | Licença | Linguagem | Último push |
| --- | --- | --- | --- | --- |
| `remiphilippe/mcp-unreal` | 75 | Apache-2.0 | **Go** | 2026-02-20 |
| `runreal/unreal-mcp` | 116 | MIT | Python | 2025-06-06 |
| `edi3on/py-ue5-mcp-server` | 8 | MIT | Python | 2025-07-17 |
| `FFZackFair92/unreal-engine-mcp` | 5 | MIT | Python | 2026-08-24 |
| `sam-david/unreal-mcp` | 7 | **NENHUMA** | TypeScript | 2026-03-28 |

---

## 2. Top 3 analisados em detalhe

### 2.1 `ChiR24/Unreal_mcp` — 909★ · MIT · ativo hoje

- **Link:** https://github.com/ChiR24/Unreal_mcp
- **Linguagem:** TypeScript (servidor MCP) + C++ (plugin "MCP Automation Bridge")
- **Conexão com o Unreal:** três caminhos — (a) HTTP/WebSocket para o **plugin C++ rodando dentro do editor** na porta 8091; (b) **Remote Control API** porta 30010 para propriedades/funções; (c) `UnrealEditor-Cmd` headless para build/test/cook.
- **Tools expostas:** superfície enorme — assets, actors, níveis, PIE, animação, Niagara, Sequencer, edição de grafos de Blueprint/Material/Behavior Tree, UBT, CVars. Expostas como **um único tool "gateway" `unreal`** com 4 operações (search/describe/execute/configure) sobre 23 tools pai.
- **Manutenção:** **muito ativo** (push em 2026-10-08), 17 issues abertas, versões de UE 5.0–5.8.
- **Licença:** **MIT** — compatível para reuso.
- **⚠️ Bloqueio para nós:** exige compilar um **plugin C++** no projeto Unreal e é **TypeScript**. Reutilizar como base significaria abandonar Python e injetar uma dependência de build C++ no bootstrap.

### 2.2 `GenOrca/unreal-mcp` — 145★ · Apache-2.0 · Python

- **Link:** https://github.com/GenOrca/unreal-mcp
- **Linguagem:** **Python** (servidor MCP, `mcp-server/src/unreal_mcp/`) + C++ (plugin)
- **Estrutura confirmada:** `Plugins/`, `UnrealMCPSample.uproject`, `mcp-server/pyproject.toml`, `setup.py`, `LICENSE`
- **Conexão:** plugin C++ + bridge; o servidor roda via `uv --directory <path> run src/unreal_mcp/main.py`
- **Tools:** ~253 ações em 21 domínios (actor, blueprint, material, umg, gas, niagara, level_sequence, behavior_tree…)
- **Manutenção:** moderada (último push 2026-07-07), 4 issues
- **Licença:** **Apache-2.0** — compatível
- **⚠️ Bloqueio para nós:** **também exige o plugin C++** (`UnrealMCPSample.uproject` + `Plugins/`). É a opção mais próxima da nossa stack (Python), mas ainda traz o custo de compilar C++ dentro do projeto do usuário.

### 2.3 `chongdashu/unreal-mcp` — 2091★ · **SEM LICENÇA**

- **Link:** https://github.com/chongdashu/unreal-mcp
- **Linguagem:** C++ (plugin) + Python (FastMCP)
- **Conexão:** **TCP socket customizado na porta 55557** para o plugin C++ — **não usa a Remote Control API**
- **Tools:** atores, Blueprints (criar classe, adicionar componentes, nós de grafo, variáveis), input mappings, viewport
- **Manutenção:** **abandonado** — último push 2025-04-22 (~18 meses), 41 issues abertas
- **Licença:** ❌ **NENHUMA.** Verificado via `gh api repos/chongdashu/unreal-mcp` → `license` vazio, e `contents/` não contém arquivo `LICENSE`. O README exibe um badge "MIT", mas **não há arquivo de licença** no repositório. **Juridicamente inutilizável para reuso** — sem licença explícita, todos os direitos são reservados por padrão.
- **Nota:** é o projeto mais popular da categoria, e é justamente o que NÃO podemos usar.

### 2.4 Menções relevantes

- `remiphilippe/mcp-unreal` (75★, Apache-2.0, Go) — arquitetura de referência interessante: separa **headless** (UBT via `exec.Command`, sem editor) de **editor** (RC API 30010 + plugin 8090). Último push 2026-02-20.
- `kvick-games/UnrealMCP` (613★) — **sem licença**, abandonado 2025-06.
- `kvnloo` / `kvgosu` forkam o ChiR24 e adicionam Rust/WASM ou auth por capability token.
- `FFZackFair92/unreal-engine-mcp` (5★, MIT, Python) — arquitetura **idêntica** à que vamos adotar (RC API + Python, "no C++ plugin to compile"), mas é novo e pequeno (criado 2026-07-28). Serve como **validação independente** de que o caminho sem plugin é viável.

---

## 3. Achado técnico decisivo

> ### ⚠️ A Remote Control API **sozinha não cria Blueprints, Actors nem Componentes.**

Verificado na **documentação oficial** (Remote Control API HTTP Reference — https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-api-http-reference-for-unreal-engine). As rotas existentes são **exatamente**:

| Rota | Verbo | O que faz |
| --- | --- | --- |
| `/remote/info` | GET | lista as rotas disponíveis |
| `/remote/object/call` | PUT | chama UFUNCTION `BlueprintCallable` de um UObject **já em memória** |
| `/remote/object/property` | PUT | lê/escreve propriedades (`READ_ACCESS`/`WRITE_ACCESS`/`WRITE_TRANSACTION_ACCESS`) |
| `/remote/object/describe` | PUT | introspecção (reflexão) de um objeto |
| `/remote/search/assets` | PUT | busca assets |
| `/remote/object/thumbnail` | PUT | thumbnail de asset |
| `/remote/object/event` | PUT | dispara evento |
| `/remote/batch` | PUT | agrupa várias chamadas |

**Não existe rota para criar assets.** Criar um Blueprint exige `FKismetEditorUtilities::CreateBlueprint` (C++) ou `unreal.AssetToolsHelpers.get_asset_tools().create_asset()` (**Python**), executado **dentro** do editor.

**Consequência arquitetural:** para cumprir os tools pedidos na Fase 4 —

- `unreal_set_property` → ✅ **RC API pura** (`/remote/object/property`, `WRITE_TRANSACTION_ACCESS`)
- `unreal_call_function` → ✅ **RC API pura** (`/remote/object/call`, `generateTransaction: true`)
- `unreal_create_blueprint_class` → ⚠️ **RC API + Python** via `ExecutePythonCommandEx`
- `unreal_add_component` → ⚠️ **RC API + Python** via `ExecutePythonCommandEx`

O caminho "RC API + Python" é exatamente o que os projetos da **Família B** documentam e o que a Epic suporta sem compilar C++. Ele exige **dois portões de configuração** distintos, que falham com erros diferentes:

```ini
; Config/DefaultRemoteControl.ini  (NÃO DefaultEngine.ini — a classe é UCLASS(config = RemoteControl))
[/Script/RemoteControlCommon.RemoteControlSettings]
bAutoStartWebServer=True
RemoteControlHttpServerPort=30010
bEnableRemotePythonExecution=True
bAllowAnyRemoteFunctionCall=False
+CustomAllowedRemoteFunctionCalls=(ClassPath="/Script/PythonScriptPlugin.PythonScriptLibrary")
```

---

## 4. DECISÃO

> ### ✅ Implementar do zero em Python — adotando a arquitetura "Remote Control API + Python Editor Script Plugin" como **referência validada**.

### Por que NÃO usar nenhum projeto como base

1. **Incompatibilidade de stack.** Os projetos maduros são **TypeScript** (ChiR24, db-lyon) ou **Go** (remiphilippe). O único Python (GenOrca) ainda assim requer **plugin C++**. O LUMEN é Python puro, com arquitetura de permissões/sandbox/checkpoint própria — adotar outra stack significaria reescrever a integração de segurança, que é o ativo mais valioso do LUMEN.
2. **Bloqueio de licença no mais popular.** O `chongdashu/unreal-mcp` (2091★) **não possui licença**. Reusar código sem licença explícita é juridicamente inviável.
3. **Custo de build C++.** ChiR24, db-lyon, tumourlove, GenOrca e DeVoe09 exigem **compilar um plugin C++ dentro do projeto do usuário**. Isso adiciona ao bootstrap uma dependência de toolchain Visual Studio + UBT — exatamente a complexidade que o objetivo desta tarefa pede para evitar ("bootstrap automatizado que o usuário roda no Windows").
4. **Requisito de auditabilidade.** Precisamos de uma ponte **fina, legível e auditável** que se integre ao modelo de permissões do LUMEN (checkpoint antes de operações destrutivas, auditoria JSONL, `PermissionLevel.COMPUTER_CONTROL` inconcedível). Nenhum projeto existente oferece esse encaixe.

### Por que a arquitetura deles é reaproveitada como referência

O conhecimento de protocolo é o ativo real, e ele está **publicamente documentado** (confirmado de forma independente por `FFZackFair92`, `sam-david`, `remiphilippe` e pela doc oficial da Epic):

- endpoints exatos e verbos (`/remote/object/call`, `/remote/object/property`, `/remote/info`);
- a obrigatoriedade de `Config/DefaultRemoteControl.ini` (e não `DefaultEngine.ini`);
- os **dois gates separados** de permissão Python remota;
- a estratégia de **degradação graciosa** (servidor sobe mesmo sem editor conectado);
- a separação **headless (UBT) vs editor (RC API)**.

Nada de código é copiado — apenas o desenho de protocolo, que é público.

### Consequência para a Fase 4

Implementar `app/unreal_bridge/` com:
1. Cliente HTTP RC API puro (stdlib `urllib`, sem dependência nova);
2. Camada Python-exec opcional via `ExecutePythonCommandEx` para as operações que a RC API não alcança;
3. Ferramenta de build headless (UBT) separada e explicitamente marcada como não validada;
4. **Marcação explícita no código** de quais chamadas exigem validação manual contra um Unreal real.

---

## 5. Fontes

- Remote Control API HTTP Reference (Epic, oficial) — https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-api-http-reference-for-unreal-engine
- Remote Control API WebSocket Reference (Epic, oficial) — https://dev.epicgames.com/documentation/unreal-engine/remote-control-api-websocket-reference-for-unreal-engine
- Remote Control Quick Start (Epic, oficial) — https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-quick-start-for-unreal-engine
- MCP Specification 2025-06-18 — Lifecycle — https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
- MCP Specification 2025-06-18 — Tools — https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- GitHub Search API: `q=unreal+mcp&sort=stars` (executado em 2026-10-08)
