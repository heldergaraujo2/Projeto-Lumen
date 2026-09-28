# Lumen — F31 Experience & Workflow Intelligence

## Objetivo

A F31 transforma resultados de uso em inteligência operacional persistente:

`observe → understand → record → generalize → store → reuse → adapt → verify`.

A fase integra a aprendizagem F26 e os workflows F10 sem criar uma segunda Lumen e sem conceder autoridade de execução ao conhecimento aprendido.

## Entregas

- `app/experience/intelligence.py`:
  - ExperienceEvent;
  - ExperienceTrace;
  - ExperienceStore persistente, bounded e atomicamente gravado;
  - PersistentWorkflowRegistry;
  - WorkflowIntelligence;
  - generalização somente de experiências bem-sucedidas e verificadas;
  - abstração determinística de parâmetros divergentes em variáveis;
  - reuse através do WorkflowMatcher existente;
  - adaptação limitada às variáveis declaradas;
  - verificação integrada ao WorkflowEvidence.
- `app/experience/__init__.py`: API pública.
- `tests/test_experience_workflow_intelligence.py`: testes de ciclo, persistência, generalização, segurança, limites e regressão.

## Segurança

- nenhum driver, browser, processo ou ferramenta é chamado;
- nenhuma Permission é concedida;
- Policy, Scope, Sandbox, Checkpoint e Audit não são alterados;
- experiência bem-sucedida precisa de evidência verificada;
- workflow novo não é reutilizável antes de evidência de sucesso;
- bindings extras ou ausentes são rejeitados;
- segredos são redigidos antes da persistência;
- armazenamento é bounded;
- workflow de alto risco continua sujeito ao Human Approval já existente;
- a evidência continua metadata-only, sem screenshots ou conteúdo sensível.

## Critérios

1. SPEC: este documento;
2. IMPLEMENTATION: módulos F31 entregues;
3. INTEGRATION: reutiliza F10/F26;
4. NEGATIVE/SECURITY: testes de rejeição e redaction;
5. REGRESSION: suíte existente;
6. DOCUMENTATION: estado e roadmap atualizados;
7. EVIDENCE: CI do PR/merge.

Validação física Windows/Unreal não é requisito do núcleo F31; continua como gate externo de F27–F30.
