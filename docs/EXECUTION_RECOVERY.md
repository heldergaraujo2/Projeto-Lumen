# Persistência e retomada segura de execuções

## Ativação

A recuperação é opt-in. Configure `LUMEN_PERSIST_EXECUTION_STATE=true` no ambiente da Lúmen. O padrão permanece desligado. A identidade opaca da conversa é mantida localmente em `data/conversation_id.txt`; não é derivada do texto enviado ao modelo.

## Como retomar

No chat, use:

```text
/retomar PLN-xxxx
```

Substitua o exemplo pelo ID do plano interrompido. O comando é tratado antes do Planner e do runtime universal; não pede a um modelo para decidir qual execução carregar.

## Garantias

- O bundle precisa existir, ser legível, usar a versão suportada e conter o mesmo ID de plano e a mesma identidade de conversa.
- Bundles legados sem identidade de conversa são bloqueados para retomada.
- O executor valida os IDs, dependências, descrições, ordens e ferramentas do snapshot contra o plano.
- Somente tarefas `DONE` com resultado JSON que declare `ok: true` podem ser reutilizadas. Apenas tarefas `PENDING` podem ser executadas novamente.
- `IN_PROGRESS`, falhas, reprovações, tarefas puladas, resultados inválidos ou snapshots inconsistentes bloqueiam a retomada. Isso evita repetir automaticamente uma ação externa cujo efeito ficou ambíguo após queda do processo.
- Checkpoints e aprovações não são restaurados. A tarefa pendente passa novamente pela política de aprovação vigente.
- Parâmetros são persistidos a partir do plano original, não dos valores de data-flow resolvidos. Se a sanitização alterou parâmetros, a retomada é bloqueada.
- Segredos, saídas de terminal e conteúdo integral de arquivos continuam sujeitos à sanitização existente.
- Retomada está desabilitada para o modo autônomo e para ciclos de correção, pois esses fluxos precisam de snapshots próprios antes de serem recuperados com segurança.

## Limitações operacionais

A retomada não garante execução *exactly-once* de ações externas. Se a queda ocorrer durante uma ferramenta, a tarefa fica `IN_PROGRESS` e o sistema bloqueia a repetição automática; o operador deve inspecionar o efeito no sistema-alvo e decidir como prosseguir. A configuração de persistência grava dados locais sanitizados em `execution_dir`; habilite-a somente se isso for apropriado para a máquina e o workspace.

## Testes

Os testes cobrem validação de identidade do bundle, isolamento entre conversas, retomada de tarefas pendentes e bloqueio de estados/retornos ambíguos. A execução deve continuar sem persistência quando a opção está desligada.
