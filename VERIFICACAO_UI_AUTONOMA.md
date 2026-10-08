# Verificação factual: autonomia da LUMEN pela UI Tkinter

**Escopo:** leitura estática do código desta versão do repositório, sem implementar alterações nem executar testes. As referências abaixo usam `arquivo:linha`.

## Resumo executivo

- A janela principal **aceita texto livre**: o usuário pode digitar um objetivo em linguagem natural e enviá-lo ao Agent.
- Há um fluxo de chat ativo para **planejamento de chamadas a ferramentas e execução controlada**. O fluxo usa `app/planner/` (singular), não o pacote `app/planning/` (feature planner).
- A busca web e a ponte Unreal têm pontos de integração no `ToolsController`, mas começam **desabilitadas** e não são habilitadas por `main.py` nem por controles da UI atual.
- `app/planning/` tem geração de plano, renderização e `ApprovalGate`, mas não está ligado ao Agent, à janela, ao controller ou ao servidor MCP no código de produção.
- Ollama pode ser selecionado como provedor, mas o padrão é `mock`. O provider Ollama não implementa function/tool calling nativo; a aplicação tem, separadamente, planejamento de tools por **JSON solicitado em prompt**.

---

## 1. Estrutura da UI

### 1.1 Imports do ponto de entrada `main.py`

`main.py:13` também ativa `from __future__ import annotations`. Imports estáticos de runtime em `main.py:15–29`:

- Biblioteca padrão: `logging`, `sys`.
- `app`: `__version__`.
- `app.ai.provider`: `create_provider`.
- `app.config.config_service`: `ConfigService`.
- `app.config.secrets`: `create_secret_store`.
- `app.config.settings`: `Settings`, `setup_logging`.
- `app.config.user_config`: `UserConfigError`, `UserConfigStore`, `apply_user_overrides`.
- `app.core.agent`: `Agent`.
- `app.memory.store`: `MemoryStore`.
- `app.memory.system`: `MemorySystem`.
- `app.security.permissions`: `PermissionManager`.
- `app.tasks.manager`: `TaskManager`.
- `app.tools.control`: `ToolsController`.

Imports locais, executados durante a inicialização: `tkinter` dentro de `tk_root()` (`main.py:164–168`) e `LumenWindow` de `app.ui.main_window` dentro de `main()` (`main.py:125–126`). **Não há import de `app.research`, `app.planning` ou `app.unreal_bridge` em `main.py`.**

A composição inicial cria o provider, memória, permissões, Agent e `ConfigService` em `main.py:40–74`. Depois, cria `ToolsController`, injeta-o no Agent e entrega os dois à janela (`main.py:131–157`). O comentário em `main.py:53` descreve as permissões iniciais como “apenas CHAT nesta fase”.

### 1.2 Elementos visíveis na janela principal

A construção principal está em `app/ui/main_window.py:103–220`:

| Elemento | Tipo/comportamento | Referência |
|---|---|---|
| Marca “L U M E N” | `Label` | `main_window.py:107–113` |
| Indicador de estado | `Label` (“Pronta”, “Pensando…”, “Erro”) | `main_window.py:114–117`; estados em `52–56` |
| “⚙ Configurações” | Botão que abre configurações de IA | `main_window.py:119–134`, abertura em `227–234` |
| “🛡 Ferramentas” | Botão que abre ferramentas/segurança | `main_window.py:136–151`, abertura em `236–246` |
| Subtítulo | `Label` com versão, provider e modelo atuais | `main_window.py:90–101`, construção em `153–160` |
| Conversa | `Text` **somente leitura** | `main_window.py:162–186` |
| Entrada | `Entry` de texto livre, enviada também com Enter | `main_window.py:188–204` |
| “Enviar” | Botão que chama `send()` | `main_window.py:206–220` |

Não há menu Tkinter na janela principal. A entrada é um campo genérico de mensagem, não um formulário de comandos: `send()` lê qualquer texto não vazio e encaminha para o Agent (`main_window.py:266–287`); o worker chama `process_message()` (`main_window.py:289–299`). Portanto, **sim, existe campo para digitar um pedido em linguagem natural**.

Os botões abrem janelas secundárias. Configurações de IA contém seleção de provider, campo de modelo, campo de API key, teste de conexão e salvar (`app/ui/settings_dialog.py:63–137`). Ferramentas e Segurança contém aprovação de checkpoints, workspaces, permissões, terminal, toggles de automação e auditoria (`app/ui/tools_dialog.py:74–89`). Esses controles secundários não equivalem a um editor/revisor de plano completo.

---

## 2. Conexão da UI com os módulos novos

### 2.1 `app/research/`

**Existe integração de produção, mas é condicional.** `ToolsController.enable_web_search()` importa o factory do pacote de pesquisa e tenta habilitá-lo (`app/tools/control.py:941–962`); se habilitado, `build_registry()` registra `WebSearchTool` (`app/tools/control.py:1060–1066`). O catálogo do planner só inclui `web_search` quando há provider configurado (`app/tools/control.py:1015–1032`; `app/planner/catalog.py:341–377`). A ferramenta exige permissão `READ` (`app/research/tool.py:40–56`).

No entanto, o construtor do controller define `_web_search_provider = None` por padrão (`app/tools/control.py:436–438`), e **não há chamada a `enable_web_search()` em `main.py` ou nos diálogos da UI**. O entry point do MCP, por outro lado, tem um caminho explícito: habilita pesquisa quando recebe `args.enable_web_search` (`app/mcp_server/__main__.py:204–208`). O provider de busca procura configuração/chaves de Tavily ou Brave no ambiente/`.env` (`app/research/client.py:425–455`); a tela de IA da UI não configura essas chaves.

### 2.2 `app/planning/` — feature planner e aprovação

**Não está importado/chamado por código de produção fora do próprio pacote.** A busca de referências Python no repositório não encontrou consumidores em `main.py`, `app/core/`, `app/ui/`, `app/tools/` ou `app/mcp_server/`; as referências do pacote são internas (por exemplo, exports em `app/planning/__init__.py:22–46`).

O pacote contém APIs reais, mas isoladas:

- `FeaturePlanner.create_plan(objective, research=...)` recebe blocos de pesquisa, chama um `AIProvider` e produz um `FeaturePlan` (`app/planning/planner.py:92–145`). Não executa nada (`108–114`).
- `ApprovalGate.submit()` e `approve()` registram um plano pendente e uma decisão explícita (`app/planning/approval.py:76–118`).
- `render_markdown()` renderiza o plano para revisão (`app/planning/render.py:22–109`).
- `FeaturePlan.to_planner_plan()` exige aprovação antes de converter (`app/planning/models.py:284–303`), mas sua conversão atual gera tarefas de diretório/arquivo e `run_command` (`app/planning/models.py:307–362`); **não gera tarefas `unreal_*`**.

Nada na janela instancia `FeaturePlanner`/`ApprovalGate`, chama `extract_research_blocks()` ou apresenta `render_markdown()`.

### 2.3 `app/unreal_bridge/`

**Há integração no controller compartilhado com a aplicação, mas não está ativada no fluxo da UI.** `ToolsController.enable_unreal_bridge()` constrói/configura o cliente (`app/tools/control.py:972–1005`); quando habilitado, `planning_catalog()` passa a incluir as tools Unreal e `build_registry()` registra as ferramentas do bridge (`app/tools/control.py:1015–1032` e `1067–1073`). O caminho de execução ainda passa por `run_plan()` (`app/tools/control.py:1155–1263`). Os quatro tipos de operação Unreal que alteram estado têm checkpoints próprios, condicionados a `WRITE` (`app/tools/control.py:296–312`).

Mas `_unreal_client` começa como `None` (`app/tools/control.py:439–440`), e `main.py:131–152` cria o controller e o injeta no Agent **sem chamar** `enable_unreal_bridge()`. Também não há controle Unreal nos blocos construídos pelo `ToolsDialog` (`app/ui/tools_dialog.py:74–79`). O caminho explícito fora da UI é o MCP, que instancia cliente/configuração e chama `enable_unreal_bridge()` quando o flag correspondente está ligado (`app/mcp_server/__main__.py:209–219`).

**Conclusão desta pergunta:** a implementação da ponte não é exclusivamente “código do MCP”, pois o `ToolsController` usado pela UI contém os hooks. Porém, no startup real da UI esses hooks permanecem desligados: as ferramentas `unreal_*` não entram no catálogo nem no registry do chat.

### 2.4 Fluxo que existe hoje e diferença para o fluxo pedido

Existe um fluxo parcial de linguagem natural para ferramentas comuns:

1. `LumenWindow.send()` recebe o texto; `_worker()` chama `Agent.process_message()` (`app/ui/main_window.py:266–299`).
2. Com o controller injetado, o Agent cria `ToolCallingBridge` (`app/core/agent.py:131–160`).
3. `ToolCallingBridge.process()` lê o catálogo do controller e chama `Agent.request_tool_plan()` (`app/core/bridge.py:85–96`).
4. `request_tool_plan()` instancia `app.planner.Planner` com o provider atual e o catálogo (`app/core/agent.py:162–196`). O Planner solicita resposta JSON, valida o tipo e valida as tarefas contra a allowlist (`app/planner/planner.py:323–451`).
5. Se for plano de ação válido, o bridge chama **imediatamente** `ToolsController.run_plan()` (`app/core/bridge.py:117–134`). Se for conversa, usa a conversa comum; se for inválido, não executa (`98–115`).
6. Se uma operação viável exigir checkpoint, a execução pausa. A janela “Ferramentas e Segurança” apresenta a operação pendente e botões “APROVAR”/“RECUSAR” (`app/ui/tools_dialog.py:92–114`, `116–182`) e chama `controller.approve()`/`refuse()` (`184–226`). A janela é aberta pelo botão da UI (`app/ui/main_window.py:236–246`).

Isso **não** é o fluxo “pesquisa → `app/planning.FeaturePlanner` → mostrar o plano inteiro → aprovação do plano → execução”. A ponte atual envia o plano genérico ao executor antes de uma aprovação do plano completo; a aprovação visual existente é de checkpoint/operação. Tarefas anteriores que não exigem checkpoint podem já ter sido executadas quando uma operação posterior pausa. O conteúdo mostrado no checkpoint é a operação pendente (ferramenta, permissão, local e, quando aplicável, prévia), não o FeaturePlan completo.

---

## 3. Provider Ollama e tool calling

### 3.1 Onde é configurado

A implementação é `app/ai/ollama_provider.py`. O provider usa o endpoint local padrão `http://127.0.0.1:11434` e um modelo padrão (`app/ai/ollama_provider.py:28–45`). A fábrica registra `ollama` e o instancia por `create_provider()` (`app/ai/provider.py:162–195`). `Settings` tem campos Ollama, mas o provider padrão geral é **`mock`** (`app/config/settings.py:86–111`). A tela de configurações preenche o combobox usando `available_providers()` (`app/ui/settings_dialog.py:68–78`), portanto é possível escolher Ollama na UI; a configuração é aplicada ao Agent (`app/config/config_service.py:97–145`).

### 3.2 Function calling nativo versus JSON em prompt

**O provider Ollama não implementa function/tool calling nativo.** A assinatura de `OllamaProvider.chat()` não recebe definições de tools (`app/ai/ollama_provider.py:60–64`); o payload para `/api/chat` contém modelo, mensagens, streaming, `keep_alive` e opções, sem campo `tools` (`84–92`). Ao ler a resposta, o código extrai `message.content` e monta `AIResponse` apenas com conteúdo textual (`110–130`). O contrato comum registra `TOOL_CALL` como preparação futura e documenta que, nesta versão, respostas são `FINAL_RESPONSE` e `tool_calls` fica vazio (`app/ai/types.py:14–56`).

Há, contudo, **planejamento estruturado implementado na camada da aplicação**, por texto: `app/planner/planner.py` instrui o modelo a responder JSON com `type`, `tool` e `parameters` (`120–158`); `create_tool_plan()` envia esse system prompt ao provider, extrai/valida o JSON e produz um `Plan` (`323–451`). Assim, Ollama pode ser usado como cérebro desse planner por meio de saída JSON em texto, sujeito ao modelo obedecer ao formato; isso não é a API nativa de tools do Ollama.

Esse mecanismo está ligado ao `app.planner` (singular), que é o usado por `Agent`/`ToolCallingBridge`. **Não está ligado ao `app.planning.FeaturePlanner`**. Mesmo no planner ativo, o modelo só pode escolher tools presentes no catálogo do controller; como busca e Unreal estão desligadas no startup da UI, não pode selecioná-las nesse fluxo atual.

---

## 4. Gap analysis e veredito

> **RESPOSTA CURTA:** **A LUMEN AINDA NÃO conecta esses módulos na UI.** A GUI já tem chat em linguagem natural, um tool-planner genérico (`app/planner/`) e execução segura por `ToolsController` para as ferramentas disponíveis. Mas hoje não encadeia a busca web com `app/planning/`, não apresenta/aprova um FeaturePlan completo e não ativa `app/unreal_bridge/` na inicialização da UI. A LUMEN, portanto, não funciona hoje *apenas* como servidor MCP: há um fluxo de ferramentas na UI, mas não o agente autônomo completo descrito no pedido. Pesquisa e Unreal têm ativação explícita demonstrada no entry point MCP (`app/mcp_server/__main__.py:204–219`).

### Peças faltantes para o fluxo completo

| Arquivos a criar/modificar | Trabalho necessário | Escopo estimado |
|---|---|---|
| `main.py`; `app/ui/tools_dialog.py` (ou novo `app/ui/integrations_dialog.py`) | Tornar a configuração/ativação de pesquisa e Unreal acessível no app desktop; chamar `enable_web_search()` e `enable_unreal_bridge()` com configuração válida; exibir estado/erro. A API do controller já existe, mas o startup da UI não a chama. A pesquisa requer provider/chave de busca; Unreal requer configuração e editor acessível. | **Pequeno** para só ligar integrações por configuração existente; **médio** para UX segura/configurável na UI. |
| Novo `app/planning/orchestrator.py` (ou equivalente em `app/core/`) | Coordenar objetivo → chamada a `web_search` → `extract_research_blocks()` → `FeaturePlanner.create_plan()` → `ApprovalGate.submit()` → decisão → conversão → `ToolsController.run_plan()`. Atualmente essas peças não têm chamador/orquestrador de produção. | **Grande** |
| `app/planning/models.py` e possivelmente `app/planning/planner.py` | Representar chamadas `unreal_*` no plano aprovado e traduzi-las em tarefas executáveis. Hoje `FeaturePlan` converte artefatos para tools de arquivo e comandos para `run_command`, sem tarefas Unreal (`models.py:307–362`). Preservar os gates de `WRITE` e checkpoints já implementados no controller. | **Médio a grande** |
| `app/ui/main_window.py` e novo `app/ui/plan_review_dialog.py` (ou extensão planejada de `app/ui/tools_dialog.py`) | Direcionar o pedido para o orquestrador; mostrar evidências/fontes e o **plano completo**; oferecer aprovar/rejeitar antes de chamar execução; depois exibir progresso/resultado. Hoje o worker chama `process_message()` (`main_window.py:289–299`) e a aprovação existente é somente de checkpoint. | **Médio a grande** |
| `app/core/bridge.py` e/ou `app/core/agent.py` | Se o fluxo atual for mantido, substituir ou complementar a chamada imediata a `run_plan()` (`bridge.py:123–126`) por estado pendente de aprovação do plano inteiro. Alternativamente, fazer a UI usar o novo orquestrador e reservar o bridge atual para o fluxo de tools genérico. | **Médio** |
| Testes de integração, por exemplo novos casos em `tests/test_planning_e2e.py`, `tests/test_research_integration.py` e testes de UI | Adicionar cobertura da jornada completa em ambiente controlado: pesquisa → plano → renderização/decisão → execução pelo controller, incluindo catálogo Unreal e checkpoints. O caminho de produção hoje não percorre essa jornada integrada. | **Médio** |
| **Opcional**, se “tool calling” precisar ser nativo e não JSON em prompt: `app/ai/provider.py`, `app/ai/types.py`, `app/ai/ollama_provider.py` | Estender o contrato do provider para enviar definições de ferramentas e interpretar chamadas estruturadas retornadas pelo Ollama. Não é necessário para a abordagem atual de JSON em texto, mas é necessário para function calling nativo. | **Médio a grande** |

**O que já pode ser reaproveitado:** `ToolsController` já tem métodos condicionais de ativação, registro de `web_search` e `unreal_*`, execução via `run_plan` e checkpoints para operações Unreal de mutação (`app/tools/control.py:941–1073`, `1155–1263`). O principal trabalho é ligá-los a um orquestrador e à UX desktop, não reimplementar esse pipeline de segurança.
