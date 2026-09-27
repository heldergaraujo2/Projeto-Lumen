# F21 — Provider Independence

## Objetivo

Reduzir dependência de um provider específico sem executar ou alterar o runtime.
A F21 trabalha com contratos declarativos de capacidade, compatibilidade, fallback
e planos reversíveis de migração.

## Contratos

- ProviderCapabilityContract
- ProviderCompatibility
- ProviderFallbackPolicy
- ProviderIndependenceAssessment
- ProviderMigrationPlan
- ProviderIndependenceLab

## Fluxo

PROVIDER PROFILES -> CAPABILITY CONTRACT -> COMPATIBILITY ASSESSMENT
-> FALLBACK POLICY -> MIGRATION PLAN -> EXISTING F12-F20 GATES

## Segurança

F21 não invoca providers, modelos ou ferramentas; não baixa modelos; não treina;
não faz inferência; não executa browser/driver; não faz deploy; não concede
permissões; não altera Policy/Sandbox/Checkpoint/Audit; não amplia Scope.

A independência é avaliada somente sobre perfis declarados. Fallback e migração
são contratos e planos, não execução automática.

## Critério de conclusão

A fase está concluída quando contratos, compatibilidade multi-provider, fallback,
migração reversível, integração com F17 StackRequest, testes de segurança e CI
estiverem verdes e a continuidade oficial estiver sincronizada.
