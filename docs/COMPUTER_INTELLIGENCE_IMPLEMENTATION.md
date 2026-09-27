# Lumen — F3 Computer Intelligence

## Escopo

A F3 consolida a camada própria de Computer Intelligence sem duplicar o
subsystema de Computer Control já existente. Ela cria contratos de percepção,
estado, targeting, grounding, intenção/planejamento de ação, resolução do
mecanismo, verificação e recovery.

## Fluxo

Perception → ComputerObservation → State Fingerprint → Targeting →
Grounding Validation → ActionIntent → ActionPlan → ExecutionResolver →
CCActionRequest → fronteira de execução segura → Observation → Verification →
Recovery limitado.

## Segurança

ComputerIntelligence não importa PermissionManager, não executa drivers, não
persiste bytes de screenshots e não possui autoridade para ampliar escopo.
ExecutionResolver apenas produz o contrato CCActionRequest. A execução real
continua sendo responsabilidade das camadas de segurança/controle existentes.

## Percepção e estado

VisionObservationPerception adapta a saída estruturada de VisionProvider para
ComputerObservation. O fingerprint SHA-256 representa somente dados
estruturados e pode ser usado para comparar estados sem guardar imagens.

## Targeting

TargetingEngine usa a ordem oficial de fontes do GroundingEngine existente:
UI Automation, Accessibility, Native, DOM, Template, OCR e Vision. A validação
final respeita dimensões da observação, região autorizada e confiança mínima.

## Ações

ActionPlanner gera intenções e planos. ExecutionResolver converte uma intenção
válida para CCActionRequest. Nenhum desses componentes chama um driver.

## Verificação e recovery

IntelligenceVerifier verifica presença de alvo e mudança de fingerprint.
IntelligenceRecovery usa o motor de recovery existente com orçamento finito e
não pode conceder autoridade.

## Fora do escopo

Integrações Windows nativas mais profundas, novos Vision Providers, OCR,
template matching, controle consolidado, verification/recovery avançados e
Unreal Agent permanecem nas fases posteriores do roadmap oficial.

## Critério

F3 somente é marcada como concluída após testes focados, compileall e suíte CI
completa verdes.
