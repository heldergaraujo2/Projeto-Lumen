# Lumen F0 — Baseline, Auditoria e Critérios de Conclusão

Fase: F0 — Baseline / Auditoria / Contratos  
Estado: PENDENTE até a validação final da suíte e CI  
Base auditada: e2944011d37ccfa363b5adf2fcd654a7746aefd7

## Escopo

A F0 estabelece uma fundação verificável para F1–F24: auditoria do código,
baseline reproduzível, contratos explícitos, threat model, Capability
Registry, critérios de promoção e validação automatizada.

## Auditoria inicial

A base possui Agent Core, Providers, memória de conversa e estruturada,
Planner, Executor, Tasks, Tools, filesystem sandbox, terminal policy,
PermissionManager, checkpoints, auditoria, verification, correction,
execution-state opt-in, evidence reports, snapshots/restore, Computer
Control parcial e UI desktop.

Gaps deliberados: Research Engine formal, Knowledge Engine formal,
Experience Memory especializada, VisionProvider executável, Grounding
Engine, Unreal Agent e Evolution System runtime.

Também não havia Capability Registry formal, threat model consolidado ou
workflow CI declarado.

## Baseline

| Item | Estado |
|---|---|
| Branch oficial | master |
| Commit auditado | e2944011d37ccfa363b5adf2fcd654a7746aefd7 |
| Entradas no repositório | 167 |
| Arquivos de teste | 58 |
| Runner | pytest |
| CI antes da F0 | inexistente |
| Lint configurado | inexistente |
| Type-check configurado | inexistente |
| Coverage configurada | inexistente |

Os 995 passed / 5 skipped / 0 failed registrados no LUMEN_STATE são
históricos e não são apresentados como execução nova desta sessão.

O ambiente desta sessão não conseguiu clonar o GitHub por falha de DNS.
Por isso a execução local não é considerada evidência final. O workflow
f0-validation.yml passa a fornecer a execução reproduzível no GitHub.

## Critérios de evidência

- Documentação não prova comportamento.
- IMPLEMENTED no Capability Registry exige evidência.
- PARTIAL significa implementação real, porém contrato incompleto.
- PLANNED significa que não há implementação suficiente.
- Falha crítica mantém a F0 pendente.
- Falha ambiental é registrada separadamente de falha do produto.

## Critérios F0

1. Auditoria registrada.
2. Baseline registrada.
3. Capability Registry implementado e testado.
4. Contratos arquiteturais formalizados.
5. Threat model formalizado.
6. Critérios de promoção formalizados.
7. Workflow CI reproduzível.
8. Suíte completa executada após as alterações.
9. CI verde.
10. Estado e continuidade atualizados com a evidência final.
11. Commit final verificável.

## Regra de não-confusão

Capability Registry é catálogo. Não concede permissão, não executa Tool,
não escolhe Provider e não altera Policy/Sandbox/Checkpoint.

## Continuidade

F1 poderá introduzir Ollama como Provider local sem tornar o Provider a
identidade da Lumen.
