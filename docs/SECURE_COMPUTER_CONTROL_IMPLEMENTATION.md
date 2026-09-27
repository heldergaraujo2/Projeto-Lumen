# Lumen — F7 Secure Computer Control

## Objetivo

A F7 transforma um \`GroundedTarget\`/ação planejada em execução física somente
depois de atravessar uma cadeia explícita de autoridade.

## Cadeia obrigatória

\`\`\`text
GroundedTarget / ActionRequest
        ↓
PermissionManager(COMPUTER_CONTROL)
        ↓
CC Policy
        ↓
CCScope
        ↓
One-shot CC Checkpoint
        ↓
Authorized execution scope validation
        ↓
ComputerControlDriver
        ↓
metadata-only Audit
\`\`\`

O driver nunca é chamado antes da aprovação do checkpoint.

## Checkpoint de Computer Control

Cada ação possui um checkpoint \`CC-CP-XXXXXX\`.

O checkpoint contém apenas:
- scope_id;
- fingerprint não reversível da requisição;
- tipo de ação;
- timestamps;
- status;
- nota de decisão.

A aprovação é one-shot.

Uma aprovação não pode ser reutilizada para:
- outro ponto;
- outra ação;
- outro target;
- outro scope;
- uma segunda execução.

Após execução, o checkpoint vira \`CONSUMED\`.

## Fingerprint

A requisição é vinculada a:
- scope;
- ação;
- coordenadas;
- geometria e fonte do GroundedTarget;
- presença/tamanho de texto;
- teclas;
- delta;
- região.

Conteúdo textual não é colocado no fingerprint em claro nem na auditoria.

## Scope

O \`CCScope\` continua impondo:
- expiração;
- limite total de ações;
- limite por minuto;
- limite opcional de duração;
- conjunto de ações autorizadas;
- região autorizada.

Região de screenshot e pontos de mouse são revalidados imediatamente antes
da execução. Uma alteração posterior do scope não consegue ampliar a ação:
ela pode apenas tornar a requisição inválida.

## Fail-closed

São bloqueados:
- ausência de COMPUTER_CONTROL;
- ausência de scope;
- scope inválido;
- scope expirado;
- ação não autorizada;
- checkpoint inexistente;
- checkpoint já decidido/consumido;
- checkpoint de outro scope;
- fingerprint incompatível;
- alvo fora da região;
- screenshot fora da região autorizada;
- ações ainda não implementadas pelo driver.

## Auditoria

A auditoria registra somente metadados:
- operação;
- timestamp;
- scope;
- tipo de ação;
- decisão;
- motivo;
- duração;
- artifact reference.

Não registra bytes de screenshot nem texto digitado.

## Compatibilidade

O modo \`require_checkpoint=False\` existe apenas como opt-out explícito para
testes/integrações legadas. O padrão seguro da F7 é \`True\`.

## Limites

F7 executa somente as ações já suportadas pelo driver atual:
- screenshot;
- focus window;
- mouse move/click/double/right click;
- scroll;
- key press/combo/type.

Mouse drag, clipboard e operações de janela ainda não são executados por esta
camada e falham de forma controlada até receberem implementação e validação
próprias.

## Critério de conclusão

F7 é considerada concluída quando:
- execução física passa por permissão + policy + scope + checkpoint;
- aprovação é one-shot e vinculada à requisição;
- escopo é revalidado no momento da execução;
- auditoria permanece metadata-only;
- caminhos de negação e falha são testados;
- suíte completa e validações de CI estão verdes.
