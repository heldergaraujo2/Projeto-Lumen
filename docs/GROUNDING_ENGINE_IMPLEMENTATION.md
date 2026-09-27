# Lumen — F6 Grounding Engine

## Objetivo

A F6 transforma percepção estruturada em alvos acionáveis e validados, sem executar ações e sem conceder autoridade ao modelo.

Fontes suportadas: UI Automation, Accessibility, Native, DOM, Template, OCR e Vision.

Ordem padrão estruturada-first:

UI Automation → Accessibility → Native → DOM → Template → OCR → Vision

## Elegibilidade antes da prioridade

Um candidato não pode vencer apenas por pertencer a uma fonte prioritária. Antes da resolução, cada candidato passa por validade estrutural, confiança mínima, limites da imagem, região autorizada e identidade de janela quando disponível.

Somente candidatos elegíveis participam da priorização. Assim, um candidato UIA/native inválido não bloqueia um candidato visual válido.

## Normalização

Labels usam Unicode NFKC, casefold e normalização de espaços. A comparação continua determinística e exata após a normalização; não existe fuzzy matching silencioso.

## Adapters

GroundingEngine.from_vision() adapta VisionObservation.
GroundingEngine.from_native() adapta objetos NativeElement através do contrato grounded(), sem importar a implementação Windows.

## Deduplicação

Candidatos geometricamente idênticos dentro da mesma fonte e label são deduplicados, preservando o candidato com maior confiança.

## Janela ativa

Quando um candidato possui identidade de janela, ela é comparada à janela esperada. Candidatos visuais screenshot-bound sem identidade própria continuam válidos porque pertencem à observação ativa.

## Segurança

O resultado do grounding é somente um GroundedTarget. Não há clique, teclado, driver ou concessão de autoridade.

Execução permanece nas fases posteriores:

Grounding → Action Resolver → Policy → Permission → Checkpoint → Computer Control → Audit → Verification

## Testes

A F6 cobre prioridade, normalização, fallback, confiança mínima, identidade de janela, adaptação de NativeElement, deduplicação, VisionObservation, limites de escopo e validação da ordem de fontes.

## Limites deliberados

A F6 define contratos e resolução de grounding. OCR/template físicos, execução de Computer Control e verification pós-ação pertencem às fases oficiais posteriores.

UI-TARS e Qwen3-VL são referências/candidatos de capacidade; a Lumen não copia suas implementações nem cria dependência arquitetural deles.