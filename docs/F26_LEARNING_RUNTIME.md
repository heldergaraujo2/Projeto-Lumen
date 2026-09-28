# F26 — Learning Runtime & Continuous Knowledge

## Objetivo
A Lumen deve ficar progressivamente mais capaz quando o usuário a utiliza ou ordena que ela aprenda. O conhecimento é persistente e pertence à Lumen, não ao provider.

## Fluxos
- Explícito: objetivo → pesquisa → conhecimento candidato → prática → verificação → consolidação → memória → reutilização.
- Uso: situação → resultado → sucesso/falha → lição → estratégia → experiência persistente.
- Consulta: tarefa futura → recall de conhecimento verificado → adaptação.

Exemplo: “Lúmen, aprenda C++” cria um LearningGoal; a fonte de pesquisa autorizada pode alimentar claims, e prática/verificação podem consolidá-los.

## Segurança
O runtime não executa código, processos, browser, rede, drivers ou ferramentas e não concede permissões. Pesquisa, prática e verificação são callbacks explícitos do runtime superior. Segredos são redigidos antes da persistência. Conhecimento candidato não aparece no recall padrão. Armazenamento JSON é atômico e bounded.

## Critérios
SPEC + IMPLEMENTATION + INTEGRATION + NEGATIVE/SECURITY + REGRESSION estão cobertos pela documentação e testes dedicados. Validação de ambiente físico não se aplica ao núcleo de memória; integrações reais permanecem gates separados.
