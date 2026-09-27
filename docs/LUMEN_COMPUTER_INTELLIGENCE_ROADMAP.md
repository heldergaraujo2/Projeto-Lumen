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
Principal referência para visão, grounding e interação visual.

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

**Status:** PENDENTE

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

**Status:** PENDENTE

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

**Status:** PENDENTE

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

**Status:** PENDENTE

---

# 11. FASE 5 — VISION PROVIDER

## Objetivo

Adicionar visão como Provider independente.

A Lumen não deve ficar presa a um único modelo visual.

Interface conceitual:

\`\`\`text
VisionProvider
├── Ollama / Qwen-VL
├── Ollama / Qwen3-VL
├── outros modelos compatíveis
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

**Status:** PENDENTE

---

# 12. FASE 6 — GROUNDING ENGINE

## Objetivo

Transformar percepção em alvo acionável.

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

## Fontes possíveis

- UIA
- accessibility tree
- native APIs
- templates
- vision
- bounding boxes
- OCR
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

**Status:** PENDENTE

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

**Status:** PENDENTE

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
