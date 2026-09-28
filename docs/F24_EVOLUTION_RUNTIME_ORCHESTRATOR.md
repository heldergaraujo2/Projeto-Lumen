# F24 — Evolution Runtime Orchestrator

## Objetivo
Coordenar o ciclo de evolução sem executar ações externas.

`detect → investigate → research → hypothesis → experiment request → build evidence → benchmark → security → human approval → promotion → monitoring`

## Limite de autoridade
O F24 somente valida evidências fornecidas por componentes externos e avança estados. Não executa provider, ferramenta, processo, build, driver, browser, deploy ou promoção automática.

## Gates
- experimento exige workspace isolado;
- candidate pertence à evolução;
- build precisa de evidência;
- benchmark precisa de evidência;
- regressão/security bloqueiam promoção;
- aprovação explícita é obrigatória;
- monitoring só ocorre após promoção.

## Critério
F24 só é concluída após suíte completa, testes negativos/security, compilação, CI verde e documentação/evidência atualizadas.
