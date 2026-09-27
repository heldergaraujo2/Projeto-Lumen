# Contratos Arquiteturais da Lumen — F0

Este documento formaliza contratos. Um contrato futuro não significa que o
componente já esteja implementado.

## Regras transversais

1. Depender de contratos estáveis.
2. Provider não é a Lumen.
3. Modelo não recebe autoridade direta sobre o sistema operacional.
4. Tool passa por Permission/Policy e Checkpoint quando exigido.
5. Efeitos externos relevantes são auditáveis.
6. Resultados críticos recebem Verification.
7. Segurança falha fechada.
8. Alto risco recebe validação adicional e Human Approval quando definido.
9. Runtime estável e laboratório experimental são separados.
10. Barreiras de segurança não podem ser enfraquecidas unilateralmente.

## AIProvider

Entrada: mensagem, contexto e system prompt.  
Saída: AIResponse normalizada.  
Erros: taxonomia de Provider.  
Autoridade: nenhuma execução direta de ferramentas.

## Agent

Recebe objetivo, compõe contexto, consulta Provider e coordena Planner e
Tools quando aplicável. Não implementa drivers de sistema operacional.

## Planner

Transforma intenção em plano validado, valida dependências e limites e não
executa ferramentas.

## Tool

Declara nome, descrição e permissão mínima; executa somente pelo mecanismo
autorizado; retorna resultado estruturado quando possível.

## Permission e Policy

PermissionManager determina autorização de classe de ação. Policy refina
por contexto e escopo. Capability Registry nunca substitui autorização.

## Checkpoint

Representa decisão explícita antes de ação classificada como necessitada de
aprovação. Recusa impede a execução correspondente.

## Sandbox

Restringe caminhos, recursos e autoridade. Interface de usuário não é
fronteira de segurança.

## Audit

Registra metadados suficientes para reconstruir decisão e resultado sem
armazenar desnecessariamente segredos ou conteúdo privado.

## Memory

Separar conversa, conhecimento, experiência, decisões, falhas, sucessos e
evidências. Persistência não equivale a aprendizagem.

## Research

Contrato futuro:
ResearchRequest → Search/Collect → Source → Extract → Compare → Synthesize
→ Verify → Provenance → ResearchResult.

Conteúdo externo é não-confiável; prompt injection não recebe autoridade.

## Vision e Grounding

Contrato futuro:
Image/Screen → Observation → Elements/Targets → Confidence → Bounds →
GroundedActionCandidate.

Vision e grounding produzem informação e candidatos; não executam diretamente.

## Computer Control

Intent → Policy → Permission → Scope → Checkpoint → Driver → Audit →
Observation → Verification.

Modelo nunca chama driver diretamente.

## Verification e Recovery

Verification determina se o resultado satisfaz o critério. Recovery atua
dentro de limites e nunca converte falha em sucesso sem evidência.

## Evolution System

Contrato futuro:
Goal → Diagnose → Baseline → Research → Hypothesis → Experiment → Build →
Test → Benchmark → SecurityReview → PromotionGate → Promote/Reject →
Monitor → Learn.

LES não pode remover Permission, Policy, Sandbox, Checkpoint, Audit,
Rollback, Promotion Rules ou secret protection.
