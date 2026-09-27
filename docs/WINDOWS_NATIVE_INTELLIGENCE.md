# Lumen — F4 Windows Native Intelligence

## Objetivo

A F4 adiciona compreensão estruturada do Windows antes da visão: janelas,
processo, UI Automation, propriedades de controles, árvore limitada e
contratos de ações nativas.

## Fluxo

Windows/Win32 -> WindowsUIABackend -> NativeWindow/NativeElement ->
GroundedTarget -> TargetingEngine -> NativeActionRequest -> execução segura F7.

## Entregas

- enumeração de janelas;
- correspondência por handle, título, processo e aplicação;
- descoberta de elementos via UI Automation;
- nome, tipo, bounds, AutomationId, classe e enabled;
- traversal limitado por profundidade e quantidade;
- conversão para GroundedTarget;
- contrato de ação nativa sem execução física.

## Segurança

F4 é inteligência, não autoridade. Ela não concede permissões e não chama
mouse_event, keybd_event, Invoke ou qualquer ação Windows diretamente.
NativeActionRequest é apenas intenção estruturada.

A execução física continua atrás da cadeia consolidada na F7, evitando um
segundo caminho que contorne Policy, PermissionManager, Checkpoint e Audit.

## Compatibilidade

COM/UIA é importado somente no Windows. A suíte Linux pode testar os contratos
com FakeWindowsNativeBackend sem fingir que isso é um teste físico do Windows.

## Limites

OCR/VLM/grounding visual permanecem F5/F6. Execução segura permanece F7.
Verification/recovery ampliados permanecem F8. Unreal Agent permanece F9.
Multi-monitor/DPI avançados continuam trabalho futuro.

## Critério

F4 somente pode ser marcada como concluída após testes focados, compileall,
suíte completa e CI verde. O teste real em Windows é complementar e não é
falsificado pela CI Linux.
