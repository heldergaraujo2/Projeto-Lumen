# Lumen — F11 Autonomous Multi-Step Agent

## Objetivo

A F11 transforma a infraestrutura F0–F10 em uma camada de orquestração multi-etapas limitada. A Lumen pode encadear passos, verificar cada etapa por meio do executor seguro, aplicar recovery bounded e interromper a tarefa diante de falhas de segurança.

## Regra arquitetural

A autonomia é uma camada de decisão/orquestração. Ela não é uma nova autoridade de execução.

O executor recebido pelo agente deve representar a fronteira segura já existente. A F11 não chama driver, não concede Permission, não cria ou aprova checkpoints e não altera Scope/Policy/Sandbox/Audit.

## Contrato

`AutonomyGrant -> MultiStepTask -> AutonomousMultiStepAgent -> StepExecutor -> F7/F8`

O `AutonomyGrant` exige aprovação humana explícita e possui orçamento máximo de passos.

Limites independentes:
- máximo de passos por tarefa;
- máximo de recoveries;
- máximo de tentativas por passo.

## Comportamento

1. Validar grant e tarefa.
2. Recusar autonomia sem aprovação humana.
3. Recusar tarefa acima do orçamento.
4. Executar um passo por vez através do executor autorizado.
5. Só avançar após o passo retornar sucesso/verificação.
6. Em falha, consultar RecoveryEngine.
7. Nunca recuperar permissões ou escopo.
8. Falha de permission/scope é terminal.
9. Exceder orçamento encerra a execução.
10. Um passo que exige Human Approval adicional não pode ser executado no modo autônomo.
11. Workflows F10 podem ser sugeridos; a sugestão não executa.

## Capacidades novas

- tarefas multi-etapas;
- execução sequencial;
- estado por passo;
- estado global da execução;
- retry/recovery bounded;
- orçamento de autonomia;
- aprovação humana explícita;
- integração de descoberta com WorkflowMatcher.

## O que a F11 ainda não faz

- não concede permissões;
- não aprova checkpoints;
- não chama drivers diretamente;
- não inventa passos fora da tarefa recebida;
- não executa workflows F10 automaticamente sem conversão/autorização explícita;
- não possui autonomia ilimitada;
- não substitui o Security Core.

## Validação

Testes focados em `tests/test_autonomous_multi_step.py` cobrem autorização, orçamento, ordem, retry, falhas de segurança, limite de recovery e integração não-executável com workflows.

Smoke test físico Windows/Unreal continua dependente de ambiente Windows real.
