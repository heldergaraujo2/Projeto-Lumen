# F30 — Unreal Real Integration

## Objetivo
Integrar a Lumen a um projeto Unreal existente, preservando a autoridade do ComputerControlService e sem criar uma segunda Lumen ou um segundo projeto.

## Entregas
- app/unreal/integration.py: descoberta read-only de .uproject, validação JSON, identificação de Content/Source/Config/Plugins/Saved, descoberta do Unreal Editor pela camada Windows Native e workflow bounded.
- Operações mutáveis são marcadas como exigindo aprovação.
- testes dedicados em tests/test_f30_unreal_integration.py.

## Segurança
A integração não cria projeto Unreal, cria outra Lumen, executa processo por conta própria, chama driver diretamente, concede COMPUTER_CONTROL, altera Policy/Scope/Checkpoint ou trata detecção visual como autorização.

A operação real continua passando por:
Goal → Plan → Permission → Policy → Scope → Checkpoint → ComputerControlService → Driver → Audit → Verification.

## Gate de ambiente real
A CI valida contratos e regressões, mas não prova Unreal Editor instalado, projeto real aberto, UI Automation real, Blueprint/C++, build/compile, PIE, logs ou recovery reais.

Para F30 ser declarada verde, é necessária uma sessão Windows interativa com projeto Unreal existente e evidência das operações reais.
