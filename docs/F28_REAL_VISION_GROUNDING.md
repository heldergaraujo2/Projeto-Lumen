# F28 — Real Vision + Grounding

## Objetivo

Transformar screenshot real em observação de visão, candidatos de elementos e
um alvo grounded seguro, sem entregar autoridade de execução ao provider.

## Entregas

- VisionRequest/VisionObservation/VisionElement com validação de limites.
- OllamaVisionProvider usando o endpoint local de geração multimodal.
- VisionProviderManager para desacoplar provider/modelo.
- GroundingEngine structured-first, com threshold de confiança e proteção de
  região/screenshot.
- TargetResolver com prioridade UI Automation -> Accessibility -> Native ->
  DOM -> Template -> OCR -> Vision.
- VisionGroundingPipeline: screenshot -> provider -> observation -> grounding
  -> target candidate.
- F28 não executa ações; ComputerControlService continua sendo a única
  fronteira física.

## Segurança

- bounding boxes devem estar dentro da imagem;
- confidence abaixo do threshold é rejeitada;
- targets fora da região autorizada são rejeitados;
- não é permitido inferir identidade de janela a partir de pixels;
- provider não recebe Permission/Policy/Scope/Checkpoint;
- nenhuma promoção, alteração de código ou execução é realizada pela pipeline.

## Critérios

SPEC / IMPLEMENTATION / INTEGRATION / NEGATIVE / SECURITY / REGRESSION /
REAL PROVIDER VALIDATION / DOCUMENTATION / EVIDENCE.

## Limite de validação

A validação automatizada pode provar contrato e integração, mas não pode
provar que Ollama está instalado com um modelo multimodal na máquina do usuário.
O smoke real de F28 requer um screenshot benigno e um provider multimodal
disponível, mantendo a execução física desligada.


## Compatibilidade com capturas de alta resolução

Capturas físicas podem ter resolução muito superior àquela em que um modelo
multimodal pequeno consegue gerar uma resposta estruturada com estabilidade.
O `OllamaVisionProvider` reduz, de forma não destrutiva, a maior dimensão da
imagem enviada ao modelo para no máximo 1280 pixels, preservando a captura
original como evidência. Após a observação, as caixas retornadas pelo modelo
são remapeadas para as dimensões originais antes da validação e do grounding.
Assim, a otimização de entrada não concede ao provider nenhuma autoridade física
nem altera a fronteira de execução do ComputerControlService.

A validação F28 deve usar um modelo multimodal local realmente disponível na
máquina. O smoke atual aceita `LUMEN_OLLAMA_VISION_MODEL` e usa
`qwen3-vl:2b-instruct` como padrão.
