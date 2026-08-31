# Arquitetura da Lumen — versão 0.6.x (0.6.3)

Este documento descreve a arquitetura da Lumen após a 0.2 (Cérebro
Real), a 0.3/0.3.x (Memória + Providers), a 0.4/0.4.x (Planner +
Executor), a 0.5 (Filesystem Tools), a 0.5.x (UI de Workspaces,
Permissões, Checkpoints e Auditoria — §16), a 0.6 (Terminal Tools —
§17), a 0.6.x (UI de Terminal/Allowlist/Concessão TERMINAL — §17.4), a
0.4.x (Correção Automática Controlada — §18) e a 0.6.3 (Tool Calling /
Planner Bridge — §19):
camadas, fluxo de mensagens, camada de provedores de IA,
persona/system prompt, política de erros/timeout/retry, persistência,
segurança e pontos de extensão.

---

## 1. Princípio fundamental

A Lumen é um **sistema modular em camadas**. A lógica nunca vive na
interface gráfica, e a implementação de um provedor específico de IA
nunca se espalha pelo restante do código. Cada camada evolui
independentemente:

```text
UI (Tkinter)
 ↓
AGENT CORE
 ↓
AI PROVIDER (abstrato)      MEMORY      TASK SYSTEM
                             ↕               ↕
                          TOOLS  →  PERMISSIONS
```

Regra de dependências: **setas apontam para baixo**. A UI não conhece
provedores; o Agent Core não conhece Tkinter; ferramentas nunca são
executadas sem permissão.

## 2. Mapa de módulos

| Camada | Módulo | Responsabilidade |
| ------ | ------ | ---------------- |
| UI | `app/ui/main_window.py` | Janela, widgets, status, streaming via fila + botão ⚙ Configurações. Só apresentação. |
| UI | `app/ui/settings_dialog.py` | Diálogo "Configurações → Inteligência Artificial" (provider/modelo/API Key). |
| UI | `app/ui/tools_dialog.py` | **0.5.x:** diálogo "🛡 Ferramentas e Segurança" (workspaces, permissões, aprovação de checkpoints, auditoria; **0.6.2:** card de correção proposta) — só apresentação; lógica no `ToolsController`. |
| Agent Core | `app/core/agent.py` | `Agent.send_message()`: permissão → contexto → provedor (system prompt + streaming) → memória; **`Agent.request_plan()`** (0.4): pedido → Planner → `Plan` (sem execução); **0.6.3**: `process_message()` decide conversa × ação, `request_tool_plan()` e `set_tools_controller()` (ponte §19). |
| Planner | `app/planner/` | **0.4 — fundação:** `Planner.create_plan()` → `Plan`/`PlannedTask` (ordem, dependências, análise prévia, `PlanStatus`); validação strict de JSON; falha controlada; memória 0.3 como leitura; **0.6.3:** `create_tool_plan()` + `catalog.py` (allowlist de protocolo) emitem `tool`/`parameters` validados; **não executa nada**. |
| Executor | `app/executor/` | **0.4.x:** `PlanExecutor` executa um plano READY respeitando ordem/dependências, com `step()`/`run_all()`, fail-fast (restantes `SKIPPED`), `TaskRun`/`ExecutionReport` + eventos, checkpoints/retry/verificação; **0.6.2:** `CorrectionEngine` (§18) — ciclo de correção com limites rígidos, planos sucessores imutáveis e estados separados. Separado do Planner e **agnóstico de ferramentas** (a ponte com tools reais é o `ToolTaskHandler`, na camada de tools). |
| AI Provider | `app/ai/provider.py` | ABC `AIProvider` (`chat`/`generate`), taxonomia de erros, fábrica `create_provider()`. |
| AI Provider | `app/ai/openai_provider.py` | `OpenAIProvider` — SDK oficial (import lazy), timeout/retry/streaming. |
| AI Provider | `app/ai/gemini_provider.py` | `GeminiProvider` — SDK oficial `google-genai` (import lazy), adaptador dict→config, timeout em ms, modelo padrão GA. |
| AI Provider | `app/ai/groq_provider.py` | `GroqProvider` — SDK oficial `groq` (lazy), herda o núcleo do `OpenAIProvider`, padrão `openai/gpt-oss-120b` (0.3.x). |
| AI Provider | `app/ai/together_provider.py` | `TogetherProvider` — SDK oficial `together` (lazy), Llama 4 real, padrão `meta-llama/Llama-4-Scout-17B-16E-Instruct` (0.3.x). |
| AI Provider | `app/ai/mock.py` | `MockProvider` — simulador offline determinístico. |
| AI Provider | `app/ai/types.py` | `AIResponse`, `Usage`, `ResponseType` (normalização + preparação para agente). |
| Config | `app/config/settings.py` | `Settings` (leitor `.env` próprio) + `setup_logging()` com redação de segredos. |
| Config | `app/config/persona.py` | Identidade central (nome, gênero, papel, idioma) + `build_system_prompt()`. |
| Config | `app/config/user_config.py` | Configuração **não secreta** salva pela UI (`data/settings.json`) + precedência GUI > ambiente > `.env`. |
| Config | `app/config/secrets.py` | Cofre de credenciais: `keyring` (Windows Credential Manager) com fallback em arquivo restrito. |
| Config | `app/config/config_service.py` | `ConfigService`: valida/salva/aplica config no Agent, remove chave, testa conexão (requisição mínima). |
| Memory | `app/memory/store.py` | `MemoryStore`/`Message` — histórico de conversa JSON, escrita atômica, thread-safe, busca acento-insensível (0.3). |
| Memory | `app/memory/sanitization.py` | `redact_secrets`/`contains_secret` — segredos (API keys, tokens, senhas) redigidos **antes** de persistir na memória estruturada. |
| Memory | `app/memory/records.py` | `MemoryRecord` (frozen dataclass: id, kind, título, conteúdo, origem, status, timestamps, tags, project_id, related_ids, supersedes, content_hash), `MemoryKind` (6 domínios), `RecordStatus`, IDs por domínio (`PRJ-`, `TASK-`, `KN-`, `DEC-`, `ERR-`, `SOL-0001`). |
| Memory | `app/memory/record_store.py` | `RecordStore` — persistência JSON atômica por domínio, thread-safe; deduplicação por hash entre ACTIVE, `update` imutável, `mark_obsolete`, `supersede` (trilha), `search` por relevância (título 3 > tag 2 > conteúdo 1, +1 todos os termos, obsoletos ×0,2). |
| Memory | `app/memory/system.py` | `MemorySystem` — fachada: conversa (0.1) + 6 domínios; `remember`/`update`/`mark_obsolete`/`supersede`/`recall`/`relate`/`stats` e **`build_context(query)`** (gancho para o fluxo futuro do Agent). |
| Task System | `app/tasks/manager.py` | `TaskManager`/`Task`/`TaskStatus` — registro de tarefas (sem execução). |
| Tools | `app/tools/base.py` | ABC `Tool` + `ToolResult`/`StructuredTool` + `ToolRegistry` (porteiro de permissões). |
| Tools | `app/tools/filesystem.py` | **0.5:** `WorkspaceSandbox` (raízes autorizadas, bloqueio de `..`/fora/symlink, modo escrita/exclusão), `FilesystemAudit` (trilha sem conteúdo) e as 6 ferramentas: `list_directory`/`read_file`/`write_file`/`create_file`/`delete_file`/`file_exists`. |
| Tools | `app/tools/handler.py` | **0.5:** `ToolTaskHandler` (ponte Executor→ToolRegistry; tarefa com `tool`/`parameters`) + `ToolCheckpoints` (checkpoint antes de ferramentas destrutivas). |
| Tools | `app/tools/workspaces.py` | **0.5.x:** `WorkspaceEntry`/`WorkspaceStore` (workspaces autorizados, `data/workspaces.json` atômico, validação/normalização, raiz de disco rejeitada) + `MultiWorkspaceSandbox` (política por raiz). |
| Tools | `app/tools/audit_log.py` | **0.5.x:** `JsonlAuditSink` (persistência JSONL da auditoria) + `read_audit_tail` (leitura tolerante). |
| Tools | `app/tools/control.py` | **0.5.x/0.6:** `ToolsController` — fachada UI (permissões CHAT/READ/WRITE, workspaces, execução com `PrevalidatedCheckpoints`, auditoria, `enable_terminal` com allowlist); `PrevalidatedCheckpoints`: checkpoint só para operações viáveis. |
| Tools | `app/tools/terminal.py` | **0.6:** `TerminalPolicy` (allowlist explícita + denylist permanente + timeout/limite de saída + validação de argumentos/cwd), `AllowedCommand`/`ValidatedCommand`, `RunCommandTool` (`run_command`, permissão `TERMINAL`) e `PrevalidatedTerminalCheckpoints` — o **único** módulo com `subprocess`. |
| Permissions | `app/security/permissions.py` | `PermissionLevel` (CHAT→COMPUTER_CONTROL), `PermissionManager`. |
| Entrada | `main.py` | Composition root: settings → logging → provedor → memória → tarefas → permissões → Agent → UI. |

Erros tipados: `ConfigError`, `AgentError`, `MemoryStoreError`,
`RecordError` (modelo) e `RecordStoreError`/`RecordNotFoundError`/
`DuplicateRecordError` (memória estruturada),
`TaskError`/`TaskNotFoundError`, `ToolError`/`ToolNotFoundError`,
`PermissionDeniedError` e a taxonomia de `ProviderError` (abaixo).

## 3. Camada AI Provider (0.2)

### 3.1 Contrato

```python
class AIProvider(ABC):
    name: str
    model_name: str                     # modelo em uso ("" se não fizer sentido)

    @abstractmethod
    def generate(self, message, context=None) -> str: ...   # API simples (0.1)

    def chat(self, message, context=None, *, system_prompt=None,
             on_delta=None) -> AIResponse: ...               # API rica (0.2)
```

- `generate` — mantida da 0.1 (devolve `str`); provedores simples só
  implementam essa.
- `chat` — API rica: recebe **system prompt** e histórico, suporta
  **streaming** via callback `on_delta(pedaço)` e devolve uma resposta
  **normalizada**. A implementação padrão embrulha `generate`.
- `on_delta` é **dirigido pelo chamador**: a UI passa o callback quando
  quer streaming; o provedor transmite pedaços se souber (OpenAI usa
  `stream=True`) e a soma dos pedaços equivale ao conteúdo final.

### 3.2 Resposta normalizada (`app/ai/types.py`)

```python
AIResponse(content, model, usage, finish_reason, response_type, tool_calls=())
Usage(input_tokens, output_tokens, total_tokens)
ResponseType.FINAL_RESPONSE | TOOL_CALL | PLAN
```

Nem o Agent Core nem a UI dependem do formato de uma API específica.
`ResponseType` + `tool_calls` são a **preparação para o agente futuro**
(0.4+): uma resposta poderá representar uma chamada de ferramenta ou um
plano **sem reescrever o Agent Core**. Na 0.2 todo provedor retorna
apenas `FINAL_RESPONSE` com `tool_calls` vazio — tool calling real NÃO
está implementado.

### 3.3 Taxonomia de erros e retry

| Erro | Situação | Retry? |
| ---- | -------- | ------ |
| `MissingApiKeyError` | `LUMEN_API_KEY` vazia com provedor real | nunca |
| `ModelNotConfiguredError` | `LUMEN_MODEL` vazio com provedor real | nunca |
| `InvalidModelError` | modelo rejeitado/não encontrado (404/BadRequest) | nunca |
| `ProviderAuthError` | chave inválida/sem autorização (401/403) | nunca |
| `ProviderRateLimitError` | limite de uso (429) | sim |
| `ProviderTimeoutError` | excedeu `LUMEN_REQUEST_TIMEOUT` | sim |
| `ProviderNetworkError` | falha de rede/conexão | sim |
| `ProviderServerError` | erro interno do provedor (5xx) | sim |
| `ProviderDependencyError` | SDK `openai` não instalado | nunca |
| `UnexpectedProviderError` | não classificado | nunca |

Política: **1 tentativa + `LUMEN_MAX_RETRIES`** (default 2) com backoff
curto crescente, apenas para as linhas "sim". O SDK oficial é criado
com `max_retries=0` — o retry é nosso, visível e testável. Exceção do
SDK são classificadas por tipo/isinstance quando disponível ou por
nome/status_code (torna o mapeamento testável sem o SDK instalado).
**Streaming:** se uma tentativa falhar *após* emitir deltas ao usuário,
não há retry (evitaria texto duplicado na tela).

### 3.4 Fábrica de provedores

`create_provider(settings)` é o único ponto que conhece nomes concretos:

```python
_PROVIDER_REGISTRY = {
    "mock": "app.ai.mock.MockProvider",
    "openai": "app.ai.openai_provider.OpenAIProvider",
    "gemini": "app.ai.gemini_provider.GeminiProvider",
    "groq": "app.ai.groq_provider.GroqProvider",        # 0.3.x
    "together": "app.ai.together_provider.TogetherProvider",  # 0.3.x
}
```

Novos provedores entram com uma linha aqui + um módulo novo — nada mais
muda.

### 3.5 GeminiProvider (0.2 — complemento)

Integração com a API do Google Gemini usando o **SDK oficial
`google-genai`** (Google GenAI SDK, GA — o legado `google-generativeai`
está deprecated; o endpoint OpenAI-compat do Gemini foi avaliado, mas o
caminho recomendado oficialmente é o SDK nativo, com erros/usage mais
fiéis — e a arquitetura de providers da Lumen já previa a adição sem
mudanças no núcleo).

- **Chamadas**: `client.models.generate_content(_stream)(model, contents,
  config)`; o provider fala com uma interface própria em dict
  (`config={"system_instruction", "max_output_tokens"}`) e a factory
  padrão envolve o SDK real em um adaptador (`_SdkAdapter`) que converte
  dict → `types.GenerateContentConfig` e **timeout de segundos para
  milissegundos** (unidade do `HttpOptions` do SDK).
- **Histórico**: roles mapeadas para o formato nativo
  (`assistant` → `model`, `parts/text`); system prompt via
  `system_instruction`.
- **Modelo padrão**: `gemini-2.5-flash` quando `LUMEN_MODEL` vazio —
  escolha baseada na documentação oficial atual (GA estável, melhor
  preço/desempenho para conversa com raciocínio/programação); qualquer
  modelo pode ser configurado (ex.: `gemini-2.5-pro`).
- **Usage**: `usage_metadata` preservado (input=`prompt_token_count`,
  output=`candidates_token_count`, total=`total_token_count`).
- **Erros**: mesma taxonomia da §3.3 — `ClientError.code` 401/403 →
  auth; **400 com "API key" → auth** (o Gemini usa 400 p/ chave
  inválida); 429 → rate limit; 404/400+modelo → modelo inválido;
  `ServerError`/5xx → servidor; nomes com Timeout/Deadline → timeout;
  Connection → rede.
- **Retry/streaming**: mesma política do OpenAIProvider (retry só para
  temporários, nunca após deltas emitidos; streaming via
  `generate_content_stream`).

### 3.6 GroqProvider (0.3.x — expansão de providers)

Integração com a **GroqCloud** usando o **SDK oficial `groq`**
(introspectado na versão 1.7.0: interface OpenAI-compatível —
`Groq(api_key, timeout, max_retries)` e `chat.completions.create(model,
messages, stream, max_tokens, timeout)`; exceções com os mesmos
nomes/status do SDK `openai`). Por isso a classe **herda o núcleo
testado do `OpenAIProvider`** (payload, timeout, retry, streaming,
normalização, mapeamento de erros — zero duplicação) e implementa o que
é próprio: fábrica de client (import lazy + `max_retries=0`), modelo
**opcional** com padrão e mensagens de configuração.

- **Modelo padrão**: `openai/gpt-oss-120b` quando `LUMEN_MODEL` vazio —
  modelo de produção em destaque no catálogo oficial da GroqCloud
  (2026-08): 131k de contexto, raciocínio configurável e tool calling
  (conversa/programação/agente). Alternativas de produção:
  `openai/gpt-oss-20b`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`.
- **API Key**: mesma `LUMEN_API_KEY`/cofre; chave em console.groq.com/keys.
- **Sonda TESTAR CONEXÃO**: sem `max_tokens` (gpt-oss raciocina; limite
  mínimo geraria resposta vazia/falso negativo) — política já usada com
  o Gemini para provedores não-openai.

### 3.7 TogetherProvider (0.3.x — Llama 4 real)

Integração com a **Together AI** usando o **SDK oficial `together`**
(introspectado na versão 2.32.0: `Together(api_key, timeout,
max_retries)` e `chat.completions.create(...)` com `max_tokens`/`stream`/
`timeout` por requisição). Mesma decisão de herança do §3.6.

- **Por que Together AI** (decisão registrada): o pedido original era a
  "Meta Llama API", mas a Meta **encerrou o Llama API Public Preview em
  06/07/2026** (llama.developer.meta.com/docs/llama-api-deprecation — a
  API devolve apenas resposta de encerramento; o SDK `llama-api-client`
  aponta para o endpoint morto). Modelos Llama permanecem via hosts de
  terceiros: a **Cerebras removeu todos os Llama do catálogo público**
  (Maverick 10/2025, Scout 11/2025, `llama-3.3-70b` 02/2026,
  `llama3.1-8b` 05/2026 — restam `gpt-oss-120b`/`gemma-4-31b`), e a
  Together AI mantém o **Llama 4** em API pública. O serviço hospedado
  atual da Meta (Model API, `api.meta.ai`, modelos Muse Spark) **não é
  Llama** e não foi implementado.
- **Modelo padrão**: `meta-llama/Llama-4-Scout-17B-16E-Instruct`
  (LUMEN_MODEL vazio) — Llama 4 Scout (109B total/17B ativos, MoE),
  indicado pela Together para análise multi-documento e raciocínio sobre
  codebase, com function calling e custo menor. Alternativa:
  `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8` (flagship
  400B/17B ativos).
- **API Key**: mesma `LUMEN_API_KEY`/cofre; chave em api.together.ai.

## 4. Persona e system prompt

`app/config/persona.py` é o **único** lugar com a identidade da Lumen:

```python
Persona(name="Lumen", gender="feminina",
        role="assistente pessoal de desenvolvimento",
        language="português do Brasil")
```

`build_system_prompt()` compõe seções curtas: identidade (nome,
assistente feminina), papel, idioma (português por padrão), estilo
(objetiva e colaborativa), honestidade/limitações (nunca fingir ações
executadas; **sem acesso ao computador** nesta versão — sem arquivos,
comandos, mouse, teclado, tela) e futuro (evoluirá para agente, não
prometer capacidades que não tem). O Agent usa esse prompt por padrão;
um `system_prompt` customizado pode ser injetado (testes).

O modelo real controla a conversa — não há respostas artificiais
forçadas (apenas o `MockProvider` simulado tem regras fixas).

## 5. Fluxo de uma mensagem (0.2)

```text
[UI thread]                    [worker thread]                [camadas]
LumenWindow.send()
  ├─ exibe "Você: ..."
  ├─ status ← "● Pensando…"
  └─ thread ──────────────────► Agent.send_message(text, on_delta=emit_delta)
                                   ├─ PermissionManager.require(CHAT)
                                   ├─ MemoryStore.recent(LUMEN_MAX_CONTEXT_MESSAGES)
                                   ├─ MemoryStore.add_message("user", ...)
                                   ├─ AIProvider.chat(msg, histórico,
                                   │     system_prompt=persona, on_delta=emit_delta)
                                   │        ├─ deltas ──► queue ──► UI exibe pedaços
                                   │        └─ AIResponse (content/model/usage/finish)
                                   ├─ (ProviderError → AgentError amigável + log técnico)
                                   └─ MemoryStore.add_message("assistant", ...)
                                 "reply"/"error" ──► queue
_poll_queue() (after ~80ms)
  ├─ "delta" → abre bloco "Lumen:" e anexa o pedaço
  ├─ "reply" → fecha o bloco (ou exibe a resposta inteira, sem streaming)
  └─ "error" → exibe "⚠ <mensagem amigável>" e status ● Erro
```

A thread da UI nunca bloqueia; widgets só são tocados pela thread do Tk
(via fila drenada com `after`).

## 6. Configuração gráfica e cofre de credenciais (0.2 — complemento)

A tela **⚙ Configurações → Inteligência Artificial** (`app/ui/settings_dialog.py`)
fala **apenas** com o `ConfigService` — a UI não toca stores, fábrica ou
Agent diretamente.

```text
SettingsDialog (UI)
 └─ ConfigService (app/config/config_service.py)
     ├─ UserConfigStore   → data/settings.json   (provider/model, NÃO secreto)
     ├─ SecretStore       → cofre do SO ou arquivo restrito (API Key)
     ├─ create_provider() → novo AIProvider (validado ANTES de persistir)
     └─ Agent.set_provider() → troca thread-safe, sem reiniciar
```

### 6.1 Precedência de configuração

```
GUI salva (data/settings.json + cofre)  >  ambiente LUMEN_*  >  .env  >  padrões
```

A API Key segue: **cofre → `.env`**. Remover a chave do cofre cai de
volta para a do `.env` (documentado e avisado na UI).

### 6.2 Cofre de segredos (`app/config/secrets.py`)

- Preferencial: **keyring** → no Windows, Credential Manager.
- Fallback (sem keyring/backend): arquivo `data/.credentials.json`
  (0600, escrita atômica, fora do Git) — documentado como fallback.
- Operações: salvar/recuperar/alterar/remover; a chave salva **nunca**
  é exibida de volta na UI (o campo começa vazio; 👁 revela só o que
  está sendo digitado).
- A chave nunca vai para logs, `settings.json` ou o payload do modelo.

### 6.3 Fluxo de salvar (aplicação imediata)

1. `SettingsDialog.save()` → `ConfigService.save(provider, model, key?)`.
2. Validação **antes** de persistir: provider contra o registro;
   `create_provider()` candidato (openai sem chave/modelo → erro
   amigável, nada é salvo).
3. Persiste `settings.json` (não secreto) + chave no cofre (se digitada;
   em branco = manter).
4. `Agent.set_provider()` troca o provider sob `RLock` — `send_message`
   usa um snapshot do provider, portanto a troca é segura mesmo com uma
   resposta em andamento. **Sem reiniciar a aplicação.**

### 6.4 Teste de conexão

`ConfigService.test_connection(provider?, model?, key?)`:

- `mock` → exercita o simulador offline (`🟢 MockProvider funcionando`).
- `openai` → `chat("ping", max_tokens=1)` com `max_retries=0`:
  requisição mínima e barata; valida credencial, modelo, conexão e
  resposta. Modelos que rejeitam `max_tokens` (ex.: série `o`): a
  chamada é repetida automaticamente **uma única vez** sem o parâmetro
  (`_request_plain_compat`) — correção de compatibilidade, não um
  recurso novo.
- `gemini` → `chat("ping")` **sem limite de tokens**: modelos com
  "thinking" podem consumir um orçamento mínimo em raciocínio e devolver
  texto vazio (falso negativo); o custo do prompt "ping" segue ínfimo e
  não há retries.
- Erros → mensagem amigável (`user_message_for`); detalhes técnicos no
  log (tipos/status), **sem segredos**; timeout/rate limit/rede/5xx
  mapeados pela taxonomia da §3.3.
- O teste **nunca altera** a configuração salva (nem quando falha);
  roda em thread própria — a janela não congela.

## 7. Pontos de extensão

### 7.1 Novo provedor de IA

1. Criar `app/ai/xyz_provider.py` herdando `AIProvider` (implementar
   `generate` e, se quiser API rica, sobrescrever `chat`);
2. Registrar em `_PROVIDER_REGISTRY`;
3. Selecionar via `LUMEN_PROVIDER=xyz`.

### 7.2 Evoluir para agente (0.4+)

**Entregue na 0.4 (fundação do Planner):** `Agent.request_plan()` →
`Planner.create_plan()` (ver §13) produz planos estruturados. **Entregue
na 0.4.x (fundação do Executor):** `Agent.execute_plan()` →
`PlanExecutor` (ver §14) executa planos READY. **Entregue na 0.5:** a
conexão com ferramentas reais — `ToolTaskHandler` (ver §15) é um
`TaskHandler` implementado sobre o `ToolRegistry` (porteiro de
permissões) que despacha tarefas com `tool`/`parameters`, completando
`Planner → Executor → ToolRegistry → Tools` sem mudar o núcleo do
Executor. Correção automática real, `TOOL_CALL`/`PLAN` em
`AIResponse.response_type` e a UI de planos/checkpoints continuam
reservados — nada disso existe ainda.

### 7.3 Nova ferramenta (0.5+)

Herdar de `Tool` (name, description, required_permission) — ou de
`StructuredTool` para resultado estruturado (`ToolResult` serializado
em JSON por `execute`) — e registrar no `ToolRegistry`; a execução
continua bloqueada sem a permissão correspondente. Ferramentas com
acesso a recursos reais devem seguir o padrão da 0.5: política de
escopo explícita (ex.: `WorkspaceSandbox`) + trilha de auditoria (ver
§15).

### 7.4 Integrar a memória estruturada ao fluxo do Agent (0.4+)

`MemorySystem.build_context(query)` já existe e devolve os registros
mais relevantes (até `LUMEN_MAX_MEMORY_RECORDS`, excertos ≤400 chars)
para um pedido. A integração futura é: consultar antes de responder,
injetar o contexto no payload e, após a resposta, armazenar o
conhecimento identificável — sem mudar os contratos da memória.

## 8. Persistência

JSON com escrita atômica (`.tmp` + `os.replace`) e locks, inalterada da
0.1 no mecanismo:

### 8.1 Conversa (0.1)

`data/memory/conversation.json` — mensagens com role/content/timestamp.
A conversa cotidiana continua linear, como na 0.1; o que a 0.3 adiciona
é a memória estruturada, separada por domínio.

### 8.2 Memória estruturada (0.3)

`data/memory/{projects,task_records,knowledge,decisions,issues,solutions}.json`
— um `RecordStore` por domínio, criados no primeiro uso. Cada registro
(`MemoryRecord`) tem id sequencial por domínio, timestamps, origem,
status (`ACTIVE`/`OBSOLETE`), tags, `project_id`, `related_ids`,
`supersedes` e `content_hash` (sha256 do título+conteúdo normalizados).
Deduplicação por hash entre ACTIVE (regravável após obsoleto); `update`
é imutável (nova instância + `updated_at`); `supersede` cria o sucessor
apontando o antigo e o marca `OBSOLETE` (trilha de histórico). A busca
pontua título 3 > tag 2 > conteúdo 1 (+1 quando todos os termos casam),
com obsoletos penalizados (×0,2) e excluídos por padrão. **Segredos são
redigidos antes de persistir** (`sanitization.redact_secrets`); arquivo
corrompido/forma inválida gera `RecordStoreError` com mensagem clara.
Tarefas seguem em `data/tasks.json` (inalterado).

## 9. Segurança

- Permissões: por padrão **somente `CHAT`** (READ/WRITE/TERMINAL/
  COMPUTER_CONTROL continuam não concedidas e sem nenhuma tool que as
  use).
- API Key: só no `.env` local (`.gitignore`); nunca em código, nunca em
  log (filtro `_SecretRedactionFilter` + padrões `sk-…`/`api_key=`).
- Logs: metadados apenas — nunca conteúdo de mensagens do usuário, nem
  deltas de streaming, nem segredos; erros técnicos ficam registrados
  para diagnóstico.
- Nenhuma forma escondida de execução: não existe código de
  terminal/arquivos/mouse/teclado no projeto.

## 10. Threads e concorrência

- `MemoryStore`, `RecordStore` (cada domínio), `MemorySystem`,
  `TaskManager` e `PermissionManager` protegidos por
  `RLock`; a worker thread e a UI podem tocar os mesmos objetos.
- Uma requisição de IA nunca roda na thread da UI; resultados (deltas,
  resposta final, erro) chegam exclusivamente pela fila.

## 11. Decisões técnicas (0.2, 0.3, 0.3.x e 0.4)

| Decisão | Motivo |
| ------- | ------ |
| SDK `openai` com import lazy | modo mock/testes funcionam sem o pacote instalado. |
| `client_factory` injetável no provider | testes de timeout/retry/streaming 100% offline. |
| Retry próprio (`max_retries=0` no SDK) | política explícita, limitada e testável. |
| Streaming via callback `on_delta` | UI progressiva sem threads extras nem queues de SDK. |
| Sem retry após deltas emitidos | evita duplicação de texto visível ao usuário. |
| Mapeamento de erros por nome/status_code | testável sem o SDK; robusto com ele. |
| Persona em módulo próprio | identidade central, prompt fácil de modificar. |
| `AIResponse`/`ResponseType` | agente futuro sem reescrever o Agent Core. |
| Cofre do SO (keyring) + fallback em arquivo 0600 | API Key fora de código/Git/logs; fallback documentado. |
| `ConfigService` como única porta da UI de config | tela não conhece stores/fábrica; validação antes de persistir. |
| Troca de provider via `RLock` no Agent | aplicação imediata da configuração, sem reiniciar e sem corrida com respostas em andamento. |
| Gemini via SDK oficial `google-genai` + adaptador dict→config | caminho recomendado pelo Google; provider testável sem o SDK instalado (fakes na mesma interface). |
| Modelo padrão GA `gemini-2.5-flash` | documentação oficial atual: estável e melhor preço/desempenho p/ conversa com raciocínio; sem "inventar" modelo. |
| Sonda Gemini sem `max_tokens` | thinking consome o orçamento mínimo e geraria falso negativo no TESTAR CONEXÃO. |

Decisões da **0.3**:

| Decisão | Motivo |
| ------- | ------ |
| JSON por domínio (não SQLite ainda) | fundação simples, legível e atomicamente gravável; a migração futura não muda contratos. |
| 6 domínios + conversa separada | separa o que a spec pediu (projetos, tarefas, conhecimento, decisões, erros, soluções) sem salvar a conversa indiscriminadamente. |
| Hash sha256 de título+conteúdo normalizados (NFD, sem acentos) | dedup estável e independente de acentuação/espaçamento. |
| Dedup apenas entre ACTIVE | permite regravar conhecimento depois de obsoleto sem falso positivo. |
| `update` imutável (nova instância) | histórico confiável de `updated_at`; colisão com outro ACTIVE é erro explícito. |
| `supersede` em vez de sobrescrever | preserva a trilha "como era antes" — requisito de recordação de projetos. |
| Busca por pontuação (título 3 > tag 2 > conteúdo 1) | relevância simples, determinística e testável sem embeddings (futuro 0.3.x). |
| Redação de segredos ANTES de persistir | segredos nunca chegam ao disco de memória, mesmo por engano. |
| `build_context()` como gancho isolado | memória pronta e testada; a integração ao Agent fica para a próxima etapa, sem misturar escopos. |

Decisões da **0.3.x** (expansão de providers):

| Decisão | Motivo |
| ------- | ------ |
| Groq/Together herdam o `OpenAIProvider` | os dois SDKs oficiais são OpenAI-compatíveis (introspecção 1.7.0/2.32.0) — núcleo de payload/retry/streaming/erros reutilizado sem duplicação; cada provider mantém factory, padrão e validação próprios. |
| Llama via Together AI, não "Meta Llama API" | a Meta encerrou a Llama API em 06/07/2026 (endpoint devolve só sunset) e a Cerebras removeu os Llama do catálogo público; a Together mantém Llama 4 em API pública (§3.7). |
| Não implementar o Meta Model API (Muse Spark) | serviço atual da Meta não serve modelos Llama — fora do pedido; documentado como não implementado. |
| Modelo padrão `openai/gpt-oss-120b` (groq) | modelo de produção em destaque no catálogo oficial: 131k contexto, raciocínio e tool calling, acessível no plano Developer (os Llama da Groq estão em tier Enterprise). |
| Modelo padrão Llama 4 Scout (together) | raciocínio sobre codebase + function calling + custo menor que o Maverick; Maverick documentado como alternativa. |
| Modelo opcional (vazio = padrão) em groq/together | mesmo UX do gemini; openai continua exigindo modelo explícito. |
| Sonda sem `max_tokens` para groq/together | modelos com raciocínio consumiriam o orçamento mínimo pensando → resposta vazia/falso negativo (mesma política já usada com o Gemini). |

Decisões da **0.4** (Planner — fundação):

| Decisão | Motivo |
| ------- | ------ |
| Plano = dataclasses imutáveis (`Plan`/`PlannedTask`) | o planejamento produz apenas dados; executor futuro preenche `result`/`error` sem mudar o contrato. |
| Protocolo JSON strict (objetivo/análise/tarefas) | saída de IA interpretável e validável; tolerância apenas a cercas de código e texto ao redor. |
| IDs canônicos `T1…Tn` pela ordem de listagem | independe dos ids que o modelo inventar; dependências remapeadas e validadas (desconhecidas rejeitadas, ciclos detectados via Kahn). |
| `BLOCKED` = pré-condição do ambiente ausente; `FAILED` = plano inválido/erro do provedor | distingue "configure o provider" de "a IA não planejou bem"; motivo sempre em `error`, nunca traceback. |
| `COMPLETED` existe mas não é produzido | só faz sentido após execução (executor futuro); nada artificial. |
| `create_plan` não lança exceção de negócio | falhas voltam como estados do plano — UI futura nunca recebe traceback. |
| Memória 0.3 consultada via `recall()` (leitura, excertos limitados) | enriquece o planejamento sem gravar/duplicar nada; ausente/quebrada não derruba o plano. |
| Planner recebe o provider vigente a cada `request_plan` | respeita a troca de provider em runtime sem novo acoplamento. |
| `request_plan` não toca na conversa nem no `send_message` | chat 0.2/0.3 permanece idêntico; planejamento não é conversa. |

Decisões da **0.4.x** (Executor — fundação):

| Decisão | Motivo |
| ------- | ------ |
| Pacote `app/executor/` separado do `app/planner/` | regra da spec: nenhuma lógica de execução dentro do Planner; camadas independentes. |
| Ação da tarefa em `TaskHandler` (ABC) | costura única com o futuro: ferramentas reais (0.5+) viram handlers sobre o `ToolRegistry` sem mudar o núcleo. |
| Somente `SimulatedHandler` (in-memory) | prova o mecanismo sem qualquer efeito no computador; auditável por AST. |
| Fail-fast: falha → restantes `SKIPPED` + plano `FAILED` | interrupção correta e determinística quando uma tarefa obrigatória falha. |
| Elegibilidade = todas as dependências `DONE` | respeita rigorosamente ordem e dependências (DAG). |
| `step()` além de `run_all()` | avanço tarefa por tarefa — base para checkpoints de confirmação futuros. |
| `TaskRun` separado do `PlannedTask` (imutável) | o plano original nunca é mutado; o relatório é o snapshot da execução. |
| `ExecutionObserver` no-op + `attempts`/`result`/`error` | abstrações mínimas para retry/verificação/correção/TaskManager futuros — sem implementá-los. |
| Auditoria por AST nos testes | garante que nenhum import/identificador de ferramenta real entre no pacote (grep em docstring daria falso positivo). |
| `execute_plan` não toca conversa/memória/providers | apenas gate `CHAT` + relatório; fluxos 0.1–0.4 intocados. |

Decisões da **0.4.x** (checkpoints/retry/verificação):

| Decisão | Motivo |
| ------- | ------ |
| Checkpoint = política + pedido imutável, sem UI | API interna pronta para a confirmação futura do usuário (0.5+); `NeverCheckpoints` padrão preserva a 0.4.1 |
| Recusa de checkpoint ⇒ plano `FAILED` sem executar a tarefa | recusa é decisão explícita do futuro confirmador; nada roda após ela |
| `RetryPolicy` validada (`max_attempts ≥ 1`) | impossível configurar retry infinito por construção |
| Backoff linear **injetável** (`sleeper`) | espera real em produção; testes registram atrasos sem dormir |
| Erro *inesperado* do handler não é repetido | fora do contrato (`HandlerError`) — repetir bug não é retry |
| Falha de verificação **não** consome retry | repetir sem corrigir é inútil; o loop correção→nova tentativa é futuro |
| Status `REJECTED` distinto de `FAILED` + `verified` no `TaskRun` | representa claramente "executou mas foi reprovada" com resultado preservado |
| Verificador quebrado ⇒ reprovação controlada | nunca crash/traces na cara do usuário |
| `correction.py` não é importado pelo Executor | abstrações mínimas apenas; auditoria AST garante que nada de correção automática roda |

## 12. O que deliberadamente NÃO existe na 0.6

O acesso real ao computador segue **restrito a duas ferramentas**:
arquivo (0.5) e comando de terminal **allowlistado** (0.6, §17). **Não
existe acesso irrestrito a PowerShell/CMD** (nada como
`execute_any_command("qualquer coisa")` — fora da allowlist é
bloqueado, e shells/interpretadores/builders/rede são denylist
permanente), não existem **mouse, teclado, visão computacional,
captura de tela, computer control, Unreal, ferramentas externas ou
rede das ferramentas** (0.7+; testes AST garantem `subprocess` só em
`app/tools/terminal.py`). Também não existem: **permissão global
nova** (default segue só `CHAT`; READ/WRITE só por concessão explícita
pela UI; `TERMINAL` somente por **ação dedicada** na UI 0.6.x —
explícita/auditada/por sessão — ou programática; o caminho genérico e
`COMPUTER_CONTROL` seguem **rejeitados**; DELETE segue como opt-in por
workspace), integração Executor↔TaskManager/memória e
cobrança/controle financeiro de tokens;
na memória: sumarização, embeddings, múltiplas sessões, SQLite e o
envio da memória estruturada no fluxo de **chat**. Em providers: o
**Meta Model API** (api.meta.ai, Muse Spark) e outros provedores
(Anthropic, xAI, Cerebras) não foram implementados. A concessão
`TERMINAL` pela UI existe desde a 0.6.x (§17.4) — explícita, auditada e
por sessão. Ver [ROADMAP.md](ROADMAP.md).

## 13. Planner (0.4 — fundação)

Camada `app/planner/` entre o Agent Core e os provedores:

```text
Agent.request_plan(pedido)
  ├─ PermissionManager.require(CHAT)
  ├─ Planner(provider vigente, memory=MemorySystem|None)
  │    ├─ recall(pedido)  → excertos relevantes (leitura apenas)
  │    ├─ system prompt: papel de planejador + protocolo JSON strict
  │    ├─ provider.chat(pedido, histórico, system_prompt)   ← abstração
  │    └─ validação: JSON → tarefas ≥1 → descrições → deps existentes
  │                 → sem ciclos (Kahn) → Plan
  └─ Plan: PLANNING → READY | BLOCKED | FAILED (COMPLETED reservado)
```

- **`PlannedTask`**: `id` (`T1…Tn`), `description`, `order`,
  `dependencies`, `status` (sempre `PENDING` na 0.4), `result`, `error`.
- **`Plan`**: `id` (`PLN-0001`…), `objective`, `status`, `analysis`
  (o que analisar antes da execução), `tasks`, `error`, timestamps;
  `to_dict()` para serialização futura.
- **Nenhuma tarefa é executada** — não existe código de execução,
  terminal, arquivos, mouse/teclado ou Unreal no pacote (auditado por
  teste estático). O `main.py` monta o `MemorySystem` (0.3) sem efeitos
  colaterais e o injeta no Agent para uso **somente** pelo Planner.

## 14. Executor de Planos (0.4.x — fundação + checkpoints/retry/verificação)

Camada `app/executor/`, separada do Planner, que **consome** um `Plan`
READY e coordena a execução — sem planejar e sem conhecer provedores:

```text
Agent.execute_plan(plan, handler?, verifier?, retry?, checkpoints?)
  ├─ PermissionManager.require(CHAT)
  └─ PlanExecutor(plan READY, handler = SimulatedHandler|injetado)
       ├─ validação defensiva (READY · tarefas · deps existentes · sem ciclos)
       ├─ loop: próxima elegível (todas as dependências DONE)
       │    ├─ CHECKPOINT (se a política exigir e não aprovado):
       │    │     pausa (PENDING_APPROVAL) → approve_checkpoint()/
       │    │     refuse_checkpoint()  [recusa ⇒ plano FAILED controlado]
       │    ├─ RETRY por tarefa (RetryPolicy, limite estrito, backoff
       │    │     linear injetável): tentativa → HandlerError?
       │    │        ├─ falha transitiva → AttemptRecord(erro) → repete
       │    │        └─ inesperado → FAILED sem repetir
       │    ├─ VERIFICAÇÃO (se verifier): EXECUTOU → VERIFICOU →
       │    │     SUCESSO (DONE, verified=True) | FALHOU (REJECTED,
       │    │     verified=False, fail-fast; não consome retry)
       │    └─ fail-fast: restantes SKIPPED, plano FAILED (motivo)
       ├─ eventos: task_started/retry/completed/failed/verification_passes
       │          /verification_failed/skipped/checkpoint_*/plan_finished
       └─ ExecutionReport: TaskRuns (result/error/attempts/verified/
            attempt_log), checkpoints (histórico + pendente), to_dict()
```

Módulos (`app/executor/`):

- **`handlers.py`** — `TaskHandler` (ABC) + `SimulatedHandler`
  (in-memory). Futuro (0.5+): handler real envelopando o `ToolRegistry`.
- **`checkpoints.py`** — `CheckpointPolicy` (ABC; `NeverCheckpoints`
  padrão, `EveryTaskCheckpoints`) + `CheckpointRequest`/`CheckpointStatus`
  (`PENDING_APPROVAL` = necessário/execução **pausada**; `APPROVED`;
  `REFUSED` ⇒ plano falha sem executar a tarefa). API interna — a UI de
  confirmação do usuário é futura (0.5+).
- **`retry.py`** — `RetryPolicy(max_attempts ≥ 1, backoff_seconds ≥ 0)`
  com validação (impossível retry infinito) + `AttemptRecord`
  (número/result/erro por tentativa). Backoff injetável (`sleeper`).
- **`verification.py`** — `TaskVerifier` (ABC) + `VerificationResult` +
  `SimulatedVerifier` (reprova ids mapeados). Verificador quebrado ⇒
  reprovação controlada, nunca crash.
- **`correction.py`** — **abstrações mínimas** para o loop futuro
  `falha → análise → correção → nova tentativa → verificação`:
  `CorrectionStrategy` (ABC) + `CorrectionProposal` +
  `NoopCorrectionStrategy` (padrão: não propõe nada). O Executor **não
  importa nem chama** este módulo (garantido por teste de auditoria AST).

Semântica importante: falha de **verificação** (`REJECTED`) não consome
retry — repetir sem corrigir seria inútil; a correção automática real
(chamar provider para analisar/corrigir) é explicitamente futura.

## 15. Filesystem Tools (0.5 — fundação segura)

Primeira camada de **ferramentas reais**, em `app/tools/`. O acesso
real ao computador é o **arquivo** (esta seção) e, desde a 0.6, o
**comando de terminal allowlistado** (§17) — sempre confinados,
permitidos e auditados:

```text
Agent.execute_plan(plan, handler=ToolTaskHandler(registry))
  └─ PlanExecutor (núcleo intacto, agnóstico de ferramentas)
       └─ ToolTaskHandler.execute(task)            [app/tools/handler.py]
            ├─ task.tool designado? (senão HandlerError honesto)
            ├─ audit.scoped(task_id, plan_id)       (contexto da trilha)
            └─ ToolRegistry.execute(tool, **parameters)
                 ├─ PermissionManager.require(READ|WRITE)  ← porteio
                 └─ FilesystemTool.run(**params)     [app/tools/filesystem.py]
                      ├─ sandbox.assert_operation_allowed(read|write|delete)
                      ├─ sandbox.resolve(path)  → valida formato,
                      │    rejeita '..'/traversal, confina nas raízes
                      │    (pós-resolve: symlink não escapa)
                      ├─ operação real (pathlib, UTF-8 explícito)
                      └─ FilesystemAudit.record(...)  (toda tentativa)
                           → ToolResult{ok, data, error} (JSON)
```

### 15.1 Ferramentas (contratos)

| Ferramenta | Permissão | Operação | Comportamento |
| ---------- | --------- | -------- | ------------- |
| `list_directory` | `READ` | read | entradas ordenadas (nome/tipo/tamanho) + contagem |
| `read_file` | `READ` | read | conteúdo UTF-8; limite `max_bytes` (default 1 MiB) |
| `write_file` | `WRITE` | write | cria **ou sobrescreve** (`overwritten` informado); pai deve existir |
| `create_file` | `WRITE` | write | apenas novo — **falha se existe** (não sobrescreve) |
| `delete_file` | `WRITE` | delete | apenas arquivos; exige `writable` **e** `allow_delete` |
| `file_exists` | `READ` | read | `exists` + `is_dir` |

Resultados são **estruturados** (`ToolResult`: `ok`/`data`/`error`;
`data` traz operação, caminho solicitado, caminho resolvido e os dados
da operação). Falhas não viram exceção para o chamador — viram
`ok=False` com erro amigável (o handler as converte em `HandlerError`,
fail-fast controlado do Executor).

### 15.2 Sandbox/workspace (`WorkspaceSandbox`)

- Raízes **autorizadas explicitamente** por quem integra (caminhos
  absolutos, resolvidos; duplicadas descartadas; ao menos uma).
- `writable=False` por padrão (somente leitura); `allow_delete=False`
  por padrão (exclusão = opt-in duplo).
- Resolução: rejeita vazio/não-string/caracteres de controle; **rejeita
  qualquer componente `..`** (traversal bloqueado até se o destino
  ficaria dentro); absolutos aceitos só se dentro de uma raiz;
  relativos resolvidos contra as raízes na ordem declarada (primeira
  contém); **contenção verificada após `Path.resolve()`** — symlink
  para fora é bloqueado. Multiplataforma (pathlib; no Windows o mesmo
  contrato vale para `C:\…`).

### 15.3 Auditoria (`FilesystemAudit`)

Toda tentativa — sucesso, bloqueio de política, bloqueio de permissão
(registrado pelo handler com `operation="permission_gate"`) ou erro de
filesystem — gera um `AuditRecord`: timestamp, ferramenta, operação,
caminho solicitado, caminho resolvido (quando houver), sucesso, erro,
`tarefa`/`plano` de origem (via `audit.scoped()` do handler) e
metadados (`detail`: bytes, contagens, flags). **Conteúdo de arquivos
nunca é registrado.** Registros em memória; `sink` injetável recebe
cada dict para persistência futura (ex.: JSONL) sem mudar contrato;
sink quebrado não derruba operação.

### 15.4 Ponte com o Executor (`app/tools/handler.py`)

- `ToolTaskHandler(registry, audit?, plan_id?)`: despacha
  `task.tool` com `task.parameters` pelo registry (único caminho de
  execução — permissão sempre portada). `PermissionDeniedError`,
  ferramenta inexistente e `ok=False` viram `HandlerError` (tarefa
  `FAILED`, plano falha de forma controlada — **bloqueado, não
  executado**). Tarefa sem `tool` falha honestamente ("não designa
  ferramenta") — sem execução fantasma.
- `ToolCheckpoints(required_tools)`: política de checkpoint que pausa a
  execução antes de tarefas com ferramentas destrutivas
  (`FILESYSTEM_DESTRUCTIVE_TOOLS` = write/create/delete); aprovar
  executa, recusar bloqueia. Consentimento sem UI obrigatória.
- `PlannedTask` ganhou campos **opcionais** `tool`/`parameters`; o
  protocolo do Planner **não** os produz (planos com ferramentas são
  montados programaticamente — TaskManager/UI futuros).

### 15.5 Decisões técnicas (0.5)

| Decisão | Motivo |
| ------- | ------ |
| Handler-ponte em `app/tools/`, não no Executor | o núcleo do Executor permanece agnóstico (auditoria AST continua verde); dependência aponta das tools para os contratos do Executor, nunca o contrário |
| Sandbox por raízes explícitas + `writable`/`allow_delete` default off | sem acesso irrestrito ao computador/Windows; escrita e exclusão são opt-in separados |
| `..` rejeitado sempre (mesmo ficando dentro) | regra simples, previsível e auditável; contenção pós-resolve cobre o resto (symlinks) |
| Falha de ferramenta = `ToolResult(ok=False)`, não exceção | resultado estruturado previsível para handler/plano; handler decide o fail-fast |
| Permissão negada = exceção no registry → `HandlerError` | o porteio acontece ANTES de qualquer código da ferramenta rodar |
| `create_file` separado de `write_file` | criar sem risco de sobrescrever por acidente; sobrescrever é ato explícito (e checkpointável) |
| Auditoria sem conteúdo de arquivos | rastro completo sem vazar dados sensíveis |
| `delete_file` implementado com triple gate | spec só pedia "se a arquitetura permitir com segurança": WRITE + writable + allow_delete + checkpoint pronto — seguro por construção; default continua bloqueado |
| Registro de ferramentas sempre explícito (sem startup side effects) | `main.py` intacto; quem integra define raízes e concede permissões |
| `max_bytes` default no `read_file` | leitura acidental de arquivos enormes não estoura memória |
| `_abstract_base` marcador nas bases intermediárias de `Tool` | validação de metadados apenas em ferramentas concretas (erro rápido onde importa) |

## 16. Camada de controle e UI de Ferramentas (0.5.x)

A 0.5.x fecha o ciclo **humano** das ferramentas: quem autoriza, quem
concede, quem aprova e quem audita é o usuário — por uma tela. Toda a
lógica vive no :class:`~app.tools.control.ToolsController` (testável
sem Tk); o diálogo ``🛡 Ferramentas`` é apresentação.

```text
main.py (composition root)
 └─ ToolsController(permissions do Agent, workspaces.json, audit.jsonl)
      ├─ Workspaces: WorkspaceStore (valida/normaliza/persiste) +
      │    MultiWorkspaceSandbox (política POR RAIZ)
      ├─ Permissões: só CHAT/READ/WRITE (TERMINAL/COMPUTER_CONTROL
      │    rejeitados; DELETE = opt-in por workspace)
      ├─ run_plan(plan): ToolTaskHandler + ToolRegistry + ferramentas
      │    com PrevalidatedCheckpoints → pausa em operação destrutiva
      │    VIÁVEL → pending_approval() (o quê/onde/ferramenta/permissão)
      │    → approve()/refuse()  [recusa ⇒ nada roda]
      └─ Auditoria: FilesystemAudit (memória) + JsonlAuditSink (JSONL)
UI: app/ui/tools_dialog.py (workspaces · permissões · aprovação ·
    auditoria) — botão 🛡 na janela principal
```

- **`WorkspaceStore`** (`data/workspaces.json`, atômico): só nasce na
  1ª autorização; valida absoluto+existente+diretório, normaliza com
  `resolve()`, deduplica e **rejeita raiz de disco** (`/`, `C:\`) —
  nunca o Windows inteiro. `MultiWorkspaceSandbox`: `resolve` na ordem
  de autorização; `check_operation` aplica a política **do workspace
  que contém o caminho** (somente-leitura num workspace bloqueia
  escrita nele mesmo que outro permita); vazio ⇒ tudo bloqueado.
- **`PrevalidatedCheckpoints`**: pede aprovação **somente** para
  operações destrutivas **viáveis** (permissão concedida + caminho que
  passa na política). Operação inviável falha controlada com o motivo
  real — o usuário nunca é interrogado sobre algo que nem permissão
  tem (aprovação nunca decorativa).
- **Aprovação na UI**: card com "O que / Ferramenta · Operação ·
  Permissão / Onde (solicitado → resolvido + workspace)" + APROVAR /
  RECUSAR; recusa ⇒ tarefa `SKIPPED`, plano `FAILED`, arquivo
  intocado; aprovação ⇒ executa e segue até a próxima pausa/fim.
- **Auditoria JSONL** (`data/audit/audit.jsonl`): append thread-safe
  por registro; visualização com timestamp · ferramenta · operação ·
  caminhos · ✓/✗ · erro · tarefa/plano; **sem conteúdo de arquivos**;
  leitor pula linhas corrompidas.
- **Startup sem efeitos colaterais**: nenhum arquivo de workspace/
  auditoria nasce, nenhuma permissão concedida, nenhuma ferramenta
  registrada até o usuário agir.

### 16.1 Decisões técnicas (0.5.x)

| Decisão | Motivo |
| ------- | ------ |
| Lógica no controller, UI só apresenta | testes de segurança cobrem a camada de controle sem Tk; diálogo é fino |
| Política por workspace no `MultiWorkspaceSandbox` (+`check_operation` ciente do caminho) | um workspace somente-leitura nunca é "contaminado" por outro permissivo |
| Store rejeita raiz de disco | "nunca o Windows inteiro" garantido na origem, não por promessa |
| `DELETE` na tela = opt-in por workspace | espelha a arquitetura real (não é `PermissionLevel`); sem nível falso |
| UI rejeita conceder `TERMINAL`/`COMPUTER_CONTROL` | nenhuma concessão silenciosa de níveis de versões futuras |
| Checkpoint só para operações viáveis (`PrevalidatedCheckpoints`) | pedir aprovação para algo sem permissão é ruído; o bloqueio real vem primeiro |
| Arquivos nascem só no primeiro uso | startup sem side effects (workspaces.json/audit.jsonl ausentes até agir) |
| JSONL para auditoria | simples, append-only, legível; separado do conteúdo dos arquivos |
| `Agent.permissions` (property read-only) | composição do controller com a MESMA instância dos gates do Agent |


## 17. Terminal Tools (0.6 — fundação controlada)

Segunda camada de **ferramentas reais**: execução de comandos **sem
jamais receber PowerShell/CMD irrestrito**. Toda a execução vive em
`app/tools/terminal.py` (o **único** módulo com `subprocess` — testes
AST garantem); o Executor segue agnóstico (a ferramenta entra pelo
`ToolRegistry` como qualquer outra).

```text
Planner (protocolo; não emite tools — plano montado programaticamente)
 └─ ToolsController.run_plan(plan)            [app/tools/control.py]
     ├─ ToolRegistry.execute("run_command")   ← porteiro: TERMINAL
     │    (sem permissão ⇒ HandlerError; NADA roda; gate auditado)
     ├─ _CombinedCheckpoints
     │    └─ PrevalidatedTerminalCheckpoints: pausa SOMENTE se o
     │         comando é viável (allowlist+args+cwd) E requires_approval
     │         (default True — todo comando pede aprovação)
     └─ RunCommandTool.run                    [app/tools/terminal.py]
          ├─ TerminalPolicy.validate (revalida — defesa em profundidade):
          │    denylist permanente → allowlist explícita → argumentos
          │    (operadores/redirecionamento/"-exec"/".."/caminho
          │    absoluto fora) → cwd confinado ao workspace →
          │    timeout (obrigatório, clamp 60s) → limite de saída
          ├─ subprocess.Popen(argv lista, shell=False, cwd=workspace,
          │    stdin=DEVNULL, env SANITIZADO — sem KEY/TOKEN/SECRET)
          │    + leitores com teto de bytes (64 KiB) + wait(timeout)
          │    → timeout mata; saída além do teto trunca (falha honesta)
          └─ FilesystemAudit.record(tool=run_command, command=argv
               sanitizado, cwd, exit_code, timed_out/truncated,
               duration_ms, tarefa/plano) — sem stdout/stderr na trilha
```

### 17.1 Componentes

| Componente | Papel |
| ---------- | ----- |
| `AllowedCommand` | Um comando permitido: `name` normalizado, `full_path` opcional (match exato), `args_allowlist` opcional (argumentos fixos), `requires_approval` (default `True`), `timeout_s`/`max_output_bytes` próprios |
| `TerminalPolicy` | Allowlist explícita (`allow()`/`enable_terminal`), denylist permanente (`FORBIDDEN_COMMANDS`, 137 nomes normalizados — shells, interpretadores, builders que executam código, escalonamento, destrutivos/administrativos e **rede**), `DANGEROUS_ARGUMENTS` (`-exec`, `/c`, `-EncodedCommand`…), `OPERATOR_TOKENS` (`&&`, `|`, `;`, `>`, `$(`… bloqueados salvo `allow_operators=True`), validação completa em `validate()` (levanta subtipos de `TerminalSecurityError` com motivo claro) |
| `RunCommandTool` | `run_command` (`command`, `args`, `cwd`) — permissão `TERMINAL`; executa argv **sem shell**, captura `stdout`/`stderr` separadas com teto, `exit_code`, `timed_out`, `truncated`, `duration_ms` no `ToolResult`; ambiente filho sanitizado (`SAFE_ENV_VARS`; nada com KEY/TOKEN/SECRET/PASSWORD) |
| `PrevalidatedTerminalCheckpoints` | Checkpoint só para comandos **viáveis** marcados `requires_approval` (mesma lógica 0.5.1 — inviável falha direto com o motivo real; sem aprovação decorativa) |
| `ToolsController.enable_terminal/allow_command/disable_terminal` | Opt-in do integrador (nada habilitado no startup); `TERMINAL` segue concessão programática |
| `TerminalStore` (0.6.x) | Persistência da allowlist em `data/terminal.json` (atômico; só nasce no primeiro cadastro; **fail closed**: ilegível ⇒ desabilitado, entrada inválida/denylistada ⇒ descartada; defaults restaurados). A permissão `TERMINAL` **nunca** é persistida |
| `ToolsController.grant_terminal/revoke_terminal` (0.6.x) | Concessão/revogação **explícita e auditada** de `TERMINAL` (o genérico `grant_permission` segue rejeitando; por sessão) + `list_allowed_commands`/`remove_allowed_command`/`terminal_status` para a UI |

### 17.2 Decisões técnicas (0.6)

| Decisão | Motivo |
| ------- | ------ |
| Fora da allowlist = **bloqueado** (não "confirmar e rodar") | Spec 0.6 mais rígida que o ROADMAP original; allowlist é o ato de confiança, o checkpoint não substitui |
| Denylist permanente além da allowlist | Nenhum integrador cadastra `sh`/`powershell`/`python`/`make`/`curl` por engano; normalização mata aliases (`python.exe`, `POWERSHELL`, `/bin/sh`) |
| argv lista + `shell=False` + operadores bloqueados em args | Sem interpretação de shell; operadores/redirecionamento são deep-defense |
| `full_path` exige match exato; nome simples não aceita caminho | `/tmp/evil/git` jamais casa com a entrada `git` |
| Todo comando `requires_approval=True` por default | Fundação conservadora; comandos comprovadamente inofensivos podem dispensar |
| Timeout obrigatório (clamp 60 s) + teto de saída 64 KiB com kill | Comando travado ou verboso não pendura a Lumen nem estoura memória |
| Env filho sanitizado | `printenv`/`env` dump nunca vaza credenciais da Lumen |
| cwd confinado + args absolutos fora bloqueados + `..` bloqueado | Mesmo contrato de workspace do filesystem aplicado ao terminal |
| Auditoria registra argv sanitizado (32 args/200 chars) e exit code; **nunca** stdout/stderr | Trilha legível sem virar despejo de conteúdo |
| `exit_code != 0`, timeout e truncamento = `ok=False` com motivo | Falha honesta; dados parciais nunca parecem sucesso |
| subprocess exclusivo de `terminal.py` (auditoria AST) | Superfície de execução mínima e verificável |

### 17.3 Limitações assumidas (documentadas, sem promessa de isolamento de SO)

A allowlist é confiança explícita do integrador: um comando
legitimamente permitido pode, por natureza, ter efeitos além do cwd
(ex.: escrever em caminho interno fixo, consumir CPU). As defesas de
argumento/cwd são profundidade, não sandbox de sistema operacional.
Rede segue inacessível (curl/wget/ssh… são denylist). A UI da allowlist
(e concessão `TERMINAL` pela tela) é 0.6.x. Comandos testados no
sandbox são POSIX (printf/mkdir/sleep/seq/ls/false/printenv); no
Windows real a mesma política vale para `dir`, `where`, `git` etc.

### 17.4 UI de Terminal, Allowlist e Concessão TERMINAL (0.6.x)

Fechamento do ciclo humano do terminal, na tela 🛡 (apresentação;
lógica 100% no controller — a UI importa apenas `app.tools.control`):

- **Permissão TERMINAL**: linha dedicada com estado + Conceder/Revogar
  (`grant_terminal`/`revoke_terminal` — auditados como
  `terminal_grant`/`terminal_revoke`). O caminho genérico de permissões
  (`grant_permission`) **continua rejeitando** TERMINAL — a concessão
  exige o ato dedicado (nada silencioso) e **vale só na sessão**
  (nunca restaurada do disco; `COMPUTER_CONTROL` inconcedível).
- **Allowlist**: cadastro (aprovação obrigatória por default, ou
  execução direto), remoção e "Desabilitar terminal" (esvazia tudo).
  Primeiro cadastro = habilitação explícita da allowlist (auditada;
  sem concessão de permissão). Persistência via `TerminalStore`
  (`data/terminal.json`, fail closed). Denylist aplicada no cadastro E
  na carga do arquivo.
- **Card de aprovação**: comando, argumentos, diretório de trabalho e
  timeout em linhas próprias (dados do `pending_approval`: `command`,
  `timeout_s`, `resolved_path`).
- **Auditoria administrativa**: `tool=terminal_admin` com operações
  `terminal_grant`/`terminal_revoke`/`allowlist_add`/
  `allowlist_remove`/`terminal_enable`/`terminal_disable` (tentativas
  rejeitadas incluídas; sem conteúdo sensível).

Ver também: §15 (Filesystem), §16 (camada de controle), §9 (Segurança).

## 18. Correção Automática Controlada (0.4.x — versão 0.6.2)

O mecanismo adiado desde a 0.4.x, entregue de forma **controlada**:
`EXECUTAR → VERIFICAR → SUCESSO continua / FALHA → ANALISAR → GERAR
PROPOSTA → VALIDAR → CHECKPOINT/APROVAÇÃO quando necessário → APLICAR
→ RETRY → VERIFICAR`, limitado ao sistema de ferramentas **já
autorizado**. Não é execução arbitrária: sem shell livre, sem novos
poderes, sem bypass de permissões/checkpoints, sem acesso fora dos
workspaces.

### 18.1 Componentes

- **`app/executor/correction.py`** (genérico; **não importa
  `app.tools`** — testes AST): `CorrectionEngine` envolve o
  `PlanExecutor`; na falha de uma tarefa, consulta a
  `CorrectionStrategy` → `CorrectionProposal` (tarefa corrigida,
  sugestão, `requires_approval`, `detail`). Estados por ciclo
  (`CorrectionStatus`), **todos separados**: `PROPOSED` (proposta
  gerada), `INVALID` (validador bloqueou — nada aplica, nem pausa),
  `REFUSED` (usuário recusou — nada executa depois), `APPROVED`,
  `APPLIED` (plano sucessor criado), `RETRIED` (nova tentativa),
  `SUCCEEDED` (sucesso final após correção), `FAILED` (correção
  aplicada não resolveu e não há nova proposta), `NO_PROPOSAL`
  (estratégia sem proposta), `EXHAUSTED` (limite atingido).
- **Plano sucessor imutável**: id `<plano>#C<n>`; a tarefa corrigida
  **mantém id/ordem** (sucessores idênticos aos da original;
  dependências filtradas aos ids presentes); o plano original nunca é
  mutado (dados frozen; verificação dedicada nos testes).
- **Limites rígidos** (`enable_corrections(strategy=None,
  max_cycles=2, max_total_attempts=8)`; negativos rejeitados):
  correções **aplicadas** ≤ `max_cycles`; tentativas **acumuladas**
  (`sum` dos `attempts` por execução) ≤ `max_total_attempts`;
  `max_cycles=0` desliga o loop; **nunca retry infinito** — todo
  desfecho negativo termina o plano com `FAILED`.
- **`app/tools/correction.py`**: `ToolCorrectionStrategy`
  **conservadora** — única proposta real: `create_file → write_file`
  quando o erro é "arquivo já existe"; erros com marcadores de
  segurança (permissão negada, allowlist, fora do workspace,
  traversal, somente leitura, `allow_delete`, operador de shell…)
  **nunca** geram proposta (`NO_PROPOSAL` — sem bypass).
  `build_proposal_validator(registry, permissions, sandbox,
  terminal_policy)`: proposta só é válida com **tool registrada +
  permissão concedida + sandbox aprovando** (path/operação) — e
  `run_command` ainda validado pela `TerminalPolicy`.
- **`ToolsController`**: `enable_corrections`/`disable_corrections`/
  `corrections_enabled`/`correction_history()`; `run_plan` cria o
  engine quando habilitado; pendências roteiam **transparentemente**
  correção × checkpoint de operação em `has_pending`/
  `pending_approval`/`approve`/`refuse` (pendência de correção vem
  com `kind="correction"`; de operação, sem `kind`); aprovar a
  correção aplica e segue para o checkpoint da operação corrigida.
- **Auditoria**: todo ciclo → JSONL com `tool="correction"`,
  `operation="correction_<status>"` (sucesso=False para
  INVALID/REFUSED/FAILED/NO_PROPOSAL/EXHAUSTED), `task_id`/`plan_id`/
  `cycle` no detail; `suggestion`/`note` truncados em 160; **sem
  conteúdo sensível**.
- **UI 🛡**: card **CORREÇÃO PROPOSTA** — falha (execução ou
  verificação), ferramenta de→para, parâmetros original/corrigido;
  Aprovar/Recusar (recusa mantém a falha; nada executa depois).

### 18.2 Decisões técnicas (0.6.2)

1. **Motor genérico na camada do Executor** (sem `app.tools`) — a
   estratégia é injetada; o motor não conhece ferramentas reais.
2. **`_handle_failure` tri-state** (`True` segue / `None` pausa
   aguardando decisão / `False` falha definitiva) — preserva a retomada
   do executor após a decisão do usuário.
3. **Validação antes da pausa**: proposta inválida vira `INVALID`
   imediatamente (não existe checkpoint decorativo de correção).
4. **Numeração por análise** (não por registro): múltiplos estados do
   mesmo ciclo compartilham `number`; a análise seguinte incrementa.
5. **Retomada com plano sucessor** (não "rewind"): o histórico de
   execuções permanece íntegro no `ExecutionReport`.
6. **Planner intocado** — sem lógica de execução ou correção no
   planejamento (item 8 do protocolo).

Ver também: §14 (Executor), §15.4 (ponte Executor↔tools), §16
(camada de controle), §9 (Segurança).

## 19. Tool Calling / Planner Bridge (0.6.3)

A ponte **CHAT → PLANNER → TOOL CALLING → VALIDATION → TOOLS
CONTROLLER** como parte da arquitetura: uma solicitação em linguagem
natural ("Crie um arquivo chamado teste_lumen.txt contendo: TESTE LUMEN
0.6.3") vira tarefa estruturada e chega ao sistema de ferramentas já
existente — **sem criar nenhum poder novo**.

### 19.1 Fluxo completo

```
UI (main_window.send → worker)
  → Agent.process_message            (0.6.3)
    → ToolCallingBridge.process      (app/core/bridge.py)
      → controller.planning_catalog  (allowlist de protocolo)
      → Agent.request_tool_plan      (gate CHAT; provider vigente)
        → Planner.create_tool_plan   (prompt com a allowlist)
          → provider.chat            (classifica conversa × planeja)
          → catalog.validate_task_tool  (validação local ANTES de tudo)
      → kind=conversation → send_message clássico (streaming; nada executa)
      → kind=invalid     → PLAN_INVALID controlado (nada executa)
      → kind=plan        → ToolsController.run_plan (cadeia §16 intacta)
           → PlanExecutor → ToolTaskHandler → ToolRegistry (porteiro)
           → PermissionManager → WorkspaceSandbox → CHECKPOINT (pausa)
           → APROVAÇÃO do usuário → tool real → verificação → auditoria
```

### 19.2 Componentes

- **`app/planner/catalog.py`**: allowlist declarativa das ferramentas
  **já existentes** (6 filesystem + `run_command` apenas com terminal
  habilitado). `validate_task_tool` rejeita: tool vazia/inventada,
  parâmetros ausentes/desconhecidos/tipos errados, `path` absoluto ou
  com `..`. Falha de protocolo = falha controlada (plano `FAILED` com
  motivo) — **nunca** execução parcial.
- **`Planner.create_tool_plan` → `ToolPlanResult`**: `plan` (READY com
  `tool`/`parameters`), `conversation` (pedido conversacional) ou
  `invalid` (saída fora do protocolo). O prompt embute a allowlist e
  proíbe inventar ferramentas; a memória 0.3 segue como leitura e
  **não é autorização**.
- **`app/core/bridge.py`**: `ToolCallingBridge` orquestra e expõe
  `RequestState` (`CONVERSATIONAL`, `PLANNING`, `PLAN_READY`,
  `PLAN_INVALID`, `WAITING_APPROVAL`, `EXECUTING`, `VERIFYING`,
  `COMPLETED`, `FAILED`, `REJECTED`). Sem lógica de filesystem/terminal
  — só delega ao controller.
- **`Agent`**: `process_message` (UI passa a chamar isto), 
  `set_tools_controller` (injetado pelo `main.py`; sem controller o
  comportamento 0.6.2 é preservado).
- **`MockProvider.chat`**: reconhece o prompt de planejamento com
  ferramentas e planeja de forma **determinística** (offline), incluindo
  o pedido canônico de criação de arquivo; pedidos vagos/destrutivos e
  injeções viram conversa.
- **UI 🛡**: card de aprovação exibe o **conteúdo** a gravar
  (`content_preview`) além de ferramenta/permissão/workspace.

### 19.3 Regras de autoridade (inalteradas)

1. **LLM não é autorização** — o plano é apenas um pedido; a execução
   exige as camadas reais (permissão concedida, workspace, checkpoint).
2. "O usuário pediu" ≠ "o usuário autorizou": sem WRITE/READ/TERMINAL a
   operação falha controlada; nenhuma permissão é concedida
   automaticamente pelo chat.
3. Terminal não foi ampliado: `run_command` só entra na allowlist de
   planejamento se o terminal já estiver habilitado; denylist,
   allowlist, timeout e checkpoint por comando seguem valendo (o plano
   jamais contorna a `TerminalPolicy`).
4. Hierarquia: Sistema de segurança → Permissões → Workspace/Sandbox →
   Checkpoint → ToolRegistry → Plano → LLM (nunca o contrário).
5. Imutabilidade preservada: o plano original nunca muda; correções
   seguem o mecanismo sucessor do §18 (testado via chat).

Ver também: §13 (Planner), §14 (Executor), §16 (controle), §17
(Terminal), §18 (Correção), §9 (Segurança).
