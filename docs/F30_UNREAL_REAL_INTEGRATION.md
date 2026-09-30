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

## Estado real de validação — 2026-09-30

### Ambiente
- 🟢 Unreal Engine real detectado: UE 5.8.
- 🟢 Projeto real: AgeOfAether.
- 🟢 Unreal Editor real identificado como UnrealEditor.exe.
- 🟢 SlateInspectorToolset e ToolsetRegistry habilitados no projeto real.
- 🟢 ModelContextProtocol carregado.
- 🟢 MCP real disponível em 127.0.0.1:8000/mcp.

### Evidências MCP/Slate
- 🟢 initialize real: HTTP 200, sessão MCP estabelecida.
- 🟢 notifications/initialized + tools/list.
- 🟢 list_toolsets: AgentSkillToolset e SlateInspectorToolset.
- 🟢 describe_toolset do SlateInspectorToolset.
- 🟢 Snapshot real do AgeOfAether — Unreal Editor, ref w1.
- 🟢 Observe real até maxDepth=30.
- 🟢 WaitFor semântico real para Gaveta de Conteúdo.
- 🟢 Screenshot real do widget b16.
- 🟢 Snapshot profundo real confirmou refs e controles Slate, incluindo Gaveta de Conteúdo.

### Ponte Slate → Computer Control
- 🟢 Snapshot MCP aninhado em JSON é decodificado corretamente.
- 🟢 Coordenadas virtuais negativas do desktop são normalizadas para coordenadas de observação.
- 🟢 Formato real [pos=x,y size=w,h] é aceito.
- 🟢 SlateGroundingAdapter produz GroundedTarget com GroundingSource.SLATE.
- 🟢 TargetingEngine resolve alvo Slate para ExecutionMechanism.COMPUTER_CONTROL.
- 🟢 plan_slate_click("Gaveta de Conteúdo") produziu ação mouse_click, centro (78,1061), sem executar driver.
- 🟢 A conversão no limite físico transforma o centro de observação (78,1061) no ponto Windows (-1842,1061).

### Segurança do ComputerControlService
- 🟢 Sem checkpoint: execução retorna checkpoint_required.
- 🟢 Após aprovação controlada: execução autorizada e checkpoint consumido.
- 🟢 Região autorizada incompatível: execução bloqueada com point outside authorized region.
- 🟢 Reutilização do checkpoint com alvo alterado: bloqueada com checkpoint_request_mismatch.
- 🟢 Clique físico real no Unreal Editor executado exclusivamente pelo ComputerControlService, com Permission → Policy → Scope → Checkpoint → Driver.
- 🟢 O clique físico retornou SUCCESS=True, ERROR=None, DECISION=allowed, CHECKPOINT_STATUS=CONSUMED.
- 🟢 Verificação pós-ação via MCP/Slate confirmou o estado funcional do Content Browser, expondo Tudo → Conteúdo → Aether → Characters → Mago (ref=b52).
- 🟢 Nenhuma entrada física foi executada fora do fluxo oficial.

### Suíte automatizada
- 🟢 tests/test_cc_service.py: 14 passed nesta continuidade.
- 🟢 Suíte Slate direcionada: 8 passed nesta continuidade.
- 🟢 CI pós-correção de coordenadas: test, validation ubuntu, validation windows e windows — success.
- 🟢 Suíte histórica completa antes da correção: 1475 passed, 49 skipped, 0 failed.
- 🟢 Suíte F30/Slate relacionada: 29 passed no último ciclo direcionado.
- 🟢 Branch integrada anteriormente no commit 7e599d97079a66a770531afb08f9858249070475.
- 🟡 data/audit/ permanece como conteúdo local não rastreado e não foi removido.

### Classificação atual
**F30 — validação real segura: APROVADA, incluindo o primeiro clique físico controlado e sua verificação funcional no Unreal Editor.**

O clique físico foi executado uma única vez no alvo Gaveta de Conteúdo, com coordenadas de observação (78,1061) e conversão no limite físico para (-1842,1061). A verificação pós-ação foi read-only via MCP/Slate.
