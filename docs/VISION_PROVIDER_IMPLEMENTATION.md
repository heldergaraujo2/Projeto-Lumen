# Lumen — F5 Vision Provider

## Objetivo

A F5 torna visão uma capacidade independente da Lumen. Um modelo visual é um
Provider substituível; ele não é a arquitetura de Computer Intelligence.

## Contrato

\`VisionProvider\` recebe \`VisionRequest\` e devolve \`VisionObservation\`.

A observação contém:
- provider/model;
- dimensões da imagem;
- texto observado;
- elementos estruturados;
- confiança;
- bounding boxes em pixels.

## Implementação

\`JsonVisionProvider\` valida respostas estruturadas.

\`OllamaVisionProvider\` fornece o primeiro adapter local e usa por padrão
\`qwen3-vl:8b\`, configurável por modelo e endpoint. O mesmo adapter pode ser
usado para outros modelos vision compatíveis com Ollama, sem tornar um modelo
específico parte da identidade da Lumen.

\`VisionProviderManager\` registra e seleciona Providers por
\`name:model\`, mantendo múltiplos modelos independentes.

## Segurança e limites

- prompt vazio é rejeitado;
- tokens inválidos são rejeitados;
- imagens inexistentes ou acima do limite são rejeitadas;
- payloads não estruturados são rejeitados;
- elementos fora da imagem são rejeitados;
- respostas HTTP inválidas são normalizadas;
- respostas acima do limite são rejeitadas;
- imports de Pillow são feitos no caminho de observação;
- visão produz observação, não executa ações;
- grounding e resolução de alvo permanecem responsabilidades posteriores.

## Separação de responsabilidades

\`\`\`text
VisionProvider
      ↓
VisionObservation
      ↓
Computer Intelligence
      ↓
Grounding Engine (F6)
      ↓
Action Resolver
      ↓
Secure Computer Control (F7)
\`\`\`

A F5 não deve chamar mouse/teclado nem transformar diretamente uma previsão
visual em autorização de ação.

## Critério de conclusão

F5 exige contrato independente, adapter local, seleção de múltiplos Providers,
validação fail-closed, testes focados e CI completa verde.
