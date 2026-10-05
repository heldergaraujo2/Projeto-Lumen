# Lúmen — Cérebro Modular Autoexpansível

A Lúmen passa a ter uma composição explícita entre seu cérebro nativo e
ecossistemas especializados. Nenhum framework externo ganha autoridade de
execução.

## Componentes

- Lúmen: identidade, permissões, checkpoints, memória, world model, gaps,
  pesquisa, evolução, testes, rollback e Unreal/MCP.
- OpenAI Agents SDK: agentes, tools, handoffs, guardrails, sessões, MCP e voz.
- OpenHands: engenharia de software, workspace, execução e skills.
- Browser Use: navegação e automação web.
- AutoGen: composição multiagente e especialistas.
- LangGraph: estado durável, persistência, recuperação e human-in-the-loop.
- MAP: inspiração para planner, monitor, predictor e evaluator.
- Connectomes: inspiração para percepção -> estado interno -> ação -> feedback.

## Autoridade

Segurança -> Permissão -> Scope/Workspace -> Checkpoint -> ToolRegistry ->
OperationalBrain -> especialista -> execução -> verificação.

Frameworks externos fornecem contexto/capacidade/sugestões. A
MissionEnvironment é o caminho de execução real.

## Estrutura

LÚMEN
├── CognitiveFusion
│   ├── ExperienceMemory
│   ├── WorldModel
│   ├── CapabilityGraph
│   ├── ResearchFindings
│   ├── Hypotheses
│   ├── ToolCandidates
│   ├── TemporalLearning
│   └── EvolutionGovernor
├── OperationalBrain
│   ├── estado persistente
│   ├── decisões
│   ├── recuperação
│   └── gates de promoção
├── ModularCognitiveBrain
│   ├── OpenAI Agents
│   ├── OpenHands
│   ├── Browser Use
│   ├── AutoGen
│   └── LangGraph
├── Percepção
│   ├── Windows
│   ├── Web
│   └── Unreal / MCP
└── Evolução
    ├── pesquisa
    ├── lacunas
    ├── ferramentas/código
    ├── testes
    ├── benchmark
    ├── rollback
    └── reavaliação

## Loop

objetivo -> observar -> memória/world model -> lacunas -> pesquisa ->
especialistas -> planejamento -> execução governada -> observação ->
verificação -> aprendizagem -> correção/evolução -> repetição.

## Autoexpansão

Uma capacidade ausente vira CapabilityGap. O cérebro pesquisa soluções,
seleciona especialistas, propõe uma ferramenta ou alteração isolada, cria
testes, valida evidências e somente então promove.

A instalação de um framework não conta como capacidade. Capacidade só é
promovida depois de execução e verificação reais.

## Dependências

Os cinco ecossistemas são adapters opcionais. O núcleo continua funcional
sem nenhum deles e cada backend pode ser ativado progressivamente.
