# Lumen — F8 Verification + Recovery + Regression

## Objetivo

F8 fecha o ciclo de execução segura iniciado em F7:

`Observe → Plan → Act → Observe → Verify → Diagnose → Recover → Verify`

A regra central é:

> **Executar uma ação não significa que ela foi concluída.**

## Verification

O contrato em `app/computer_control/verification.py` suporta pós-condições explícitas:

- `target_visible`;
- `target_absent`;
- `window_focused`;
- `state_changed`;
- `state_unchanged`.

Estados:

- `VERIFIED`: evidência suficiente para a pós-condição;
- `FAILED`: evidência contradiz a pós-condição;
- `INCONCLUSIVE`: faltam evidências suficientes.

O fingerprint de estado continua determinístico e não armazena screenshot bruto.

## Recovery

`RecoveryEngine` classifica falhas e produz somente uma decisão:

- alvo → `REFIND_TARGET`;
- janela/foco → `REFOCUS_WINDOW`;
- timeout/transitório → `RETRY`;
- demais falhas recuperáveis → `REOBSERVE`;
- orçamento esgotado → `ABORT`.

Falhas de permission, scope, checkpoint ou negação de segurança são terminais.

Recovery **não** executa driver, concede Permission, cria checkpoint nem amplia CCScope. Uma ação de recuperação que realmente execute algo deverá voltar a atravessar o F7.

## Regression

`RegressionDetector` compara fingerprints e resultados de verification sem alterar o runtime.

- `NO_REGRESSION`;
- `REGRESSION`;
- `INCONCLUSIVE`.

Ausência de evidência nunca é convertida em sucesso.

## Integração

`ComputerIntelligence` agora expõe:

- verificação de alvo presente/ausente;
- verificação de janela;
- verificação de mudança/estabilidade de estado;
- comparação contra baseline;
- classificação e decisões de recovery.

A autoridade de execução continua exclusivamente no `ComputerControlService` do F7.

## Segurança

Fluxo oficial:

`Intent → Policy → PermissionManager → Scope → Checkpoint → Driver → Audit → Verification`

Recovery não contorna nenhuma dessas barreiras.

## Testes

`tests/test_verification_recovery_regression.py` cobre:

- pós-condições explícitas;
- alvo ausente;
- estado inalterado;
- ausência de evidência;
- expectativas inválidas;
- classificação de falhas;
- limites de tentativa;
- falhas de segurança terminais;
- comparação determinística;
- regressão por verification falha;
- estado inconclusivo não promovido a seguro.

A CI Linux não constitui smoke test físico de mouse/teclado no Windows.
