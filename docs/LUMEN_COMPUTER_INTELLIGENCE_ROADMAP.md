# LUMEN — COMPUTER INTELLIGENCE ROADMAP

**Documento:** Roadmap de evolução da Inteligência de Computador da Lumen  
**Status:** PLANEJAMENTO OFICIAL  
**Objetivo:** Evoluir a Lumen de uma plataforma de Agent com ferramentas para um Agent local-first capaz de compreender, controlar, verificar e aprender com o computador, com foco especial em Windows e Unreal Engine.  
**Provider local inicial:** Ollama  
**Modelo principal inicial:** `qwen2.5-coder:7b-instruct-q8_0`

---

## 1. VISÃO

A Lumen não será uma cópia de UFO², UI-TARS, Agent S, OpenAdapt ou qualquer outro projeto externo.

Esses projetos serão utilizados como **referências de capacidades**, respeitando suas respectivas licenças, para identificar o que a Lumen deve:

- **REPLICAR** — capacidade conceitual/funcional necessária;
- **ADAPTAR** — incorporar a ideia à arquitetura própria da Lumen;
- **SUPERAR** — implementar com maior segurança, integração, verificação ou generalidade;
- **CRIAR** — capacidade própria da Lumen que não deve depender de um projeto externo.

### Princípio central

> A Lumen deve incorporar capacidades, não copiar projetos.

---

# 2. ARQUITETURA-ALVO

\`\`\`text
                           USER
                            │
                            ▼
                      LUMEN AGENT
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
           Planner        Memory       Research
              │             │             │
              └─────────────┼─────────────┘
                            ▼
                     Provider Manager
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
           Ollama        Other API      Future Local
              │
       ┌──────┴──────┐
       ▼             ▼
 Qwen Coder       Vision Model
       │             │
       └──────┬──────┘
              ▼
      Computer Intelligence
              │
      ┌───────┼────────┐
      ▼       ▼        ▼
     UIA    Native    Vision
      │       │        │
      └───────┼────────┘
              ▼
          Grounding
              │
              ▼
       Action Resolver
              │
              ▼
        Policy / Safety
              │
              ▼
        ComputerControl
              │
      ┌───────┼────────┐
      ▼       ▼        ▼
    Mouse   Keyboard  Windows
                         │
                         ▼
                    Unreal Engine
                         │
                         ▼
                    Verification
                         │
               ┌─────────┴─────────┐
               ▼                   ▼
            Success             Failure
               │                   │
               ▼                   ▼
             Memory             Recovery
\`\`\`

---

# 3. PRINCÍPIOS ARQUITETURAIS

1. **Local-first:** a Lumen deve poder operar sem depender de APIs externas quando um Provider local adequado estiver disponível.
2. **Provider ≠ Lumen:** Ollama é um Provider; o Agent, Planner, Memory, Tools, Safety e Computer Intelligence pertencem à Lumen.
3. **Reasoning ≠ Vision:** o modelo de raciocínio/código e o modelo visual devem ser desacoplados.
4. **Vision ≠ Grounding:** reconhecer um elemento e determinar um alvo acionável são responsabilidades diferentes.
5. **Structured-first:** usar APIs, UI Automation e informações estruturadas antes de depender de pixels.
6. **Computer Control como subsistema:** mouse/teclado nunca devem ser o único mecanismo de automação.
7. **Modelo não controla diretamente o Windows:** toda ação passa por Tool → Policy → Permission → Checkpoint → execução → Audit → Verification.
8. **Verification-first:** uma ação não é considerada concluída apenas porque o comando foi enviado.
9. **Recovery:** falhas devem produzir diagnóstico, alternativa e recuperação controlada.
10. **Unreal-first compatibility:** a arquitetura deve permitir trabalhar com Unreal por arquivos, APIs, terminal e Computer Control.
11. **Auditabilidade:** cada ação relevante deve ser rastreável.
12. **Licença e atribuição:** código externo só poderá ser incorporado quando permitido e após análise de licença; referências arquiteturais não significam cópia de implementação.

---

# 4. PROJETOS EXTERNOS DE REFERÊNCIA

## 4.1 Microsoft UFO²

### Utilização prevista
Principal referência para integração Windows.

### Capacidades a estudar
- Windows UI Automation (UIA)
- Win32
- WinCOM
- detecção estruturada de controles
- integração GUI/API
- Host Agent / App Agent
- estados de execução
- mecanismos de percepção visual para controles não estruturados

### Classificação inicial
- **ADAPTAR:** arquitetura de interação Windows
- **ADAPTAR:** UIA + mecanismos nativos
- **SUPERAR:** segurança, permissions, checkpoints e auditoria integrados à Lumen

---

## 4.2 ByteDance UI-TARS / UI-TARS Desktop

### Utilização prevista
Referência prioritária para **grounding visual, computer-use e interação visual**. UI-TARS não será tratado como a VisionProvider única da Lumen; sua função principal no roadmap é servir como candidato/referência para Grounding e Computer Use.

### Capacidades a estudar
- screenshot understanding
- visual grounding
- coordenadas
- bounding boxes
- mouse
- teclado
- operações GUI
- execução local
- representação de ações

### Classificação inicial
- **ADAPTAR:** grounding visual
- **ADAPTAR:** representação de ações
- **ADAPTAR:** padrões de computer-use
- **SUPERAR:** integração com UIA/native-first e safety chain da Lumen

---

## 4.3 Simular Agent S

### Utilização prevista
Referência para arquitetura de Computer-Use Agent e separação entre raciocínio e grounding.

### Capacidades a estudar
- Agent reasoning
- grounding model separado
- GUI execution
- observação
- reflexão
- trajetórias de execução
- recuperação

### Classificação inicial
- **ADAPTAR:** separação Reasoning / Grounding
- **ADAPTAR:** ciclos de observação/reflexão
- **SUPERAR:** integração com Planner, Memory, PermissionManager e Verification da Lumen

---

## 4.4 OpenAdapt

### Utilização prevista
Referência para aprendizado de workflows e transformação de tarefas demonstradas em execução mais determinística.

### Capacidades a estudar
- gravação de workflow
- demonstração humana
- reprodução determinística
- experiência
- verificação
- reparo
- autoridade humana

### Classificação inicial
- **ESTUDAR:** primeiras fases
- **ADAPTAR:** workflow learning
- **CRIAR:** sistema próprio de experiência e estratégias integrado à Memory da Lumen

---

## 4.5 Browser-use

### Utilização prevista
Referência especializada para automação de navegador.

### Classificação inicial
- **ADAPTAR:** browser automation quando aplicável
- **NÃO usar como núcleo:** Computer Control geral da Lumen

---

# 5. HIERARQUIA DE RESOLUÇÃO DE ALVOS

A Lumen deve procurar a forma mais estruturada e confiável disponível antes de recorrer à visão ou coordenadas brutas.

\`\`\`text
1. API / comando nativo
2. UI Automation
3. Accessibility / UI tree
4. Win32 / WinCOM
5. DOM / browser structure
6. Template matching
7. Vision grounding
8. Coordenadas / mouse e teclado brutos
\`\`\`

Essa ordem pode ser alterada por política específica de uma aplicação, mas não deve ser ignorada sem justificativa.

---

# 6. FASE 0 — AUDITORIA E ARQUITETURA

## Objetivo

Mapear o estado atual da Lumen e comparar capacidades com UFO², UI-TARS, Agent S, OpenAdapt e Browser-use antes de implementar grandes mudanças.

## Entregáveis

- `docs/COMPUTER_CONTROL_AUDIT.md`
- `docs/EXTERNAL_PROJECTS.md`
- `docs/INTEGRATION_MATRIX.md`
- `docs/VISION_ARCHITECTURE.md`
- `docs/OLLAMA_ARCHITECTURE.md`

## Auditoria mínima

- screenshot
- captura de janela
- isolamento de janela
- UIA
- Win32
- WinCOM
- mouse
- teclado
- clipboard
- vision
- OCR
- bounding boxes
- grounding
- coordenadas
- planning
- verification
- retry
- recovery
- memory
- workflow learning
- local model
- Ollama
- model routing
- permissions
- audit
- action budgets
- privacy

## Critério de conclusão

Nenhuma grande implementação de Computer Control deve começar sem a matriz de integração revisada.

**Status:** PENDENTE

---

# 7. FASE 1 — OLLAMA PROVIDER

## Objetivo

Adicionar Ollama como Provider local oficial da Lumen.

## Modelo inicial

\`\`\`text
ollama
└── qwen2.5-coder:7b-instruct-q8_0
\`\`\`

## Responsabilidades

- coding
- reasoning
- planning
- análise
- tool selection
- interpretação de resultados

## Requisitos

- Provider isolado pelo ProviderManager
- configuração por ambiente/config
- timeout
- tratamento de erros
- health check
- observabilidade
- custos/tempo local registrados quando possível
- testes unitários
- fallback configurável

## Critério de conclusão

A Lumen deve executar um fluxo completo:

\`\`\`text
Lumen → Ollama → Qwen Coder → Tool → Resultado → Lumen
\`\`\`

sem depender de API externa.

**Status:** CONCLUÍDA 🟩

---

# 8. FASE 2 — TOOL / AGENT PROTOCOL

## Objetivo

Separar intenção do modelo, resolução de ferramenta e execução.

Exemplo conceitual:

\`\`\`json
{
  "tool": "computer.click",
  "target": "Compile",
  "reason": "Compilar o projeto"
}
\`\`\`

O modelo não deve controlar diretamente coordenadas ou drivers.

## Critério de conclusão

Qualquer Tool deve possuir contrato estruturado, validação e resultado verificável.

**Status:** 🟩 CONCLUÍDA — ToolCall estruturado, validação fail-closed, gateway seguro e integração com o pipeline de execução validados pelo CI.

---

# 9. FASE 3 — COMPUTER INTELLIGENCE

## Objetivo

Criar a camada própria de inteligência de computador da Lumen.

Estrutura-alvo:

\`\`\`text
app/
  computer/
    intelligence/
    perception/
    grounding/
    targeting/
    actions/
    verification/
    recovery/
\`\`\`

## Responsabilidades

- percepção
- identificação de estado
- seleção de alvo
- grounding
- planejamento de ação
- resolução do mecanismo de execução
- verificação
- recuperação

**Status:** 🟩 CONCLUÍDA — implementação F3 validada pela CI (1065 passed / 1 skipped / 0 failed).

---

 
# 10. FASE 4 — WINDOWS NATIVE CONTROL

## Objetivo

Construir controle Windows estruturado antes de depender de visão.

## Capacidades

- UI Automation
- Win32
- WinCOM quando necessário
- detecção de janela
- foco de janela
- controles
- propriedades de controles
- árvore de UI
- ações nativas

## Estratégia

\`\`\`text
Target
 ↓
Native resolver
 ↓
UIA / Win32 / WinCOM
 ↓
Encontrou?
 ├── SIM → executar
 └── NÃO → Vision/Grounding
\`\`\`

**Status:** 🟩 CONCLUÍDA — CI final: 1073 passed / 1 skipped / 0 failed.

---

# 11. FASE 5 — VISION PROVIDER

## Objetivo

Adicionar visão como Provider independente.

A Lumen não deve ficar presa a um único modelo visual.

Interface conceitual:

\`\`\`text
VisionProvider
├── LLaVA — candidato inicial de VisionProvider
├── Qwen-VL
├── Qwen3-VL — candidato prioritário
├── outros VLMs locais compatíveis
└── futuros Providers
\`\`\`

## Responsabilidades

- screenshot understanding
- OCR
- identificação de elementos
- regiões
- texto
- estados visuais
- descrições estruturadas

## Regra

`qwen2.5-coder:7b-instruct-q8_0` permanece como modelo textual/código; não deve ser tratado como Vision Model.

**Status:** 🟩 CONCLUÍDA — CI final: 1084 passed / 1 skipped / 0 failed.

---

# 12. FASE 6 — GROUNDING ENGINE

## Objetivo

Transformar percepção em alvo acionável.

**Candidatos prioritários a avaliar:**
- UI-TARS / UI-TARS Desktop — grounding e computer-use;
- Qwen3-VL — grounding multimodal;
- grounding próprio da Lumen combinando UIA + visão + OCR + templates.

A Lumen não ficará acoplada a nenhum desses projetos. Eles serão avaliados por benchmarks próprios e integrados através de contratos da Lumen.

Exemplo:

\`\`\`text
Vision:
"Existe um botão Compile."

Grounding:
"Esse botão corresponde à região X/Y/W/H."

Resolver:
"Centro do alvo = X/Y."

Validator:
"Coordenada autorizada?"

ComputerControl:
"Click."
\`\`\`

## Candidatos e fontes possíveis

- UIA
- accessibility tree
- native APIs
- DOM/browser structure
- templates
- OCR
- bounding boxes
- VisionProvider
- **UI-TARS / UI-TARS Desktop — candidato prioritário para estudar grounding e computer-use**
- **Qwen3-VL — candidato prioritário para grounding multimodal**
- coordenadas

## Segurança

A coordenada final deve ser validada contra:

- janela autorizada
- região autorizada
- resolução atual
- escala/DPI
- confiança mínima
- ação permitida
- orçamento de ações

**Status:** 🟩 CONCLUÍDA — CI final prevista após atualização de continuidade; última CI funcional: 1094 passed / 1 skipped / 0 failed.

---

# 13. FASE 7 — COMPUTER CONTROL SEGURO

## Objetivo

Consolidar mouse, teclado, clipboard, janelas e screenshots dentro da cadeia de segurança da Lumen.

## Capacidades

\`\`\`text
ComputerControl
├── mouse
│   ├── move
│   ├── click
│   ├── double_click
│   ├── right_click
│   ├── drag
│   └── scroll
├── keyboard
│   ├── press
│   ├── hotkey
│   └── type
├── clipboard
├── window
│   ├── focus
│   ├── minimize
│   ├── maximize
│   └── close
└── screenshot
\`\`\`

## Cadeia obrigatória

\`\`\`text
LLM
 ↓
Tool Request
 ↓
Policy
 ↓
PermissionManager
 ↓
Scope validation
 ↓
Checkpoint
 ↓
ComputerControl
 ↓
Action
 ↓
Audit
 ↓
Verification
\`\`\`

## Critério

O modelo nunca recebe acesso irrestrito ao computador.

**Status: 🟩 CONCLUÍDA — CI final: 1104 passed / 1 skipped / 0 failed.

---

# 14. FASE 8 — VERIFICATION + RECOVERY

## Objetivo

Garantir que a Lumen confirme resultados e saiba reagir a falhas.

## Ciclo

\`\`\`text
Observe
 ↓
Plan
 ↓
Act
 ↓
Observe
 ↓
Verify
 ↓
Success?
 ├── SIM → continue
 └── NÃO → Diagnose
                 ↓
               Retry
                 ↓
          Alternative target
                 ↓
             Recovery
                 ↓
             Verify
\`\`\`

## Tipos de falha

- alvo não encontrado
- janela errada
- foco perdido
- ação bloqueada
- mudança inesperada de UI
- timeout
- screenshot inválido
- baixa confiança visual
- resultado inesperado
- ação parcialmente executada

**Status:** PENDENTE

---

# 15. FASE 9 — UNREAL ENGINE AGENT

## Objetivo

Especializar a Lumen para trabalhar com Unreal Engine.

## Capacidades previstas

- projeto
- editor
- Content Browser
- assets
- Blueprint
- C++
- actors
- components
- levels
- materials
- packaging
- build
- testes

## Estratégia

Sempre que houver mecanismo estruturado:

\`\`\`text
Arquivo / API / CLI / integração
        ↓
preferir
        ↓
Computer Control
\`\`\`

Computer Control será usado quando necessário para operações que não possuam interface estruturada suficiente.

## Exemplo

\`\`\`text
"Crie um sistema de inventário."
 ↓
Qwen Coder
 ↓
Planner
 ↓
UnrealAgent
 ↓
Filesystem / C++ / Blueprint
 ↓
Unreal
 ↓
ComputerControl quando necessário
 ↓
Build
 ↓
Verification
 ↓
Tests
 ↓
Result
\`\`\`

**Status:** PENDENTE

---

# 16. FASE 10 — WORKFLOW LEARNING

## Objetivo

Registrar tarefas bem-sucedidas e transformar experiências repetidas em workflows.

## Dados

- objetivo
- contexto
- ações
- screenshots quando apropriado
- estado
- resultados
- falhas
- correções
- caminho bem-sucedido
- métricas

## Resultado

\`\`\`text
Goal
 ↓
Trajectory
 ↓
Successful execution
 ↓
Workflow
 ↓
Deterministic execution
\`\`\`

## Princípio

Workflow aprendido não elimina Verification, Permission ou Audit.

**Status:** PENDENTE

---

# 17. FASE 11 — AUTONOMOUS AGENT

## Objetivo

Unir planejamento, pesquisa, ferramentas, Computer Control, memória, verificação e recuperação.

Fluxo:

\`\`\`text
Goal
 ↓
Research
 ↓
Understand
 ↓
Plan
 ↓
Execute
 ↓
Observe
 ↓
Verify
 ↓
Correct
 ↓
Test
 ↓
Report
 ↓
Memory
\`\`\`

## Critério

A Lumen deve conseguir conduzir tarefas multi-etapas mantendo estado, respeitando permissões e recuperando falhas.

**Status:** PENDENTE

---

# 18. FASE 12 — CONTINUOUS LEARNING / EVOLUTION

## Objetivo

Usar experiência acumulada para melhorar planejamento e execução.

Fluxo:

\`\`\`text
Experience Memory
 ↓
Successful Workflows
 ↓
Failures
 ↓
Corrections
 ↓
Strategies
 ↓
Metrics
 ↓
Improved Planning
 ↓
Better Execution
 ↓
New Experience
\`\`\`

## Importante

"Aprender" inicialmente significa melhorar memória, estratégias, workflows e decisões com evidências registradas.

Não significa alterar automaticamente o próprio código ou modelo em produção sem controle.

**Status:** PENDENTE

---

# 19. MARCOS DE IMPLEMENTAÇÃO

## MARCO 1 — LUMEN LOCAL

Inclui:

- Fase 0
- Fase 1
- Fase 2

### Resultado

Lumen + Ollama + Qwen Coder + Tools + Planner.

**Status:** PENDENTE

---

## MARCO 2 — LUMEN PERCEBE O COMPUTADOR

Inclui:

- Fase 3
- Fase 4
- Fase 5
- Fase 6

### Resultado

Lumen consegue trabalhar com Windows estruturado e percepção visual.

**Status:** PENDENTE

---

## MARCO 3 — LUMEN CONTROLA O COMPUTADOR

Inclui:

- Fase 7
- Fase 8

### Resultado

Lumen executa ações com permissões, checkpoints, auditoria, verificação e recovery.

**Status:** PENDENTE

---

## MARCO 4 — LUMEN CONTROLA UNREAL

Inclui:

- Fase 9

### Resultado

Lumen trabalha efetivamente com projetos Unreal.

**Status:** PENDENTE

---

## MARCO 5 — LUMEN APRENDE WORKFLOWS

Inclui:

- Fase 10

### Resultado

Lumen reduz raciocínio desnecessário em tarefas repetitivas através de workflows verificados.

**Status:** PENDENTE

---

## MARCO 6 — LUMEN AGENT EVOLUTIVO

Inclui:

- Fase 11
- Fase 12

### Resultado

Lumen opera como Agent generalista local-first com memória, planejamento, Computer Control, recuperação, workflows e evolução baseada em experiência.

**Status:** PENDENTE

---

# 20. REGRAS DE IMPLEMENTAÇÃO

1. **NÃO CRIE OUTRA LUMEN. ALTERE SEMPRE A LUMEN EXISTENTE.**
2. Não criar cópias, backups ou ZIPs dentro do workspace.
3. Usar `/tmp` para artefatos temporários quando necessário.
4. Cada fase deve possuir testes antes de avançar.
5. Nenhuma capacidade externa deve ser copiada sem análise de licença.
6. Código externo deve ser tratado de acordo com sua licença e obrigações.
7. Não substituir a arquitetura da Lumen por um projeto externo.
8. Não criar dependência desnecessária de um único modelo visual.
9. Não acoplar o Agent diretamente ao driver de mouse/teclado.
10. Não permitir ação de computador sem validação de Policy/Permission.
11. Toda ação relevante deve possuir Audit.
12. Toda ação crítica deve possuir Verification.
13. Toda recuperação deve respeitar limites de tentativa e ação.
14. Mudanças devem ser documentadas em `PROJECT_MEMORY/` quando aplicável.
15. Atualizar estado, decisões, tarefas, testes e handoff após marcos relevantes.
16. Preservar compatibilidade com o restante da Lumen sempre que possível.
17. Testes de Computer Control real devem ser realizados em máquina Windows apropriada.
18. Nunca considerar testes FakeDriver suficientes para validar comportamento real do Windows.
19. Screenshots enviados a modelos externos exigem tratamento explícito de privacidade, escopo e consentimento.
20. A Lumen deve permanecer utilizável mesmo quando Vision Provider estiver indisponível.

---

# 21. CRITÉRIO GLOBAL DE CONCLUSÃO

O roadmap será considerado concluído quando a Lumen possuir:

- Provider local Ollama;
- Qwen Coder integrado;
- VisionProvider desacoplado;
- GroundingEngine;
- Computer Intelligence;
- UI Automation;
- Windows native control;
- Computer Control seguro;
- Permission/Policy/Checkpoint/Audit integrados;
- Verification;
- Recovery;
- Unreal Agent;
- Workflow Learning;
- Memory/Experience integrada;
- Agent multi-etapas;
- mecanismos de evolução baseados em experiência;
- testes automatizados;
- testes reais de Windows;
- documentação e handoff atualizados.

---

# 22. PRINCÍPIO FINAL

> **A Lumen não deve apenas controlar o computador. Ela deve entender o estado do computador, escolher a melhor forma de agir, executar com segurança, verificar o resultado, recuperar falhas, registrar a experiência e usar essa experiência para executar melhor no futuro.**

Este documento é o roadmap de referência para a evolução de Computer Intelligence da Lumen.


---

# 23. MASTER IMPLEMENTATION ROADMAP — LUMEN EVOLUTION EDITION

> Esta seção amplia e consolida o roadmap anterior. As fases abaixo são a sequência oficial de implementação para transformar a Lumen em um Agent local-first capaz de pesquisar, aprender, experimentar, melhorar suas próprias capacidades e continuar segura durante esse processo.

## 23.1 LEGENDA DE STATUS

- 🟩 **CONCLUÍDO** — implementado, testado e documentado com evidência.
- 🟥 **PENDENTE** — ainda não concluído como capacidade oficial.
- 🟨 **EM PROGRESSO** — existe implementação parcial, mas o critério completo ainda não foi atingido.

**Regra:** uma fase só pode virar 🟩 quando seu critério de conclusão estiver comprovado por testes/evidências. A existência de código parcial não transforma uma fase em concluída.

---

## 23.2 FASES OFICIAIS DE IMPLEMENTAÇÃO

### FASE 0 — BASELINE, AUDITORIA E CONTRATOS
**Status: 🟥 PENDENTE**

Objetivo:
- auditar a arquitetura atual;
- mapear capacidades existentes;
- definir contratos de Provider, Tool, Memory, Research, Vision e Evolution;
- estabelecer benchmarks e testes de baseline;
- definir o que pode e não pode ser alterado pelo Evolution System.

Critérios:
- baseline reproduzível;
- matriz de capacidades;
- contratos versionados;
- threat model;
- métricas iniciais;
- documentação sincronizada.

---

### FASE 1 — LOCAL PROVIDER FOUNDATION
**Status: 🟥 PENDENTE**

Implementar Provider local oficial com Ollama.

Modelo inicial:
- `qwen2.5-coder:7b-instruct-q8_0`

Responsabilidades:
- reasoning;
- coding;
- planning;
- análise;
- seleção de ferramentas;
- interpretação de resultados.

Requisitos:
- timeout;
- health check;
- observabilidade;
- configuração;
- fallback;
- isolamento do ProviderManager;
- testes.

**Regra:** Ollama é Provider; não é a Lumen.

---

### FASE 2 — RESEARCH ENGINE
**Status: 🟥 PENDENTE**

Criar capacidade nativa de pesquisa.

Fontes possíveis:
- web search;
- páginas;
- documentação;
- GitHub;
- PDFs;
- vídeos;
- artigos;
- repositórios;
- fontes locais.

Pipeline:

```text
GOAL
 ↓
Research Plan
 ↓
Search
 ↓
Collect
 ↓
Extract
 ↓
Normalize
 ↓
Compare Sources
 ↓
Synthesize
 ↓
Verify
 ↓
Store
```

Requisitos:
- fontes registradas;
- deduplicação;
- rastreabilidade;
- atualização temporal;
- detecção de conflito;
- limites de custo/tempo;
- proteção contra prompt injection em conteúdo pesquisado.

---

### FASE 3 — KNOWLEDGE + EXPERIENCE MEMORY
**Status: 🟥 PENDENTE**

Separar:
- conhecimento sobre o mundo;
- memória operacional;
- experiência;
- decisões;
- sucessos;
- falhas;
- estratégias;
- evidências de habilidade.

Qdrant poderá ser usado para busca semântica, mas não será tratado como "a memória".

Arquitetura prevista:

```text
Memory Engine
├── Working Memory
├── Knowledge
├── Experience
├── Decisions
├── Goals
├── Failures
├── Successes
├── Strategies
├── Skill Evidence
└── Semantic Index
      └── Qdrant (quando adotado)
```

---

### FASE 4 — TOOL / AGENT PROTOCOL
**Status: 🟥 PENDENTE**

Toda intenção deve passar por contrato estruturado:

```text
Intent
 ↓
Plan
 ↓
Tool Request
 ↓
Validation
 ↓
Permission
 ↓
Checkpoint
 ↓
Execution
 ↓
Audit
 ↓
Verification
```

O modelo nunca recebe acesso direto ao driver, filesystem, terminal ou Windows.

---

### FASE 5 — COMPUTER INTELLIGENCE
**Status: 🟥 PENDENTE**

Criar camada unificada para:
- percepção;
- estado do computador;
- targeting;
- grounding;
- action resolution;
- observação;
- verificação;
- recovery.

Hierarquia padrão:

```text
API / Native
 ↓
UI Automation
 ↓
Accessibility / UI Tree
 ↓
Win32 / WinCOM
 ↓
DOM
 ↓
Template
 ↓
Vision Grounding
 ↓
Raw Coordinates
```

---

### FASE 6 — WINDOWS NATIVE INTELLIGENCE
**Status: 🟥 PENDENTE**

Implementar:
- UIA;
- Win32;
- WinCOM quando necessário;
- janela/foco;
- propriedades;
- árvore de controles;
- ações estruturadas.

Objetivo:
**não usar visão quando o próprio Windows já fornece uma representação melhor do alvo.**

---

### FASE 7 — VISION PROVIDER
**Status: 🟥 PENDENTE**

Criar interface visual desacoplada.

Providers/candidatos:
- **LLaVA — candidato inicial de VisionProvider**;
- **Qwen-VL**;
- **Qwen3-VL — candidato prioritário**;
- outros VLMs locais;
- futuros Providers.

**Regra arquitetural:** VisionProvider interpreta a tela; não executa ações diretamente.

LLaVA é um candidato inicial, não um componente obrigatório permanente. A Lumen deverá conseguir trocar o modelo visual sem reescrever Computer Intelligence ou Computer Control.

Responsabilidades:
- screenshot understanding;
- OCR;
- identificação;
- regiões;
- estados visuais;
- descrição estruturada.

---

### FASE 8 — GROUNDING ENGINE
**Status: 🟥 PENDENTE**

Transformar percepção em alvo acionável.

Validações:
- janela;
- região;
- DPI;
- escala;
- resolução;
- confiança;
- tipo de ação;
- orçamento;
- permissão.

Nenhuma coordenada visual deve ir diretamente para o driver.

---

### FASE 9 — SECURE COMPUTER CONTROL
**Status: 🟥 PENDENTE**

Consolidar:
- mouse;
- teclado;
- clipboard;
- janelas;
- screenshots;
- drivers Windows.

Backend possível:
- PyAutoGUI;
- PyDirectInput;
- MSS;
- driver nativo;
- outros adaptadores.

Essas bibliotecas são **backends**, não a arquitetura de segurança.

Cadeia obrigatória:

```text
Intent
 → Policy
 → PermissionManager
 → Scope
 → Action Budget
 → Checkpoint
 → Driver
 → Audit
 → Verification
```

---

### FASE 10 — VERIFICATION, RECOVERY E REGRESSION
**Status: 🟥 PENDENTE**

Criar:
- verification engine;
- failure classifier;
- retry controlado;
- alternative strategy;
- recovery;
- regression detection;
- action budgets;
- timeout/cost budgets.

Regra:
**executar não significa concluir.**

A Lumen deve comprovar o resultado.

---

### FASE 11 — UNREAL ENGINE AGENT
**Status: 🟥 PENDENTE**

Prioridade:
1. Unreal Python/API;
2. arquivos;
3. CLI/build;
4. C++;
5. Blueprint;
6. Computer Control quando necessário.

Capacidades:
- projeto;
- assets;
- Blueprint;
- C++;
- actors;
- components;
- levels;
- materials;
- packaging;
- builds;
- testes.

---

### FASE 12 — WORKFLOW LEARNING
**Status: 🟥 PENDENTE**

Registrar:
- objetivo;
- contexto;
- trajetória;
- ações;
- resultados;
- falhas;
- correções;
- estratégia vencedora;
- evidências.

Transformar tarefas repetidas em workflows verificáveis.

Workflow aprendido nunca bypassa:
- Permission;
- Policy;
- Audit;
- Verification.

---

### FASE 13 — AUTONOMOUS MULTI-STEP AGENT
**Status: 🟥 PENDENTE**

Unificar:

```text
Goal
 ↓
Research
 ↓
Understand
 ↓
Plan
 ↓
Execute
 ↓
Observe
 ↓
Verify
 ↓
Correct
 ↓
Test
 ↓
Report
 ↓
Remember
```

A Lumen deve conseguir executar tarefas longas mantendo estado e respeitando limites.

---

# 24. LUMEN EVOLUTION SYSTEM — SISTEMA CENTRAL DE AUTOEVOLUÇÃO

## 24.1 VISÃO

O **Lumen Evolution System (LES)** será um subsistema oficial da Lumen destinado a:

> detectar limitações, pesquisar soluções, formular hipóteses, criar experimentos, implementar candidatos, testar, comparar, verificar, aprender com sucesso e fracasso e promover somente melhorias que satisfaçam critérios de segurança e qualidade.

O LES **não terá autoridade irrestrita sobre o próprio sistema de segurança**.

---

## 24.2 FASE 14 — EVOLUTION FOUNDATION
**Status: 🟥 PENDENTE**

Criar:

```text
Evolution Engine
├── Capability Registry
├── Capability Measurement
├── Self-Diagnostics
├── Improvement Planner
├── Hypothesis Manager
├── Experiment Manager
├── Candidate Registry
├── Benchmark Engine
├── Regression Detector
├── Safety Validator
├── Promotion Manager
├── Rollback Manager
└── Evolution Memory
```

Cada melhoria terá um identificador único:

```text
EVOLUTION-000001
EVOLUTION-000002
...
```

Cada registro deverá possuir:
- problema;
- hipótese;
- baseline;
- fontes;
- alterações;
- testes;
- métricas;
- regressões;
- decisão;
- evidências;
- resultado.

---

## 24.3 FASE 15 — EVOLUTION LABORATORY
**Status: 🟥 PENDENTE**

Criar laboratório isolado para experimentos.

Estrutura conceitual:

```text
EvolutionLab/
├── experiments/
├── candidates/
├── benchmarks/
├── reports/
├── rejected/
└── approved/
```

O laboratório deverá ser separado do runtime estável.

### Regra fundamental

```text
STABLE LUMEN
      │
      ├── checkpoint
      │
      ▼
EXPERIMENTAL WORKSPACE
      │
      ▼
CANDIDATE
      │
      ▼
VALIDATION
      │
      ├── FAIL → DISCARD
      │
      └── PASS → PROMOTION GATE
```

Uma falha experimental nunca pode ser necessária para iniciar a Lumen estável.

---

## 24.4 FASE 16 — SELF-DIAGNOSTICS + RESEARCH FOR IMPROVEMENT
**Status: 🟥 PENDENTE**

A Lumen deverá conseguir receber uma solicitação como:

> "Seu Computer Control e sua visão estão ruins. Melhore."

E transformar isso em:

```text
Complaint
 ↓
Capability Diagnosis
 ↓
Baseline Benchmark
 ↓
Research
 ↓
Source Evaluation
 ↓
Hypotheses
 ↓
Improvement Plan
```

Exemplos de alvos:
- visão;
- grounding;
- Computer Control;
- planner;
- recovery;
- pesquisa;
- memória;
- Unreal Agent;
- ferramentas;
- desempenho;
- confiabilidade.

---

## 24.5 FASE 17 — CANDIDATE BUILD + BENCHMARK + PROMOTION
**Status: 🟥 PENDENTE**

Nenhuma alteração será considerada melhoria apenas porque "parece funcionar".

Pipeline:

```text
Candidate
 ↓
Build
 ↓
Unit Tests
 ↓
Integration Tests
 ↓
Regression Tests
 ↓
Security Tests
 ↓
Capability Tests
 ↓
Benchmark
 ↓
Compare Against Baseline
 ↓
Promotion Gate
```

O benchmark deverá medir, conforme a capacidade:
- precisão;
- sucesso;
- falhas;
- regressões;
- latência;
- custo;
- estabilidade;
- recuperação;
- segurança.

---

## 24.6 FASE 18 — CONTINUOUS EVOLUTION
**Status: 🟥 PENDENTE**

O LES deverá fechar o ciclo:

```text
OBSERVE
 ↓
MEASURE
 ↓
DIAGNOSE
 ↓
RESEARCH
 ↓
HYPOTHESIZE
 ↓
EXPERIMENT
 ↓
IMPLEMENT
 ↓
TEST
 ↓
BENCHMARK
 ↓
VERIFY
 ↓
PROMOTE / REJECT
 ↓
LEARN
 ↓
MEASURE AGAIN
 ↺
```

A evolução deverá ser baseada em evidência, não em autoavaliação subjetiva.

---



---

## 24.7 FASE 19 — INTELLIGENCE STACK EVOLUTION
**Status: 🟥 PENDENTE**

Esta fase inaugura explicitamente a ambição de tornar a Lumen progressivamente menos dependente de um Provider específico.

Objetivo:

> A Lumen deverá aprender a avaliar, selecionar, combinar, adaptar e otimizar sua própria infraestrutura de inteligência, mantendo o Provider como componente substituível e não como identidade da Lumen.

Capacidades:
- Model Registry;
- Provider Registry;
- capability-to-model mapping;
- model routing;
- specialist selection;
- prompt/context optimization;
- inference strategy optimization;
- latency/quality/cost optimization;
- local model benchmarking;
- fallback e degradação controlada;
- comparação entre modelos;
- seleção baseada em evidências;
- gerenciamento de adapters;
- versionamento de modelos e configurações.

Fluxo:

```text
Capability → Measure → Select Model / Strategy → Experiment → Benchmark → Promote → Monitor → Learn → repetir
```

Princípio:

**A Lumen não deve depender de um Provider específico; deve depender dos próprios contratos e da própria arquitetura.**

---

## 24.8 FASE 20 — MODEL ADAPTATION LABORATORY
**Status: 🟥 PENDENTE**

Criar um laboratório específico para investigar se e como a própria camada de inteligência pode ser adaptada.

O laboratório poderá pesquisar, quando tecnicamente viável:
- LoRA/adapters;
- fine-tuning;
- distillation;
- pruning;
- quantization;
- dataset curation;
- synthetic data;
- curriculum generation;
- tool-use training;
- domain adaptation;
- specialist models;
- model compression;
- inference optimization;
- routing entre modelos especializados.

Pipeline:

```text
Observed Limitation → Research → Training / Adaptation Hypothesis → Dataset / Experiment Design → Candidate Model or Adapter → Evaluation → Regression + Security Review → Promotion Gate → Monitor
```

Regra:

A Lumen não poderá assumir que treinar ou adaptar um modelo melhora a inteligência. Toda alteração deverá ser comprovada por benchmarks reproduzíveis.

---

## 24.9 FASE 21 — LUMEN INTELLIGENCE LAB
**Status: 🟥 PENDENTE**

Unificar Evolution Lab + Model Adaptation Lab em um ambiente permanente de pesquisa de inteligência.

Objetivo:

**Permitir que a Lumen investigue continuamente como ficar mais capaz sem precisar alterar diretamente o runtime estável.**

Componentes:
- Model Registry;
- Dataset Registry;
- Experiment Registry;
- Benchmark Registry;
- Adapter Registry;
- Prompt/Context Registry;
- Routing Strategies;
- Training Experiments;
- Inference Experiments;
- Capability Benchmarks;
- Regression Detection;
- Safety Validation;
- Promotion Manager;
- Evolution Memory.

A Lumen poderá comparar modelos, adapters, estratégias de prompt/contexto, routing e estratégias de ferramentas para uma capacidade específica.

---

## 24.10 FASE 22 — SELF-OPTIMIZING INTELLIGENCE
**Status: 🟥 PENDENTE**

Esta é a fase que materializa a ambição de longo prazo do projeto.

A Lumen deverá ser capaz de identificar que uma capacidade está limitada e pesquisar sistematicamente como melhorar o próprio stack de inteligência utilizado para aquela capacidade.

Exemplo:

```text
"Lumen, você está ruim em Unreal C++."
        ↓
Capability Diagnosis
        ↓
Baseline
        ↓
Research
        ↓
Model Evaluation
        ↓
Prompt / Context Experiments
        ↓
Routing Experiments
        ↓
Adapter / Fine-Tuning Experiments
        ↓
Tool Strategy Experiments
        ↓
Benchmark
        ↓
Security / Regression Review
        ↓
Promotion
        ↓
Post-Promotion Monitoring
```

A evolução poderá ocorrer em diferentes níveis:

1. **Uso do modelo:** prompts, contexto, memória, ferramentas e decomposição de tarefas.
2. **Orquestração:** routing, especialistas, ensembles, seleção dinâmica e estratégias de inferência.
3. **Adaptação:** adapters, LoRA, fine-tuning e datasets especializados.
4. **Infraestrutura:** quantização, caching, batching, contexto e eficiência de inferência.
5. **Novos modelos:** pesquisar, avaliar, testar, promover e substituir candidatos anteriores quando houver evidência.

A Lumen deverá continuar funcionando mesmo quando um experimento falhar.

---

## 24.11 FASE 23 — PROVIDER INDEPENDENCE
**Status: 🟥 PENDENTE**

Objetivo final da arquitetura de Providers:

```text
LUMEN
  ↓
Intelligence Contracts
  ↓
Provider Abstraction
  ↓
Local A / Local B / External
  ↓
Evidence-based Routing
```

A Lumen deverá conseguir continuar operando quando:
- um Provider externo estiver indisponível;
- um modelo local estiver indisponível;
- um modelo for substituído;
- uma versão apresentar regressão;
- uma VisionProvider falhar;
- uma estratégia experimental for rejeitada.

A dependência deverá estar na **interface e nos contratos da Lumen**, não na identidade de um fornecedor específico.

---

## 24.12 FASE 24 — CONTINUOUS INTELLIGENCE EVOLUTION
**Status: 🟥 PENDENTE**

Ciclo de longo prazo:

```text
WORLD → RESEARCH → KNOWLEDGE → EXPERIENCE → MEASURE CAPABILITIES
→ IDENTIFY LIMITATIONS → RESEARCH IMPROVEMENTS → EXPERIMENT
→ ADAPT / OPTIMIZE / REPLACE → BENCHMARK → PROMOTE
→ USE → OBSERVE → LEARN → repetir
```

O objetivo não é permitir uma alteração irrestrita e imprevisível do sistema.

O objetivo é criar uma **linha de engenharia evolutiva contínua**, onde cada melhoria precisa produzir evidência, permanecer auditável e atravessar as barreiras de segurança.

---

# 24.13 CONSTITUIÇÃO DE EVOLUÇÃO DA LUMEN

1. **Provider não é a Lumen.**
2. **Modelo não é a inteligência completa da Lumen.**
3. **A Lumen pode trocar o modelo sem perder sua identidade arquitetural.**
4. **A Lumen pode pesquisar como melhorar sua própria inteligência.**
5. **A Lumen pode experimentar adaptações do stack de modelos em ambiente isolado.**
6. **Nenhuma melhoria é aceita sem evidência mensurável.**
7. **Experimentos fracassados são memória de engenharia.**
8. **A Lumen não pode remover unilateralmente suas próprias barreiras de segurança.**
9. **O runtime estável permanece separado do laboratório experimental.**
10. **Quanto mais poderosa a evolução, maior deve ser a exigência de validação.**
11. **A autonomia deve crescer através de competência comprovada, não através da remoção de controles.**
12. **A evolução da inteligência deve ser contínua, incremental, mensurável e reversível.**


# 25. ARQUITETURA DE SEGURANÇA DO LUMEN EVOLUTION SYSTEM

## 25.1 O que a Lumen pode modificar

Por política, o LES poderá evoluir capacidades como:
- algoritmos;
- adapters;
- ferramentas;
- prompts;
- estratégias;
- workflows;
- parsers;
- modelos/Providers configuráveis;
- componentes experimentais;
- código de capacidades não críticas.

## 25.2 O que NÃO pode ser auto-promovido

O LES não poderá remover ou enfraquecer por conta própria:
- PermissionManager;
- Policy Engine;
- Sandbox;
- Audit;
- Checkpoint;
- regras de promoção;
- limites de ação;
- isolamento do Evolution Lab;
- mecanismos de rollback;
- controles de segredo/credenciais;
- barreiras de acesso ao sistema.

Alterações nessas áreas exigem **Human Approval Gate** e revisão explícita.

---

# 26. ESTADOS OFICIAIS DE UMA EVOLUÇÃO

Cada experimento deverá passar por estados rastreáveis:

```text
PROPOSED
 ↓
RESEARCHING
 ↓
HYPOTHESIS
 ↓
PLANNED
 ↓
EXPERIMENTAL
 ↓
BUILDING
 ↓
TESTING
 ↓
BENCHMARKING
 ↓
SECURITY_REVIEW
 ↓
PROMOTION_PENDING
 ├── REJECTED
 └── APPROVED
       ↓
    PROMOTED
       ↓
   MONITORED
```

Falha em qualquer ponto deverá produzir estado terminal apropriado, nunca "sucesso silencioso".

---

# 27. EVOLUTION MEMORY

Cada tentativa de evolução deverá produzir memória de engenharia.

Exemplo:

```text
EVOLUTION-000042

Capability:
Computer Vision

Problem:
Grounding inconsistente

Hypothesis:
Combinar UIA + template + VisionProvider

Research:
[fontes]

Changes:
[diff/artefatos]

Baseline:
71%

Candidate:
89%

Regression:
0

Security:
PASS

Decision:
PROMOTED

Evidence:
[test/benchmark references]
```

A Lumen também deverá registrar experimentos rejeitados.

**Fracasso também é conhecimento.**

---

# 28. HUMAN APPROVAL GATES

Os níveis de risco serão:

### 🟢 BAIXO RISCO
Pode ser automatizado conforme política:
- documentação;
- índices;
- conhecimento;
- workflows;
- testes;
- otimizações isoladas;
- prompts não críticos.

### 🟡 MÉDIO RISCO
Exigir validação adicional:
- novas dependências;
- novos Providers;
- alterações de ferramentas;
- mudanças de runtime;
- mudanças com impacto em múltiplos módulos.

### 🔴 ALTO RISCO
Exigir aprovação humana:
- Computer Control;
- permissões;
- sandbox;
- Policy;
- Checkpoints;
- Audit;
- secrets;
- Security Core;
- alterações capazes de ampliar autoridade da Lumen.

---

# 29. STABLE / EXPERIMENTAL / CANDIDATE

A arquitetura oficial deverá separar:

```text
STABLE
  ↓
imutável durante experimento

EXPERIMENTAL
  ↓
ambiente de pesquisa

CANDIDATE
  ↓
versão candidata validada

STABLE
  ↓
somente após promoção
```

A Lumen não deve precisar destruir sua versão estável para descobrir se uma ideia funciona.

---

# 30. ROLLBACK E RECOVERY DA EVOLUÇÃO

Todo experimento relevante deverá possuir:
- checkpoint;
- identidade de versão;
- referência Git quando aplicável;
- manifesto;
- artefatos;
- testes;
- resultado;
- caminho de rollback.

A promoção deverá ser reversível.

O rollback deve restaurar a versão anterior sem depender do candidato que acabou de falhar.

---

# 31. EXEMPLO OFICIAL — AUTO-MELHORIA DO COMPUTER CONTROL

Solicitação:

> "Lumen, seu Computer Control e Visão não estão bons. Melhore."

Fluxo esperado:

```text
1. Registrar objetivo
2. Medir baseline
3. Diagnosticar falhas
4. Pesquisar soluções
5. Avaliar fontes
6. Criar hipóteses
7. Criar experimento
8. Criar workspace isolado
9. Implementar candidato
10. Executar testes
11. Executar benchmark
12. Comparar com baseline
13. Executar security validation
14. Verificar regressões
15. Rejeitar ou promover
16. Registrar experiência
17. Atualizar métricas
18. Monitorar resultado pós-promoção
```

A Lumen pode tentar várias estratégias, mas cada tentativa permanece rastreável.

---

# 32. PRINCÍPIO DE AUTOPROTEÇÃO DO LES

> **A Lumen pode melhorar suas capacidades; ela não pode redefinir unilateralmente as regras que protegem sua própria evolução.**

A separação fundamental será:

```text
CAPABILITY LAYER
      ↑
Evolution System
      ↑
Experimentation
      ↑
Research
      │
      │
========================
SECURITY BOUNDARY
========================
      │
Policy
Permission
Sandbox
Checkpoint
Audit
Rollback
Promotion Rules
      │
      ▼
Stable Runtime
```

---

# 33. CRITÉRIO GLOBAL DE CONCLUSÃO — EVOLUTION EDITION

O roadmap somente será considerado integralmente concluído quando a Lumen possuir:

- Provider local;
- pesquisa autônoma controlada;
- Knowledge Engine;
- Experience Memory;
- Qdrant ou índice semântico equivalente quando apropriado;
- VisionProvider desacoplado;
- LLaVA ou equivalente integrado como Provider visual;
- Grounding Engine;
- Computer Intelligence;
- Windows Native Control;
- Secure Computer Control;
- Verification;
- Recovery;
- Unreal Agent;
- Workflow Learning;
- Autonomous Multi-step Agent;
- Capability Registry;
- Self-Diagnostics;
- Research-for-Improvement;
- Evolution Lab;
- Experiment Manager;
- Candidate Registry;
- Benchmark Engine;
- Regression Detection;
- Security Validation;
- Promotion Gates;
- Rollback;
- Evolution Memory;
- Skill Evidence;
- métricas de evolução;
- monitoramento pós-promoção;
- Intelligence Stack Evolution;
- Model Adaptation Laboratory;
- Lumen Intelligence Lab;
- Self-Optimizing Intelligence;
- Provider Independence;
- Continuous Intelligence Evolution;
- Human Approval Gates para alto risco;
- testes automatizados;
- testes reais de Windows;
- documentação e continuidade atualizadas.

---

# 34. PRINCÍPIO FINAL DA LUMEN

> **A Lumen deve ser capaz de pesquisar o mundo para aprender, pesquisar o próprio desempenho para encontrar limitações, pesquisar tecnologias para descobrir soluções, experimentar essas soluções em segurança, implementar melhorias em ambientes isolados, provar por testes e métricas o que realmente melhorou, aprender também com seus fracassos e promover somente mudanças que atravessem suas barreiras de segurança.**

> **O objetivo não é uma Lumen que simplesmente se modifica. É uma Lumen que possui um sistema de engenharia capaz de descobrir, provar e incorporar melhorias continuamente sem colocar sua própria continuidade em risco.**

---

# 35. CHECKLIST MASTER DE IMPLEMENTAÇÃO

| Fase | Descrição | Status |
|---|---|---|
| F0 | Baseline, Auditoria e Contratos | 🟥 |
| F1 | Local Provider / Ollama | 🟩 |
| F2 | Research Engine | 🟥 |
| F3 | Knowledge + Experience Memory | 🟥 |
| F4 | Tool / Agent Protocol | 🟥 |
| F5 | Computer Intelligence | 🟥 |
| F6 | Windows Native Intelligence | 🟥 |
| F7 | Vision Provider / LLaVA / Qwen3-VL | 🟥 |
| F8 | Grounding Engine / UI-TARS + Qwen3-VL candidates | 🟥 |
| F9 | Secure Computer Control | 🟥 |
| F10 | Verification + Recovery + Regression | 🟥 |
| F11 | Unreal Engine Agent | 🟥 |
| F12 | Workflow Learning | 🟥 |
| F13 | Autonomous Multi-Step Agent | 🟥 |
| F14 | Evolution Foundation | 🟥 |
| F15 | Evolution Laboratory | 🟥 |
| F16 | Self-Diagnostics + Research for Improvement | 🟥 |
| F17 | Candidate Build + Benchmark + Promotion | 🟥 |
| F18 | Continuous Evolution | 🟥 |
| F19 | Intelligence Stack Evolution | 🟥 |
| F20 | Model Adaptation Laboratory | 🟥 |
| F21 | Lumen Intelligence Lab | 🟥 |
| F22 | Self-Optimizing Intelligence | 🟥 |
| F23 | Provider Independence | 🟥 |
| F24 | Continuous Intelligence Evolution | 🟥 |

**Regra operacional:** ao concluir uma fase, atualizar este checklist, o `LUMEN_STATE.md`, os testes e o handoff antes de iniciar a seguinte.
