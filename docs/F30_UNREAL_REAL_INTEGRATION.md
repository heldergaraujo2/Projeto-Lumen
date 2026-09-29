# F30 — Unreal Real Integration

## Objetivo
Integrar a Lumen a um projeto Unreal existente, preservando a autoridade do ComputerControlService e sem criar uma segunda Lumen ou um segundo projeto.

## Entregas
- app/unreal/integration.py: descoberta read-only de .uproject, validação JSON, identificação de Content/Source/Config/Plugins/Saved, descoberta do Unreal Editor pela camada Windows Native e workflow bounded.
- Operações mutáveis são marcadas como exigindo aprovação.
- testes dedicados em tests/test_f30_unreal_integration.py.

## Segurança
A integração não cria projeto Unreal, cria outra Lumen, executa processo por conta própria, chama driver diretamente, concede COMPUTER_CONTROL, altera Policy/Scope/Checkpoint ou trata detecção visual como autorização.

A operação real continua passando por:
Goal → Plan → Permission → Policy → Scope → Checkpoint → ComputerControlService → Driver → Audit → Verification.

## Gate de ambiente real
A CI valida contratos e regressões, mas não prova Unreal Editor instalado, projeto real aberto, UI Automation real, Blueprint/C++, build/compile, PIE, logs ou recovery reais.

Para F30 ser declarada verde, é necessária uma sessão Windows interativa com projeto Unreal existente e evidência das operações reais.


## Estado real de validação — 2026-09-29

### Ambiente
- 🟢 Unreal Engine real detectado: UE 5.8.
- 🟢 Projeto real: AgeOfAether.
- 🟢 Unreal Editor real identificado como `UnrealEditor.exe`.
- 🟢 SlateInspectorToolset e ToolsetRegistry habilitados no projeto real.
- 🟢 ModelContextProtocol carregado.
- 🟢 MCP real disponível em `127.0.0.1:8000/mcp`.

### Evidências MCP/Slate
- 🟢 initialize real: HTTP 200, sessão MCP estabelecida.
- 🟢 notifications/initialized + tools/list.
- 🟢 list_toolsets: AgentSkillToolset e SlateInspectorToolset.
- 🟢 describe_toolset do SlateInspectorToolset.
- 🟢 Snapshot real do `AgeOfAether — Unreal Editor`, ref `w1`.
- 🟢 Observe real até `maxDepth=30`.
- 🟢 WaitFor semântico real para `Gaveta de Conteúdo`.
- 🟢 Screenshot real do widget `b16`.
- 🟢 Snapshot profundo real confirmou refs e controles Slate, incluindo `Gaveta de Conteúdo`.

### Ponte Slate → Computer Control
- 🟢 Snapshot MCP aninhado em JSON é decodificado corretamente.
- 🟢 Coordenadas virtuais negativas do desktop são normalizadas para coordenadas de tela.
- 🟢 Formato real `[pos=x,y size=w,h]` é aceito.
- 🟢 `SlateGroundingAdapter` produz `GroundedTarget` com `GroundingSource.SLATE`.
- 🟢 `TargetingEngine` resolve alvo Slate para `ExecutionMechanism.COMPUTER_CONTROL`.
- 🟢 `plan_slate_click("Gaveta de Conteúdo")` produziu ação `mouse_click`, centro `(78,1061)`, sem executar driver.
- 🟢 Driver controlado recebeu exatamente `(78,1061,"left")` após aprovação, usando fake driver; nenhuma entrada física do Windows foi realizada.

### Segurança do ComputerControlService
- 🟢 Sem checkpoint: execução retorna `checkpoint_required`.
- 🟢 Após aprovação controlada: execução autorizada e checkpoint consumido.
- 🟢 Região autorizada incompatível: execução bloqueada com `point outside authorized region`.
- 🟢 Reutilização do checkpoint com alvo alterado: bloqueada com `checkpoint_request_mismatch`.
- 🟢 Em todos os testes controlados, o driver físico não foi acionado.
- 🟡 Clique físico real no Unreal Editor ainda NÃO foi executado; permanece deliberadamente pendente e requer autorização explícita.

### Suíte automatizada
- 🟢 Suíte completa: **1475 passed, 49 skipped, 0 failed**, em 20,61 s.
- 🟢 Suíte F30/Slate relacionada: **29 passed** no último ciclo direcionado.
- 🟢 Branch e PC sincronizados no commit `93df6010174608738230474d3aa5dc2d99e1ebac`.
- 🟡 `data/audit/` permanece como conteúdo local não rastreado e não foi removido.

### Classificação atual
**F30 — validação real segura: APROVADA até o limite sem entrada física.**

Não declarar clique físico real como concluído. O próximo teste de retomada é a decisão explícita sobre executar ou não uma ação física controlada no Unreal Editor. Caso a ação física seja autorizada, ela deve continuar exclusivamente pelo fluxo Permission → Policy → Scope → Checkpoint → ComputerControlService → Driver → Audit/Verification.
