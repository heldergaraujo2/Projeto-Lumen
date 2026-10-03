# Lúmen — Registro Mestre de Testes

> Documento consolidado dos testes realizados durante a evolução do sistema Lúmen.
> Este arquivo registra resultados comprovados, testes de integração real e pendências de revalidação.
>
> Branch: `feature/web-research-agent`

## 1. Estado geral

### Última suíte completa registrada

- **1598 passed**
- **49 skipped**
- **0 failed**
- Tempo registrado: **23.74s**

### Última validação específica

- `tests/test_autonomous_progress.py`
- **24 passed**
- **0 failed**
- A validação confirmou persistência e exposição de `observation_details`.

> Observação: após alterações posteriores à suíte completa, a suíte completa deve ser executada novamente antes de considerar o estado global definitivamente revalidado.

---

## 2. Regras de segurança dos testes

- Não apagar `data/learning/knowledge.json`.
- Não usar `git reset --hard`.
- Não usar `git clean -fd`.
- Não usar `git restore data/learning/knowledge.json`.
- Estado persistente de aprendizagem deve ser preservado.
- Testes destrutivos ou mutações reais no Unreal devem ser controlados e observados.
- Não considerar uma ação do Unreal validada apenas porque o MCP retornou HTTP 200.
- Sempre que possível, validar o estado antes e depois da ação.
- Para autonomia real, registrar evidências e evitar loops sem progresso.

---

## 3. Testes automatizados já realizados

### 3.1 Suíte geral do projeto

**Status: 🟢 APROVADO**

Resultado registrado:

```
1598 passed
49 skipped
0 failed
```

Abrange os testes existentes do projeto, incluindo módulos de agente, autonomia, aprendizagem, web research, Unreal, visão, ferramentas, UI e segurança.

---

## 4. Evolução autônoma

### 4.1 Progress Controller

**Status: 🟢 APROVADO**

Arquivo principal:

`app/evolution/autonomous_progress.py`

Cobertura validada:

- persistência do estado;
- recuperação do estado;
- ciclos;
- progress epoch;
- detecção de estagnação;
- contagem de repetições;
- contagem de falhas;
- recuperação;
- gaps de capacidade;
- capacidades descobertas;
- toolsets conhecidos;
- descrições de toolsets;
- observações;
- digest de observação;
- capacidade pendente;
- verificação pós-ação;
- evidências;
- contexto do planejador;
- limite de evidências.

---

### 4.2 Exaustão do progresso

**Status: 🟢 APROVADO**

Arquivo:

`tests/test_autonomous_progress_exhaustion.py`

O mecanismo não deve continuar executando indefinidamente quando não existe nova evidência/progresso.

Comportamento validado:

```
progress exhausted
    ↓
BLOCKED
    ↓
não repetir indefinidamente
```

---

### 4.3 Falhas de Unreal

**Status: 🟢 APROVADO**

Falhas de `unreal_call` são registradas como falha, geram gap e mantêm a missão em estado evolutivo em vez de simplesmente perder o contexto.

---

### 4.4 Falhas de evolução de código

**Status: 🟢 APROVADO**

Falhas de `evolve_code` são capturadas, registradas como evidência/gap e retornadas de forma controlada.

---

### 4.5 Isolamento de estado de runtime

**Status: 🟢 APROVADO**

Arquivos de:

- `data/evolution/**`
- `data/learning/**`

são tratados como estado de runtime e não devem provocar alteração indevida do código evolutivo.

Especialmente:

`data/learning/knowledge.json`

deve ser preservado.

---

## 5. Pesquisa web → aprendizagem persistente

### 5.1 Pesquisa web

**Status: 🟢 APROVADO**

Cobertura existente:

- pesquisa;
- parsing de resultados;
- snippets;
- fetch das fontes;
- URL final;
- content type;
- texto;
- truncamento;
- tratamento de erro de fetch.

Arquivo relacionado:

`tests/test_web_tools.py`

---

### 5.2 Pesquisa integrada à aprendizagem

**Status: 🟢 APROVADO**

A pesquisa integrada à missão pode alimentar o `LearningRuntime`.

Fluxo validado em testes:

```
Web Research
    ↓
findings
    ↓
LearningRuntime.ingest_research()
    ↓
KnowledgeItem
    ↓
knowledge.json
```

Também foram validados:

- deduplicação;
- persistência;
- recuperação;
- enumeração correta dos estados;
- limite de itens;
- truncamento determinístico.

---

## 6. Monitor de autonomia

**Status: 🟢 APROVADO**

Arquivo:

`app/ui/autonomous_mission_monitor.py`

Cobertura:

- leitura da missão;
- leitura do log de evolução;
- atualização periódica;
- estado;
- fase;
- ação;
- ciclo;
- resultados;
- erros;
- gaps;
- integração com a janela principal.

---

## 7. Unreal MCP — testes reais

> Os testes desta seção foram executados contra uma instância real do Unreal Editor com MCP ativo.

### PASSO 26 — Engine → MCP discovery

**Status: 🟢 APROVADO**

Resultado observado:

```
STEP_RESULT: list_toolsets
STATUS: EVOLVING
PHASE: LIST_TOOLSETS
LAST_ACTION: list_toolsets
LAST_RESULT: toolsets_listed
BROKER_CALLS: 0
KNOWN_TOOLSETS:
- ToolsetRegistry.AgentSkillToolset
- SlateInspectorToolset.SlateInspectorToolset
PROGRESS_EPOCH: 1
```

---

### PASSO 27 — list → describe

**Status: 🟢 APROVADO**

A engine identificou automaticamente um toolset ainda não descrito e solicitou sua descrição.

---

### PASSO 28 — descrição do Slate

**Status: 🟢 APROVADO**

Toolset:

`SlateInspectorToolset.SlateInspectorToolset`

Resultado registrado:

```
SLATE_DESCRIPTION: FOUND
SLATE_DESCRIPTION_LENGTH: 10242
```

---

### PASSO 29 — observe_unreal

**Status: 🟢 APROVADO**

Resultado:

```
STEP_RESULT_3: observe_unreal
STATUS: EVOLVING
PHASE: OBSERVE_UNREAL
LAST_ACTION: observe_unreal
LAST_RESULT: snapshot_ok
BROKER_CALLS: 0
OBSERVATIONS: 1
OBSERVATION_LENGTH: 30
```

A engine conseguiu adquirir um Snapshot do Slate real.

---

### PASSO 30 — Engine → Broker → MCP → Unreal

**Status: 🟢 APROVADO**

Foi realizada uma chamada real de `Click`.

Resultado relevante:

```
BROKER_CALLS: 1
PENDING_CAPABILITY:
unreal:SlateInspectorToolset.SlateInspectorToolset.Click
VERIFICATION_PASSED: False
```

Isso comprovou o caminho:

```
AutonomousMissionEngine
        ↓
AutonomousUnrealBroker
        ↓
UnrealMCPClient
        ↓
MCP
        ↓
Unreal Editor
```

---

### PASSO 31 — ação + observação pós-ação

**Status: 🟢 APROVADO COM RESSALVA**

Fluxo:

```
observe
  ↓
unreal_call
  ↓
observe novamente
  ↓
verificação
```

Resultado:

```
OBSERVATIONS: 2
PENDING_CAPABILITY:
unreal:SlateInspectorToolset.SlateInspectorToolset.Click
VERIFICATION_PASSED: True
PROGRESS_EPOCH: 6
```

**Ressalva:** a verificação atual demonstra mudança no digest da observação. Isso comprova mudança observável, mas ainda não constitui prova semântica de que a intenção específica da ação foi alcançada.

---

### PASSO 32 — decisão autônoma

**Status: 🟢 APROVADO — GUARDRAIL**

Foi executada uma decisão utilizando o Ollama local `qwen3:8b`.

Resultado registrado:

```
ACTION: research
REASON:
Progress guard rejected an Unreal call without a concrete advertised tool;
research/description evidence is required first.

OLLAMA_DECISION: PASS
EXECUCAO_DA_ACAO: NAO_EXECUTADA
```

O teste comprovou que a camada de segurança/progresso pode impedir uma ação Unreal sem evidência suficiente.

---

## 8. MCP — testes de protocolo

### Handshake

**Status: 🟢 APROVADO**

Endpoint:

`http://127.0.0.1:8000/mcp`

Resultado:

```
HTTP: 200
Mcp-Session-Id: obtido
```

---

### list_toolsets real

**Status: 🟢 APROVADO**

O MCP retornou os toolsets reais:

- `ToolsetRegistry.AgentSkillToolset`
- `SlateInspectorToolset.SlateInspectorToolset`

Também foi corrigido o parser para aceitar a representação textual real:

```
- ToolsetName: description
```

---

### describe_toolset real

**Status: 🟢 APROVADO**

A descrição real do Slate retornou catálogo de ferramentas incluindo:

- Windows
- WaitFor
- Unobserve
- Type
- Snapshot
- SelectOption
- Screenshot
- PressKey
- Observe
- ListObservers
- Hover
- FillForm
- Drag
- Click

---

## 9. Slate / Computer Control real

### Snapshot inicial

**Status: 🟢 APROVADO**

Snapshot real identificou:

```
AgeOfAether — Unreal Editor
ref=w1
```

---

### Observe

**Status: 🟢 APROVADO**

```
Observe(w1)
→ observer_2
```

A observação profunda permitiu identificar referências reais de widgets.

---

### Widgets identificados

**Status: 🟢 APROVADO**

Foram encontrados, entre outros:

- `b1` — Salvar nível atual
- `b2` — Navegar até o nível
- `b9` — Jogar
- `b12` — Iniciar simulação
- `b16` — Gaveta de Conteúdo
- `b17` — Log de Saída
- `b19` — Diagnóstico
- `b29` — Arquivo
- `b30` — Editar
- `b31` — Janela
- `b32` — Ferramentas
- `b33` — Compilar
- `b34` — Plataformas
- `b35` — Selecionar
- `b36` — Ator
- `b37` — Ajuda

---

### Hover

**Status: 🟢 APROVADO**

Testado em:

- `b16`
- `b19`

O MCP aceitou a operação.

---

### Click

**Status: 🟢 APROVADO COMO EXECUÇÃO**

Testado em:

- `b16`
- `b17`
- `b29`

O MCP retornou sucesso para a operação.

A confirmação semântica da consequência da ação permanece limitada e é tratada pelo mecanismo de observação/verificação.

---

### PressKey

**Status: 🟢 APROVADO**

```
PressKey(Escape)
→ returnValue: true
```

---

### ListObservers

**Status: 🟢 APROVADO**

Foram identificados observadores ativos, incluindo:

- `observer_1`
- `observer_2`

Foi constatado que o identificador do observador não é um widget ref e não deve ser usado diretamente como argumento de Snapshot.

---

## 10. Snapshot bruto do MCP

**Status: 🟢 APROVADO**

Teste realizado diretamente pelo `UnrealMCPClient`.

Resultado real:

```
IS_ERROR: False
RESULT_TYPE: dict
RESULT_REPR_LENGTH: 343
RESULT_STR_LENGTH: 343

HAS_AGE_OF_AETHER: True
HAS_WINDOW_REF: True
```

O payload real possui a estrutura:

```
response.result
  → content[0]
    → text
      → JSON
        → returnValue
          → Slate snapshot
```

Isso confirmou a estrutura real do payload MCP, em vez de depender de uma representação simulada.

---

## 11. Observation Details

### Teste de persistência

**Status: 🟢 APROVADO**

Teste:

`test_observation_details_are_persisted_and_exposed`

Resultado:

```
24 passed
0 failed
```

O teste confirmou:

```
observation_details
    ↓
EvolutionProgressState
    ↓
JSON
    ↓
reload
    ↓
planner_context()
```

Campos validados:

- `window_title`
- `root_ref`
- widgets
- refs de widgets
- labels
- `last_observation_digest`

---


---

## 11A. Bateria PASSOS 35A–35H — observação e ação real controlada

### PASSO 35A — root observation

**Status: 🟢 APROVADO**

Snapshot real da janela `AgeOfAether — Unreal Editor` foi adquirido pelo cliente MCP.

Evidências:
- MCP acessível;
- Snapshot real retornado;
- `w1` identificado como referência da janela;
- nenhuma mutação executada.

### PASSO 35B — ListObservers

**Status: 🟢 APROVADO**

Resultado real identificou:
- `observer_1` — observador raiz;
- `observer_2` — observador profundo em `w1`.

Nenhuma mutação executada.

### PASSO 35C — inventário estrutural do Snapshot

**Status: 🟢 APROVADO**

Snapshot profundo:
- tamanho: **5957** caracteres;
- referências descobertas: **114**;
- `b17` — Log de Saída;
- `b19` — Diagnóstico;
- `b33` — Compilar;
- `b16` — Gaveta de Conteúdo.

Nenhuma ação executada.

### PASSO 35D–35G — resolução robusta de referência

**Status: 🟢 APROVADO**

Foi constatado que a saída textual do terminal pode apresentar mojibake em rótulos acentuados. A resolução final não dependeu do texto Unicode do rótulo: a referência estrutural `[ref=b17]` foi encontrada diretamente.

Resultado:
- `b17` confirmado;
- `Log de Saída` estruturalmente identificado;
- nenhuma ação adicional executada durante a resolução.

### PASSO 35H — Click real em b17

**Status: 🟢 APROVADO COMO EXECUÇÃO / 🟡 EFEITO SEMÂNTICO NÃO CONFIRMADO**

Uma única chamada real foi executada:

```
Click(ref="b17")
→ returnValue: true
```

Evidências pós-ação:
- Snapshot antes: **5957** caracteres;
- Snapshot depois: **5957** caracteres;
- digest antes: `8e7cf1fcb2f5a9863a1f1b5e164cf37483b353798275b5090224e10f4825a78b`;
- digest depois: `8e7cf1fcb2f5a9863a1f1b5e164cf37483b353798275b5090224e10f4825a78b`;
- nenhuma linha nova;
- nenhuma linha removida;
- `b17` permaneceu presente;
- nenhuma compilação foi executada.

Conclusão: o MCP aceitou e executou o Click, mas a observação estrutural não mostrou alteração. Portanto, **não é permitido inferir que o painel foi aberto nem que qualquer efeito semântico ocorreu**.

### PASSO 36 — descoberta das ferramentas de verificação

**Status: 🟢 APROVADO**

A descrição real de `SlateInspectorToolset.SlateInspectorToolset` confirmou as ferramentas:
- `WaitFor`;
- `Snapshot`;
- `Screenshot`;
- `Observe`;
- `ListObservers`;
- `Unobserve`;
- `Click`;
- `Type`;
- `PressKey`;
- `Hover`;
- `FillForm`;
- `SelectOption`;
- `Drag`;
- `Windows`.

Descoberta especialmente relevante:
- `Screenshot` retorna `ToolsetImage` com `mimeType` e `data` Base64;
- `WaitFor` verifica presença/ausência de texto na árvore Slate;
- `Observe` mantém referências atualizadas aproximadamente a cada 100 ms.

Nenhuma ação Unreal foi executada neste passo.

### PASSO 37 — evidência visual real

**Status: 🟢 APROVADO**

Foi executado somente `Screenshot(ref="w1")`, sem mutação.

Evidências:
- `B17_PRESENTE: PASS`;
- `SCREENSHOT_MIME: image/png`;
- Base64 retornado: **1.821.048** caracteres;
- imagem decodificada: **1.365.785 bytes**;
- arquivo runtime gerado em `data/evolution/pass37_unreal_ui.png`.

A imagem é evidência de estado visual real da UI do Unreal. O arquivo é runtime/teste e **não deve ser tratado como alteração de código nem como evidência de sucesso semântico da ação de 35H**.

### Conclusão da bateria 35–37

O estado comprovado agora é:

```
MCP real
  ↓
toolset real
  ↓
Snapshot/Observe real
  ↓
widget real identificado
  ↓
Click real aceito/executado
  ↓
Snapshot pós-ação
  ↓
Screenshot real disponível
  ↓
efeito semântico ainda NÃO comprovado
```

Esta distinção deve permanecer explícita no desenvolvimento da Lúmen:

**execução aceita ≠ efeito observado ≠ resultado semântico verificado.**

---

## 12. O que já foi comprovado ponta a ponta

### 🟢 Pesquisa → aprendizagem

```
pesquisa web
→ findings
→ LearningRuntime
→ knowledge.json
```

### 🟢 Descoberta → descrição → observação

```
MCP
→ list_toolsets
→ describe_toolset
→ observe
```

### 🟢 Observação → ação → nova observação

```
observe
→ unreal_call
→ observe
→ digest
→ verification
```

### 🟢 Controle de progresso

```
ação
→ evidência
→ progresso
→ persistência
→ planner_context
```

### 🟢 Guardrail

```
ação sem evidência suficiente
→ progress guard
→ bloqueio/reorientação
```

---

## 13. Pendências identificadas

### 🔴 Verificação semântica de ações

O digest prova que a observação mudou, mas ainda não prova automaticamente que:

> "a ação pretendida produziu exatamente o resultado esperado."

Necessário evoluir para:

```
intenção
→ ação
→ observação
→ comparação com expectativa
→ evidência semântica
→ validação
```

---

### 🟡 Conversão completa do Snapshot real para observation_details

A infraestrutura de persistência já está pronta.

Ainda deve ser conectada ao Snapshot real para produzir uma representação estruturada, compacta e útil para o planejador, evitando colocar payloads gigantes ou Base64 no contexto do Ollama.

---

### 🟡 Capability Registry completo

Ainda deve ser fechada a cadeia:

```
gap
→ pesquisa
→ candidato a ferramenta
→ implementação
→ teste
→ uso real
→ validação
→ capability registry
```

---

### 🔴 Verificador objetivo de missão

Ainda falta uma camada geral capaz de afirmar, baseada em evidências:

```
objetivo atingido = verdadeiro
```

sem depender somente da decisão do modelo.

---

### 🔴 Desenvolvimento autônomo completo de jogos

Ainda não está comprovado o ciclo completo:

```
objetivo de jogo
→ planejamento
→ criação de ferramentas
→ implementação
→ Unreal
→ teste
→ observação
→ correção
→ validação
→ jogo final
```

Esse permanece como objetivo de longo prazo do sistema.

---

## 14. Próxima bateria de testes

Antes de avançar para autonomia mais ampla:

1. **Reexecutar a suíte completa após as últimas alterações.**
2. Testar Snapshot real → `observation_details`.
3. Testar `observation_details` chegando ao planner da missão.
4. Testar planner usando um widget observado para selecionar uma ferramenta concreta.
5. Testar verificação semântica pós-ação.
6. Testar gap → research → ferramenta.
7. Testar ferramenta criada → teste → registro de capability.
8. Testar recuperação de falha.
9. Testar missão objetiva com critério verificável.
10. Somente então aumentar gradualmente a autonomia real dentro do Unreal.

---

## 15. Histórico resumido

| Área | Estado |
|---|---|
| Suíte automatizada | 🟢 1598 passed / 49 skipped no último full run |
| Progress Controller | 🟢 |
| Persistência | 🟢 |
| Progress guard | 🟢 |
| Falha de Unreal | 🟢 |
| Falha de evolução | 🟢 |
| Web Research | 🟢 |
| Research → Learning | 🟢 |
| Monitor de autonomia | 🟢 |
| MCP handshake | 🟢 |
| MCP discovery real | 🟢 |
| MCP describe real | 🟢 |
| Unreal Snapshot real | 🟢 |
| Unreal Observe real | 🟢 |
| Unreal Click real | 🟢 execução |
| Unreal Hover real | 🟢 execução |
| Unreal PressKey real | 🟢 |
| Observe → Call → Observe | 🟢 com ressalva semântica |
| Ollama decision guard | 🟢 |
| observation_details | 🟢 |
| Verificação semântica | 🔴 |
| Gap → ferramenta automática | 🟡 |
| Capability Registry fechado | 🟡 |
| Verificador objetivo de missão | 🔴 |
| Game development autônomo completo | 🔴 |

---

## 16. Regra para atualizações futuras

Este documento deve ser atualizado sempre que uma nova bateria significativa de testes for concluída.

Cada atualização deve registrar:

- data/bateria;
- teste executado;
- comando ou procedimento quando relevante;
- resultado;
- evidência objetiva;
- limitações;
- próxima pendência.

Um teste só deve receber **🟢 APROVADO** quando houver evidência objetiva suficiente para reproduzir ou verificar o resultado.
