# Lumen — F9 Unreal Engine Agent

## Objetivo

F9 adiciona uma camada especializada para planejar trabalho no Unreal Editor sem criar um segundo executor.

O agente transforma objetivos/ações Unreal em intenções do ComputerIntelligence e, posteriormente, em CCActionRequest. A execução física continua exclusivamente no ComputerControlService do F7.

## Arquitetura

UnrealProject → UnrealAgent → UnrealPlan → ActionPlan → CCActionRequest → ComputerControlService

O agente conhece:
- identidade do projeto;
- raiz do projeto;
- versão do Unreal Engine quando conhecida;
- janela autorizada do Unreal Editor;
- operações explícitas;
- pós-condições de verification.

## Operações

- FOCUS_EDITOR
- OPEN_ASSET
- OPEN_LEVEL
- SAVE
- SAVE_ALL
- PLAY
- STOP_PLAY

O primeiro conjunto é deliberadamente limitado. Operações de edição estrutural de Blueprint, criação de Actors, alteração de propriedades e geração de C++ ficam para extensões posteriores com contratos específicos e verification própria.

## Atalhos

Os atalhos são dados de planejamento, não execução direta.

Contratos atuais baseados na documentação oficial da Epic:
- Ctrl+P — Open Asset;
- Ctrl+O — Open Level;
- Ctrl+S — Save;
- Ctrl+Shift+S — Save All;
- Alt+P — Play In Editor.

Bindings podem ser personalizados no Unreal Editor; por isso o resultado deve ser verificado no ambiente real.

## Segurança

O agente Unreal:
- não chama driver;
- não acessa mouse/teclado diretamente;
- não concede COMPUTER_CONTROL;
- não altera CCScope;
- não cria checkpoints;
- não contorna Policy;
- não executa recovery fora do F8;
- produz apenas planos/intents/requests.

A execução segue:

UnrealAgent → ComputerIntelligence → Permission → Policy → Scope → Checkpoint → Driver → Audit → Verification

## Fail-closed

Objetivos livres ambíguos não são transformados em ações arbitrárias.

Exemplo:

"melhore meu jogo" → rejeitado até existir um workflow Unreal estruturado.

Isso evita que uma instrução vaga seja convertida em operações potencialmente destrutivas.

## Verification

Cada operação relevante carrega uma pós-condição quando aplicável:
- abrir asset → alvo esperado;
- abrir level → alvo esperado;
- focus → janela esperada;
- save/play/stop → mudança de estado esperada.

A verificação real permanece no F8.

## Limitação importante

A CI atual roda em Linux. Portanto, F9 foi validada por contratos, planejamento, compilação e testes unitários, mas ainda não constitui um smoke test físico do Unreal Editor em Windows.

A validação física deve usar um projeto Unreal real e passar pelo mesmo ComputerControlService protegido.

## Testes

tests/test_unreal_agent.py cobre:
- identidade do projeto;
- validação;
- operações;
- atalhos;
- pós-condições;
- planejamento seguro;
- rejeição de objetivo ambíguo;
- conversão para ActionPlan;
- conversão para CCActionRequest;
- ausência de execução direta;
- janela autorizada do editor.
