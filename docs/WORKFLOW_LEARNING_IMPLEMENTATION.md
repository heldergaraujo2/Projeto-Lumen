# Lumen — F10 Workflow Learning

## Objetivo

A F10 adiciona memória operacional de workflows: a Lumen pode transformar uma sequência observada e verificada em um workflow reutilizável, registrar evidências de sucesso/falha, recuperar workflows compatíveis e adaptar somente variáveis declaradas.

Workflow aprendido é conhecimento/plano, não autoridade de execução.

## Arquitetura

WorkflowDefinition -> WorkflowRegistry -> WorkflowMatcher -> WorkflowLearner -> proposta/adaptação -> F7 ComputerControlService -> F8 Verification/Recovery/Regression

A F10 não chama driver, não concede permissões, não cria checkpoints e não altera Policy, Sandbox ou Audit.

## Capacidades

- definição versionada e validada;
- passos com ação, parâmetros e pós-condição;
- fingerprint SHA-256 determinístico;
- risco por passo;
- registro local de evidências;
- estatísticas de tentativas, sucesso, falha e inconclusivo;
- bloqueio de reutilização após a última execução falhar;
- recuperação determinística por similaridade lexical;
- aprendizado somente a partir de passos fornecidos/observados;
- adaptação somente para variáveis declaradas;
- adaptação não pode inserir ou remover passos;
- workflows de alto risco são marcados para Human Approval;
- nenhuma evidência armazena screenshot bytes ou conteúdo digitado.

## Segurança

1. Um workflow aprendido nunca executa o sistema operacional.
2. A F10 não possui acesso ao driver.
3. Toda execução futura continua dependente do F7: Permission -> Policy -> Scope -> Checkpoint -> Driver -> Audit.
4. O resultado deve voltar pela F8 para Verification, Recovery e Regression.
5. Falha de execução deixa o workflow não reutilizável até nova evidência de sucesso.
6. Alterações estruturais são versionadas; versões não podem retroceder.
7. Adaptação aceita apenas bindings declarados pelo workflow.
8. High-risk exige Human Approval adicional; o checkpoint F7 continua obrigatório.
9. A evidência é metadata-only: fingerprint, status e motivo, sem conteúdo sensível.

## Limitações

- O matcher atual é determinístico e lexical; embeddings e semântica ficam para fases futuras.
- O registry atual é em memória; persistência durável e integração ampla com Experience Memory permanecem futuras.
- Não há execução automática de workflow.
- Não houve smoke test físico Windows/Unreal no CI Linux.

## Critério de conclusão F10

Implementação + testes focados + suíte CI + documentação + continuidade atualizada. A fase não depende de automação física para ser considerada concluída, mas o smoke test Windows/Unreal permanece explicitamente pendente.
