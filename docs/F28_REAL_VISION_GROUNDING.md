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
