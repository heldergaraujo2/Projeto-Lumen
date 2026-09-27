# Lumen — Computer Control + Vision

## Implementado

VisionProvider -> VisionObservation -> GroundingEngine -> TargetResolver -> CCActionRequest -> ComputerControlService -> Permission/Scope/Policy -> Driver -> Audit/Verification/Recovery.

## Capacidades

- Computer Control desacoplado de Provider.
- Scope com expiração, limite total, limite por minuto, limite de sessão e região autorizada.
- Grounding com confiança mínima e validação de bounding boxes.
- Resolução estruturada-first: UI Automation, accessibility, native, DOM, template, OCR, vision.
- OllamaVisionProvider configurável; modelo padrão do adaptador: qwen3-vl:8b.
- Windows native driver isolado para mouse, teclado, screenshot, foco e enumeração de janelas.
- Windows UI Automation adapter isolado e carregado somente em Windows.
- Privacidade de screenshot: limite de tamanho, região e bloqueio de Provider externo por padrão.
- Verification e Recovery bounded; recovery nunca concede permissão.
- Código externo não foi incorporado: apenas contratos e capacidades foram adaptados.

## Referências técnicas

A arquitetura usa conceitos documentados publicamente para Windows UI Automation e capacidades de GUI agents/vision. A Lumen mantém contratos próprios.

## Próximas integrações

- ligar UIA a GroundedTarget;
- OCR/template providers;
- redaction de screenshots;
- checkpoint dedicado de Computer Control;
- integração do serviço com ToolsController;
- benchmarks reais em Windows;
- Unreal Agent.
