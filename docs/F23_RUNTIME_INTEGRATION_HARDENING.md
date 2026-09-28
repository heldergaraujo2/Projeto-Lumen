# F23 — Runtime Integration & State Machine Hardening

## Objetivo

Consolidar F19–F22 em contratos determinísticos e verificáveis antes de adicionar um orquestrador de evolução runtime.

## Correções

### F20
- Semântica de `maximize` corrigida para target/delta/threshold.
- `weight` é preservado na avaliação através de `weighted_score`.
- Seleção permanece determinística e sem autoridade de execução.

### F21
- Requisitos declarados possuem resultados explícitos.
- FAILOVER exige dois provedores compatíveis quando solicitado.
- LOCAL_AVAILABILITY só é aplicado quando solicitado.
- Fallback continua declarativo; failover runtime fica para F25.

### F22
- Observation identity é imutável.
- Conteúdo divergente para o mesmo ID é rejeitado.
- Arquivo de observações mantém referências históricas após eviction do histórico ativo.
- Ciclos possuem transições restritas e fechamento explícito.
- Trigger/plan permanecem one-shot.

### F19
Nenhum defeito estrutural adicional exigiu alteração de implementação nesta auditoria.

## Artefato de ambiente

`app/validation/environment.py` é mantido como detector fail-closed. Ele não executa nem declara validação física de mouse, teclado, UI Automation ou Unreal.

## Segurança

F23 não concede novas permissões e não pode bypassar PermissionManager, Policy, Sandbox, Checkpoint, Audit, Scope, Rollback ou Human Approval.

## Conclusão

A fase só será marcada como concluída após:
- testes F19–F23;
- regressão completa;
- negative/security tests;
- CI verde;
- evidência registrada no roadmap canônico;
- nenhuma inferência de validação física a partir de CI.
