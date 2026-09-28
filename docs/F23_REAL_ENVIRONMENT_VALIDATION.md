# F23 — REAL ENVIRONMENT VALIDATION & INTEGRATION READINESS

## Objetivo

Formalizar o gate entre a validação automatizada da Lumen e a validação de
ambiente real. F23 não concede novas permissões e não executa ações físicas.

## Entregas

- detector determinístico de capacidades em `app/validation/environment.py`;
- contrato explícito de estado para validação física e Unreal;
- testes dedicados em `tests/test_f23_environment_validation.py`;
- execução em Linux e Windows pela CI;
- regra fail-closed: Windows, display ou sessão interativa **não** implicam que
  mouse, teclado, UI Automation ou Unreal tenham sido validados;
- evidência separada entre `AUTOMATED`, `NOT_EXECUTED` e futura validação
  física real.

## Gates

| Gate | Evidência | CI padrão |
|---|---|---|
| Ambiente Python | detector + testes | PASS |
| Compatibilidade Linux | suíte automatizada | PASS quando CI verde |
| Compatibilidade Windows | suíte automatizada | PASS quando CI verde |
| Mouse físico | execução em máquina Windows real | NOT_EXECUTED pela CI |
| Teclado físico | execução em máquina Windows real | NOT_EXECUTED pela CI |
| UI Automation real | backend nativo em máquina Windows | NOT_EXECUTED pela CI |
| Unreal Engine real | editor/projeto real | NOT_EXECUTED pela CI |

## Regra de conclusão

F23, como **fase de prontidão e contrato de validação**, é concluída quando o
código, testes, CI e documentação desta fase estão verdes. A prontidão não é
uma declaração de que hardware, UI Automation ou Unreal foram fisicamente
testados. Esses são gates operacionais externos e continuam explicitamente
marcados como `NOT_EXECUTED` até que exista um ambiente real apropriado.

É proibido substituir `NOT_EXECUTED` por `PASS` com base apenas no sistema
operacional, em mocks ou em uma sessão gráfica detectada.

## Segurança preservada

F23 não altera PermissionManager, Policy, Sandbox, Checkpoint, Audit ou Scope;
não executa subprocessos, drivers, mouse, teclado, browser ou Unreal; não baixa
modelos e não cria bypass de segurança.
