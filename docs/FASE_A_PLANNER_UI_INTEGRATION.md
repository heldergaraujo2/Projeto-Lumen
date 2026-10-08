# Fase A — investigação do planner de tools usado pela UI

**Baseline analisado antes da implementação da Fase B.** Esta nota registra o estado do código anterior a qualquer alteração de integração.

## 1. Qual prompt produz o JSON de ferramentas?

O planner usado pelo chat não é `app/planning/planner.py`. É `app/planner/planner.py` (singular), chamado por `Agent.request_tool_plan()`.

- O template exato é `_TOOL_PLANNING_PROMPT`, em `app/planner/planner.py:120–158`. Ele pede somente JSON, com `type` (`conversation` ou `plan`) e, em um plano, tarefas contendo `tool` e `parameters`.
- `Planner.create_tool_plan()` executa esse fluxo em `app/planner/planner.py:323–451`: monta o prompt, chama `provider.chat()`, extrai o JSON e valida as tarefas.
- `_build_tool_system_prompt()` preenche a seção `{catalog}` com `catalog_prompt_section(self._catalog)` em `app/planner/planner.py:474–495`.
- O caminho chamado pela UI começa em `ToolCallingBridge.process()`, que pede `controller.planning_catalog()` e entrega esse catálogo a `Agent.request_tool_plan()` (`app/core/bridge.py:85–96`; `app/core/agent.py:162–196`).

Portanto, alterar somente o texto do prompt não é a integração correta: a allowlist que chega ao prompt e a validação posterior são igualmente necessárias.

## 2. Como o catálogo chega ao modelo?

O catálogo é **dinâmico na montagem do prompt, mas baseado em declarações estáticas**:

1. `app/planner/catalog.py:66–338` declara `TOOL_SPECS`: nomes, descrições e parâmetros tipados de cada ferramenta.
2. `build_catalog()` transforma essas declarações em um dicionário serializável e filtra ferramentas por flags (`include_terminal`, `include_web_search`, `include_unreal`) em `app/planner/catalog.py:341–377`.
3. `ToolsController.planning_catalog()` calcula essas flags com o estado de runtime do controller (`app/tools/control.py:1015–1032`).
4. `catalog_prompt_section()` renderiza nomes, descrições e parâmetros para o prompt (`app/planner/catalog.py:388–397`).
5. `validate_task_tool()` rejeita ferramenta ausente do catálogo, parâmetros desconhecidos/ausentes ou tipos incorretos (`app/planner/catalog.py:416–488`). O parser do Planner chama essa validação para cada tarefa (`app/planner/planner.py:584–592`).

O LLM, portanto, não escolhe nomes arbitrários: escolhe entre a allowlist dinâmica daquele pedido, e a resposta é validada novamente antes de virar plano executável.

## 3. O que é preciso para adicionar as ferramentas pedidas?

As declarações de protocolo **já existem** na baseline:

- `web_search`: `app/planner/catalog.py:200–214`.
- As sete specs Unreal: `app/planner/catalog.py:220–337`, incluindo as três consultas pedidas (`unreal_get_info`, `unreal_describe_object`, `unreal_search_assets`) e quatro tools mutáveis.

Também existem os pontos de registro condicional no `ToolsController`:

- Pesquisa: `enable_web_search()` e registro de `WebSearchTool` (`app/tools/control.py:941–962`, `1060–1066`).
- Unreal: `enable_unreal_bridge()`, inclusão no catálogo e registro de ferramentas (`app/tools/control.py:972–1013`, `1028–1032`, `1067–1073`).

O que falta na baseline da UI é habilitar/controlar essas integrações no desktop: por padrão o controller guarda `_web_search_provider = None` e `_unreal_client = None` (`app/tools/control.py:436–440`); por isso os flags são falsos e as ferramentas não chegam ao prompt. Além disso, `build_unreal_registry()` retorna as sete classes (`app/unreal_bridge/tools.py:575–592`) e `include_unreal=True` expõe atualmente as sete specs. Para esta fase é necessário aplicar o modo “somente leitura” **tanto no catálogo como no registry** da instância usada pela UI, mantendo fora da allowlist as quatro ferramentas mutáveis (`unreal_set_property`, `unreal_call_function`, `unreal_create_blueprint_class`, `unreal_add_component`). A configuração padrão dos demais consumers, inclusive o MCP, deve continuar compatível.

Há ainda um detalhe de política a tratar: na baseline, as três consultas Unreal herdam `required_permission=WRITE` e `ToolDefinition.destructive=True` de `UnrealTool` (`app/unreal_bridge/tools.py:53–80`), embora as operações em si sejam de consulta. A implementação deverá dar às consultas o gate `READ` e marcá-las não destrutivas; as quatro ferramentas mutáveis permanecem `WRITE` e seguem com checkpoint do controller (`app/tools/control.py:296–312`). `web_search` já exige `READ` (`app/research/tool.py:40–56`).

### Complexidade adicional: resumo

Não é necessário inventar outro formato JSON ou migrar o fluxo para `app/planning/`. É preciso manter alinhados **quatro** pontos: habilitação explícita na UI, `ToolSpec`/catálogo, registry real disponível durante `run_plan()` e validação/segurança. Para o Unreal, também é obrigatório um filtro read-only que impeça as tools mutáveis de chegarem ao catálogo e ao registry desta UI. Adicionar só uma linha ao prompt não satisfaria esses requisitos.

## 4. Decisão arquitetural

Não migrar para `app/planning/`: esse pacote é um FeaturePlanner voltado a gerar artefatos/commands e sua conversão para execução cobre arquivos e `run_command`, não chamadas genéricas às tools Unreal (`app/planning/models.py:284–385`). O fluxo da tarefa já existe em `app/planner/` e `ToolCallingBridge`; ampliar seu catálogo condicionado pelo controller é menor, mais direto e mantém a mesma cadeia de validação/execução usada pela UI.

## 5. Validação JSON prevista para a Fase C

A baseline já trata falhas de forma controlada: `_extract_json()` converte ausência/JSON malformado em `InvalidPlanError` (`app/planner/planner.py:515–541`); `create_tool_plan()` transforma isso em `ToolPlanResult(kind="invalid")` sem plano executável (`app/planner/planner.py:403–451`). Uma tool não allowlisted é rejeitada por `validate_task_tool()` (`app/planner/catalog.py:435–442`), também virando plano inválido. `ToolCallingBridge` retorna mensagem de falha e não chama `run_plan()` para `kind="invalid"` (`app/core/bridge.py:103–115`). Exceções inesperadas no worker da janela são encaminhadas como erro visível e liberam o estado ocupado (`app/ui/main_window.py:289–302`, `304–334`).

A baseline já tem testes para tool inventada e resposta fora do protocolo (`tests/test_planner_tools.py:187–219`; `tests/test_agent_bridge.py:143–170`), mas a Fase C adicionará uma resposta com sintaxe JSON especificamente malformada e verificará o resultado pelo caminho Agent/bridge, confirmando que o controller não inicia execução.
