# F25 — Provider Runtime Independence

## Objetivo

Transformar a independência de providers de um contrato declarativo (F21) em
execução runtime real, reaproveitando os providers concretos já existentes,
incluindo o Ollama local.

## Entregas

- runtime único ProviderRuntime;
- execução através do contrato AIProvider;
- seleção determinística por preferência, custo, confiabilidade e contexto;
- compatibilidade por capability, reliability, custo e context window;
- fallback real entre providers compatíveis;
- retry bounded somente para erros classificados como retryable;
- falha de autenticação não faz retry do mesmo provider;
- provider incompatível/desabilitado nunca é chamado;
- autorização explícita antes da execução;
- hook de autorização por provider;
- evidência de todas as tentativas;
- resposta normalizada em AIResponse;
- erro fail-closed quando nenhum provider é compatível.

## Local Provider

O OllamaProvider existente em app/ai/ollama_provider.py permanece a
implementação oficial do provider local. F25 não o duplica nem o substitui.
O runtime apenas o recebe via RuntimeProviderSpec e pode selecioná-lo ou
usá-lo como fallback.

## Segurança

O runtime não concede permissões, altera Policy/Sandbox/Checkpoint/Audit,
executa ferramentas, drivers, browser ou processos. execute_chat exige
authorized=True e pode aplicar um hook adicional por provider.

## Limites

CI Linux valida o contrato e o runtime determinístico. Uma chamada real ao
daemon Ollama/Windows só pode ser declarada como validação física quando
executada nesse ambiente.


## Validação final

- commit master: 3fecc50a2df1f5a5e89de64360c9a5306fd46c1f;
- compileall: SUCCESS;
- Lumen Tests: **1366 passed / 1 skipped / 0 failed**;
- Lumen F0 Validation: SUCCESS;
- Lumen F23 Validation: SUCCESS;
- testes F25 dedicados cobrem autorização, Ollama/local, fallback, retry, custo, contexto, verificação, auditoria, providers incompatíveis/desabilitados e fail-closed;
- CI não executa o daemon Ollama real: valida o contrato/runtime de forma determinística.

