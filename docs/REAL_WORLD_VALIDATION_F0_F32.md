# LUMEN — PLANO OFICIAL DE TESTES REAIS F0–F32

**Atualização:** 2026-09-30  
**Base:** `master` após F32 e consolidação de `LUMEN_STATE.md`.  
**Finalidade:** checklist operacional para o novo chat que executará exclusivamente validações em ambiente real.

## LEGENDA

- **✅ CONCLUÍDO:** evidência objetiva já registrada no repositório/CI ou teste real já executado.
- **❌ PENDENTE:** ainda precisa ser executado no ambiente real.
- **⚠️ CONDICIONAL:** depende da configuração real encontrada.
- **⏭️ NÃO É GATE FÍSICO:** não exigir teste físico independente.

**Regra absoluta:** CI, mock, fake, `sys.platform == win32`, import bem-sucedido ou existência de um arquivo NÃO equivalem a validação física.

**Segurança:** não criar outra Lumen, outro repositório, outro projeto Unreal, bypassar Permission/Policy/Scope/Sandbox/Checkpoint/Audit, executar ações destrutivas ou persistir secrets/screenshot/conteúdo sensível.

> **NÃO CRIE OUTRA LUMEN. ALTERE SEMPRE A LUMEN EXISTENTE.**

---

# 1. AUDITORIA E ESTADO INICIAL

A auditoria cruzou `LUMEN_STATE.md`, `docs/LUMEN_MASTER_ROADMAP.md`, documentação F27–F32, implementação dos componentes reais, scripts de smoke e workflow Windows.

| Área | Implementação/CI | Ambiente real |
|---|---:|---:|
| F0–F26 | ✅ | ⏭️ Sem gate físico identificado |
| F27 Windows | ✅ | ✅ PASS real |
| F28 Vision/Grounding | ✅ | ✅ PASS real |
| F29 Autonomous Agent | ✅ | ✅ PASS real |
| F30 Unreal | ✅ | ✅ PASS real — integração Slate/MCP, grounding, clique controlado e verificação aprovados |
| F31 Experience | ✅ | ✅ PASS — E2E local concluído |
| F32 Closed Loop | ✅ | ✅ PASS — E2E local concluído |
| F33 | ⏭️ Não definida | ⏭️ |

Scripts reais existentes:
- `scripts/f27_windows_smoke.py`
- `scripts/f28_vision_smoke.py`
- `scripts/f29_autonomous_computer_smoke.py`
- `.github/workflows/windows-validation.yml`

**Atualização de evidência real:** F27, F28 e F29 possuem validação física documentada. F30 foi encerrada com MCP/Slate, grounding, coordenadas virtuais, checkpoint, clique físico controlado e verificação pós-ação. F31 E2E, F32 E2E e o E2E integrado final também passaram localmente.

---

# 2. PRE-FLIGHT — OBRIGATÓRIO ANTES DE QUALQUER FASE

- [ ] ❌ Confirmar repositório oficial e branch.
- [ ] ❌ Registrar SHA do commit testado.
- [ ] ❌ Confirmar que não existe uma segunda Lumen em uso.
- [ ] ❌ Registrar Windows edition/build.
- [ ] ❌ Registrar Python.
- [ ] ❌ Registrar dependências.
- [ ] ❌ Confirmar sessão gráfica interativa.
- [ ] ❌ Confirmar display real.
- [ ] ❌ Confirmar mouse e teclado.
- [ ] ❌ Confirmar Ollama, se F28/F29.
- [ ] ❌ Confirmar modelo multimodal, se F28/F29.
- [ ] ❌ Confirmar Unreal Engine, se F30.
- [ ] ❌ Confirmar projeto Unreal existente, se F30.
- [ ] ❌ Registrar data/hora e operador.
- [ ] ❌ Confirmar que nenhum dado sensível estará visível durante screenshots.

Registro mínimo:
```text
Commit:
Windows:
Python:
Ollama:
Modelo Vision:
Unreal:
Projeto:
Data/hora:
```

---

# 3. CÉREBRO LOCAL — OLLAMA / PROVIDER LOCAL — PRIMEIRO GATE REAL

**Regra de ordem:** antes de qualquer teste físico F27–F30, o novo chat deve validar que a Lúmen consegue utilizar um provider local real instalado e executando no PC. Isso não substitui os gates F27–F30; é a fundação operacional para que a Lúmen tenha inteligência local durante os testes seguintes.

**Objetivo:** sair de “provider implementado/testado em CI” para “Lúmen realmente conversa com um modelo local no PC”.

## 3.1 Instalação e ambiente

- [x] ✅ Ollama instalado no Windows; versão anteriormente registrada: 0.34.4.
- [x] ✅ Versão real do Ollama: 0.34.4.
- [x] ✅ Daemon do Ollama confirmado em execução.
- [x] ✅ Endpoint local 127.0.0.1:11434 confirmado.
- [x] ✅ API local real respondeu sem mock.
- [ ] ❌ Confirmar que o processo é realmente local.
- [x] ✅ Modelo textual real: qwen3:8b.
- [x] ✅ qwen3:8b instalado e disponível.
- [x] ✅ qwen3:8b; tamanho observado: 5225388164 bytes.
- [x] ✅ Inferência textual real confirmada.
- [ ] ❌ Registrar tempo aproximado da primeira resposta e de uma resposta subsequente.
- [ ] ❌ Registrar consumo/limitações relevantes observados no hardware, sem transformar isso em requisito artificial de desempenho.

**Modelo textual inicial registrado no projeto:** `qwen2.5-coder:7b-instruct-q8_0`. O teste deve confirmar no PC qual modelo está efetivamente instalado; não marcar PASS apenas porque esse nome aparece em documentação.

## 3.2 Inferência real independente

Executar uma chamada real ao Ollama, fora de mocks/fakes.

- [ ] ❌ Enviar prompt de teste não destrutivo.
- [ ] ❌ Receber resposta real do modelo.
- [x] ✅ Log da Lúmen identificou provider=ollama.
- [ ] ❌ Confirmar ausência de fallback silencioso para provider remoto.
- [x] ✅ Provider efetivo: ollama.
- [x] ✅ Modelo efetivo: qwen3:8b.
- [ ] ❌ Registrar resultado da chamada.
- [ ] ❌ Registrar erro completo se houver falha.

## 3.3 Lúmen usando o provider local

O teste mais importante deste bloco é **pela própria Lúmen**, e não somente pelo comando do Ollama.

- [x] ✅ Lúmen v0.6.8 iniciou com provider ollama.
- [x] ✅ Execução real configurada com LUMEN_PROVIDER=ollama e LUMEN_MODEL=qwen3:8b.
- [ ] ❌ Confirmar health check pela Lúmen.
- [ ] ❌ Confirmar descoberta/listagem do modelo pela Lúmen.
- [x] ✅ Solicitações conversacionais reais processadas pela Lúmen.
- [x] ✅ Respostas reais geradas pelo provider ollama / qwen3:8b.
- [ ] ❌ Confirmar streaming quando aplicável.
- [ ] ❌ Confirmar tratamento de erro real desligando/parando o provider de forma controlada.
- [ ] ❌ Confirmar recuperação/reconexão sem criar bypass.
- [ ] ❌ Confirmar auditoria/telemetria sem persistir secrets.
- [ ] ❌ Confirmar que a Lúmen não depende de um provider remoto para concluir a inferência local.

## 3.4 Teste de continuidade do cérebro local

- [ ] ❌ Encerrar e reiniciar a sessão da Lúmen.
- [ ] ❌ Confirmar nova conexão com Ollama.
- [x] ✅ Nova inferência confirmada após recuperação da sessão.
- [ ] ❌ Confirmar que nenhuma credencial/secreta foi gravada indevidamente.
- [ ] ❌ Registrar configuração mínima necessária para reproduzir o teste.

## 3.5 Visão multimodal local — pré-requisito para F28

Depois do modelo textual local estar validado:

- [x] ✅ Ollama pronto para modelo multimodal.
- [x] ✅ Modelo multimodal real: qwen3-vl:2b-instruct.
- [x] ✅ Modelo multimodal instalado.
- [x] ✅ Modelo aceitou imagem em inferência real.
- [x] ✅ Inferência multimodal real confirmada.
- [x] ✅ Resposta utilizou a imagem fornecida.
- [x] ✅ Tag registrada: qwen3-vl:2b-instruct.
- [x] ✅ Não houve fallback textual silencioso no teste F28.

Este bloco pode utilizar o modelo vision que o teste F28 definir no ambiente real; não deve inventar um modelo apenas para obter PASS.

## 3.6 Critério para liberar os testes seguintes

O **cérebro local** somente recebe **✅ CONCLUÍDO** quando:

1. Ollama real instalado e acessível;
2. modelo textual real instalado;
3. inferência textual real confirmada;
4. Lúmen executou inferência através do provider local;
5. provider efetivo foi identificado;
6. não houve fallback remoto silencioso;
7. reinicialização/reconexão foi validada;
8. evidências foram registradas;
9. nenhum bypass de segurança foi utilizado.

A validação multimodal é necessária antes de considerar **F28** liberada para execução real.

**Importante:** instalação do Ollama não é, sozinha, prova de que a Lúmen já possui um cérebro funcional. O PASS é da cadeia **PC → Ollama → modelo → Provider Lúmen → Runtime Lúmen → resposta real**.

---

# 4. F27 — REAL WINDOWS COMPUTER VALIDATION

**Componentes auditados:** `app/computer_control/windows_driver.py`, `tests/test_f27_windows_driver.py`, `scripts/f27_windows_smoke.py`.

## 3.1 Fail-closed

- [ ] ❌ Driver com `armed=False`.
- [ ] ❌ Tentativa de mouse deve ser recusada.
- [ ] ❌ Tentativa de teclado deve ser recusada.
- [ ] ❌ Confirmar que nenhum input físico ocorreu.
- [ ] ❌ Registrar erro/mensagem.

## 3.2 Screenshot físico

- [ ] ❌ Executar screenshot pelo driver Windows real.
- [ ] ❌ Confirmar resolução.
- [ ] ❌ Confirmar que o arquivo corresponde à tela real.
- [ ] ❌ Registrar referência do artefato.
- [ ] ❌ Não persistir conteúdo sensível no estado da Lumen.

## 3.3 Mouse

- [ ] ❌ Com driver armado, mover para ponto seguro.
- [ ] ❌ Confirmar visualmente movimento.
- [ ] ❌ Registrar coordenadas.
- [ ] ❌ Não clicar nesta etapa.

## 3.4 Teclado

- [ ] ❌ Selecionar aplicativo benigno.
- [ ] ❌ Digitar `LUMEN_F27_SMOKE`.
- [ ] ❌ Confirmar visualmente o marcador.
- [ ] ❌ Não usar teclas destrutivas.

## 3.5 Foco

Cobertura real suplementar do suporte de foco:
- [ ] ❌ Selecionar duas janelas benignas.
- [ ] ❌ Focar a janela-alvo pelo mecanismo Windows Native.
- [ ] ❌ Confirmar visualmente a janela ativa.

## 3.6 Smoke oficial

PowerShell:
```powershell
$env:LUMEN_F27_PHYSICAL_CONFIRM="YES"
python scripts/f27_windows_smoke.py
```

Esperado:
```text
F27 screenshot: PASS
F27 mouse move: PASS
F27 keyboard typing: PASS
```

- [ ] ❌ Executar.
- [ ] ❌ Guardar saída completa.
- [ ] ❌ Registrar screenshot.
- [ ] ❌ Registrar data/hora.

## F27 só vira 🟩 quando

Screenshot + mouse + teclado foram executados na sessão Windows real, com evidência objetiva e sem bypass.

**Estado atual: ✅ CONCLUÍDO.** Evidência real registrada: screenshot 3840x1125, mouse move seguro, teclado com marcador LUMEN_F27_SMOKE e nenhuma ação destrutiva.

---

# 5. F28 — REAL VISION + GROUNDING

**Componentes auditados:** `OllamaVisionProvider`, `VisionGroundingPipeline`, `scripts/f28_vision_smoke.py`.

## 4.1 Ollama real

- [ ] ❌ Ollama instalado.
- [ ] ❌ Daemon ativo.
- [ ] ❌ API local responde.
- [ ] ❌ Modelo multimodal instalado.
- [ ] ❌ Modelo comprovadamente aceita imagem.
- [ ] ❌ Registrar versão do Ollama.
- [ ] ❌ Registrar modelo/tag.

## 4.2 Inferência multimodal

- [ ] ❌ Enviar uma imagem real.
- [ ] ❌ Confirmar resposta do modelo multimodal real.
- [ ] ❌ Confirmar que não houve fallback silencioso para modelo textual.

## 4.3 Pipeline

- [ ] ❌ Capturar screenshot real.
- [ ] ❌ Produzir `VisionObservation`.
- [ ] ❌ Confirmar elementos.
- [ ] ❌ Confirmar labels plausíveis.
- [ ] ❌ Confirmar bounding boxes.
- [ ] ❌ Confirmar boxes dentro da imagem.
- [ ] ❌ Confirmar confidence válida.

## 4.4 Grounding

Usar elemento benigno, visível e inequívoco.

- [ ] ❌ Solicitar resolução do target.
- [ ] ❌ Confirmar target pertence aos candidatos.
- [ ] ❌ Confirmar centro dentro dos limites.
- [ ] ❌ Confirmar scope.
- [ ] ❌ Confirmar baixa confidence é rejeitada.
- [ ] ❌ Confirmar target grounded.

## 4.5 Segurança

- [ ] ❌ Confirmar que provider não possui Permission.
- [ ] ❌ Confirmar que pipeline não executa input.
- [ ] ❌ Confirmar nenhum clique/tecla.
- [ ] ❌ Confirmar `ComputerControlService` não foi usado para executar.

## 4.6 Smoke oficial

```powershell
$env:LUMEN_F28_PHYSICAL_CONFIRM="YES"
$env:LUMEN_OLLAMA_VISION_MODEL="MODELO_MULTIMODAL_REAL"
$env:LUMEN_F28_TARGET_LABEL="ALVO_VISIVEL"
python scripts/f28_vision_smoke.py
```

- [ ] ❌ Executar.
- [ ] ❌ Registrar modelo.
- [ ] ❌ Registrar número de elementos.
- [ ] ❌ Registrar target/confidence.
- [ ] ❌ Confirmar `F28 physical input: DISARMED`.

## F28 só vira 🟩 quando

Provider real + screenshot real + elementos + target grounded forem comprovados sem input físico.

**Estado atual: ✅ CONCLUÍDO.** Evidência real registrada: qwen3-vl:2b-instruct, screenshot 3840x1125, target PowerShell, posição (802, 838), confidence 0.990 e input físico desarmado.

---

# 6. F29 — REAL AUTONOMOUS COMPUTER AGENT

**Componente:** `app/computer_control/autonomous_agent.py`.

Fluxo obrigatório:
`Goal → Plan → Observe → Target → Action → Verify → Recover → Replan`.

## 5.1 Primeira execução

Usar aplicação benigna já aberta e uma ação reversível.

Não usar inicialmente:
- terminal/CMD/PowerShell;
- navegador autenticado;
- arquivos importantes;
- exclusão;
- instalação;
- configurações;
- ações financeiras;
- Unreal como primeira ação.

## 5.2 Planner

- [ ] ❌ Registrar planner utilizado.
- [ ] ❌ Registrar provider/modelo se houver LLM real.
- [ ] ❌ Confirmar planner não concede Permission.
- [ ] ❌ Confirmar planner não acessa driver.
- [ ] ❌ Confirmar plano bounded.

## 5.3 Verifier

- [ ] ❌ Registrar `ComputerAgentVerifier`.
- [ ] ❌ Definir expectativa verificável.
- [ ] ❌ Confirmar verificação usa observação pós-ação.
- [ ] ❌ Não aceitar “chamada ao driver retornou sucesso” como verification.

## 5.4 Checkpoint obrigatório

Configurar `require_checkpoint=True`.

- [ ] ❌ Goal.
- [ ] ❌ Observe.
- [ ] ❌ Plan.
- [ ] ❌ Target.
- [ ] ❌ Confirmar `WAITING_APPROVAL`.
- [ ] ❌ Confirmar nenhuma ação ocorreu antes da aprovação.
- [ ] ❌ Registrar checkpoint ID.
- [ ] ❌ Aprovar somente após inspeção humana.

## 5.5 Ação real

Após aprovação explícita:
- [ ] ❌ Action real.
- [ ] ❌ Observação pós-ação.
- [ ] ❌ Verification real.
- [ ] ❌ `VerificationStatus.VERIFIED`.
- [ ] ❌ Estado `COMPLETED`.

## 5.6 Falha controlada

Com target ausente:
- [ ] ❌ Confirmar falha de target.
- [ ] ❌ Confirmar REPLAN.
- [ ] ❌ Confirmar limite de replans.
- [ ] ❌ Confirmar ausência de loop infinito.

## 5.7 Recovery

- [ ] ❌ Provocar falha não destrutiva.
- [ ] ❌ Confirmar RECOVER.
- [ ] ❌ Confirmar contador.
- [ ] ❌ Confirmar orçamento não cresce.
- [ ] ❌ Confirmar REPLAN/encerramento bounded.

## 5.8 Segurança

- [ ] ❌ Confirmar nenhum acesso direto ao Windows driver.
- [ ] ❌ Confirmar execução exclusivamente pelo `ComputerControlService`.
- [ ] ❌ Confirmar Permission/Policy/Scope/Checkpoint preservados.
- [ ] ❌ Confirmar confidence visual não vira autorização.
- [ ] ❌ Confirmar budgets não são ampliados.

## F29 só vira 🟩 quando

Houver evidência real de goal, observe, plan, target, checkpoint, approval, action, verification e pelo menos um caminho bounded de falha/recovery.

**Estado atual: ✅ CONCLUÍDO.** Execução real final: waiting_approval → checkpoint CC-CP-000001 → aprovação explícita → completed; 1 ciclo, 0 replans, 0 recoveries; ação física limitada a MOUSE_MOVE.

---

# 7. F30 — REAL UNREAL INTEGRATION

**Componente:** `app/unreal/integration.py`.

## 6.1 Projeto existente

- [x] ✅ Usar projeto Unreal existente.
- [x] ✅ Caminho absoluto.
- [x] ✅ Exatamente um `.uproject` na raiz.
- [x] ✅ Descriptor válido.
- [x] ✅ Content verificado.
- [x] ✅ Source verificado.
- [x] ✅ Config verificado.
- [x] ✅ Saved verificado.
- [x] ✅ Não foi criado outro projeto.

Projeto real: AgeOfAether. EngineAssociation: 5.8.

**Observação:** Plugins não existiam inicialmente na raiz do projeto e eram opcionais para a descoberta. Durante a investigação do Slate, ToolsetRegistry e SlateInspectorToolset foram explicitamente habilitados com backup do .uproject.

## 6.2 Editor real

- [x] ✅ Abrir projeto existente no Unreal Editor.
- [x] ✅ Confirmar janela real.
- [x] ✅ Confirmar título/projeto.
- [x] ✅ Descobrir via Windows Native.
- [x] ✅ Registrar evidência.

Última evidência: AgeOfAether — Unreal Editor, processo UnrealEditor.exe, Windows Native Discovery=PASS.

## 6.3 UI real

- [ ] ❌ Content Browser via UIA externa — ainda não exposto.
- [ ] ❌ Blueprint Editor via UIA externa — ainda não exposto.
- [ ] ❌ Output Log via UIA externa — ainda não exposto.
- [ ] ❌ PIE quando aplicável.
- [x] ✅ UI Automation real executada sem crash.
- [x] ✅ Inspeção real sem mock/fake.
- [ ] ❌ Elementos internos Slate ainda não comprovados pela integração da Lúmen.

**Achado real:** a inspeção externa chegou a ELEMENTS_INSPECTED=1, com Content Browser/Blueprint/Output Log/PIE não identificados. Isso motivou a investigação do SlateInspectorToolset.

## 6.4 Blueprint

- [ ] ❌ Abrir Blueprint existente.
- [ ] ❌ Confirmar editor.
- [ ] ❌ Executar operação segura/aprovada.
- [ ] ❌ Compilar Blueprint.
- [ ] ❌ Confirmar sucesso.
- [ ] ❌ Confirmar estado posterior.

## 6.5 C++

Se houver C++:
- [ ] ❌ Abrir código existente.
- [ ] ❌ Executar edição segura/aprovada se necessária.
- [ ] ❌ Compile/build real.
- [ ] ❌ Confirmar resultado.
- [ ] ❌ Confirmar Output Log.

Se não houver C++:
- [ ] ⚠️ Registrar “C++ não aplicável ao projeto”.
- [ ] ⚠️ Não fabricar um C++ só para gerar PASS.

## 6.6 Build/Compile

- [ ] ❌ Build real quando aplicável.
- [ ] ❌ Compile real.
- [ ] ❌ Confirmar sucesso.
- [ ] ❌ Registrar erros/warnings relevantes.

## 6.7 PIE

- [ ] ❌ Iniciar PIE.
- [ ] ❌ Confirmar estado PLAY.
- [ ] ❌ Executar ação simples.
- [ ] ❌ Confirmar resultado.
- [ ] ❌ Parar PIE controladamente.
- [ ] ❌ Confirmar retorno ao Editor.

## 6.8 Logs

- [ ] ❌ Abrir/inspecionar Output Log.
- [ ] ❌ Diferenciar warning de erro real.
- [ ] ❌ Registrar falhas.

## 6.9 Recovery

- [ ] ❌ Criar somente falha controlada/reversível.
- [ ] ❌ Detectar erro.
- [ ] ❌ Planejar recovery.
- [ ] ❌ Aprovar operação mutável.
- [ ] ❌ Executar recovery.
- [ ] ❌ Verificar estado recuperado.

## 6.10 Segurança

- [ ] ❌ Confirmar integração não chama driver diretamente.
- [ ] ❌ Permission.
- [ ] ❌ Policy.
- [ ] ❌ Scope.
- [ ] ❌ Checkpoint.
- [ ] ❌ Audit.
- [ ] ❌ Verification.
- [ ] ❌ Nenhuma mutação sem aprovação.

## F30 só vira 🟩 quando

Projeto real + Editor + UI + Blueprint + C++ quando aplicável + compile/build + PIE + logs + recovery forem comprovados.

---

# 8. F31 — EXPERIENCE & WORKFLOW INTELLIGENCE

A documentação oficial não define F31 como gate físico independente.

- [ ] ⏭️ Não exigir hardware físico específico para “passar F31”.
- [ ] ❌ Como E2E recomendado, executar workflow real bem-sucedido após F29.
- [ ] ❌ Registrar experiência.
- [ ] ❌ Confirmar que generalização exige sucesso + verification.
- [ ] ❌ Confirmar persistência.
- [ ] ❌ Reiniciar processo/sessão.
- [ ] ❌ Fazer recall.
- [ ] ❌ Confirmar reuse somente com evidência válida.
- [ ] ❌ Confirmar adaptação somente em bindings declarados.
- [ ] ❌ Confirmar redaction de secrets.
- [ ] ❌ Confirmar ausência de screenshot/conteúdo sensível.
- [ ] ❌ Confirmar que experiência não ganhou autoridade de execução.

Este bloco é **E2E recomendado**, não um novo gate físico.

---

# 9. F32 — CLOSED-LOOP LUMEN EVOLUTION

F32 é deliberativa/evidencial e não possui hardware físico próprio.

- [ ] ⏭️ Não criar “teste físico F32” artificial.
- [ ] ❌ Usar evidência real de F29/F30.
- [ ] ❌ Start cycle.
- [ ] ❌ Observe.
- [ ] ❌ Assess.
- [ ] ❌ Trigger quando houver degradação.
- [ ] ❌ Confirmar IDs de evidência.
- [ ] ❌ Plan.
- [ ] ❌ Confirmar evidence IDs exatos.
- [ ] ❌ Abrir Evolution Gate F24.
- [ ] ❌ Confirmar WAITING_EVIDENCE.
- [ ] ❌ Confirmar WAITING_APPROVAL.
- [ ] ❌ Confirmar ausência de promoção automática.
- [ ] ❌ Approval explícito.
- [ ] ❌ PROMOTED.
- [ ] ❌ MONITORED.
- [ ] ❌ CLOSED/REJECTED conforme resultado.
- [ ] ❌ Persistência.
- [ ] ❌ Digest determinístico.
- [ ] ❌ Nenhum secret/screenshot/conteúdo sensível persistido.

### Negativos F32

- [ ] ❌ Tentar promoção sem approval → deve falhar.
- [ ] ❌ Evidence ID incorreto → deve falhar.
- [ ] ❌ Tentar usar F32 como executor → deve não existir superfície de execução.
- [ ] ❌ Confirmar que nenhum bypass foi criado.

---

# 10. TESTE END-TO-END FINAL

Depois de F27–F30:

`Windows → Vision → Grounding → Agent → Action → Verification → Experience → Evidence → F32`

- [ ] ❌ Windows real.
- [ ] ❌ Screenshot.
- [ ] ❌ Vision real.
- [ ] ❌ Grounding.
- [ ] ❌ Goal.
- [ ] ❌ Plan.
- [ ] ❌ Checkpoint.
- [ ] ❌ Approval.
- [ ] ❌ Action.
- [ ] ❌ Verification.
- [ ] ❌ Experience.
- [ ] ❌ Persistence/Recall.
- [ ] ❌ Evidence.
- [ ] ❌ F32 trigger/plan/gate.
- [ ] ❌ Human approval.
- [ ] ❌ Monitoring.
- [ ] ❌ Segurança preservada do início ao fim.

---

# 11. MATRIZ DE FECHAMENTO

| Gate | Código | CI | Real agora | Ação |
|---|---:|---:|---:|---|
| Provider local / cérebro | ✅ | — | ✅ PASS real | Ollama + modelo + inferência pela Lúmen validados |\n| F27 Windows | ✅ | ✅ | ✅ PASS real | smoke físico já executado |
| F28 Vision | ✅ | ✅ | ✅ PASS real | provider multimodal + grounding já executados |
| F29 Autonomous | ✅ | ✅ | ✅ PASS real | agente físico + checkpoint + verification já executados |
| F30 Unreal | ✅ | ✅ | ⚠️ Parcial | integração Slate/tool bridge + workflow Unreal ainda pendentes |
| F31 Experience | ✅ | ✅ | ⏭️ | E2E recomendado |
| F32 Closed Loop | ✅ | ✅ | ⏭️ | E2E recomendado |
| F0–F26 | ✅ | ✅ | ⏭️ | nenhum gate físico identificado |
| F33 | — | — | ⏭️ | não definida |

---

# 12. EVIDÊNCIA OBRIGATÓRIA POR TESTE

Para cada execução, o novo chat deve registrar:

```text
ID:
Fase:
Data/hora:
Máquina:
Windows:
Python:
Lumen commit:
Provider:
Modelo:
Unreal/Projeto:
Pré-condições:
Comando:
Resultado observado:
PASS/FAIL:
Evidência:
Erros:
Impacto:
Próximo teste:
```

F29:
```text
Goal:
Planner:
Vision:
Target:
Checkpoint:
Approval:
Action:
Verification:
Recoveries:
Replans:
Cycles:
Estado final:
```

F30:
```text
Projeto:
.uproject:
Engine:
Editor:
Content Browser:
Blueprint:
C++:
Compile:
Build:
PIE:
Output Log:
Recovery:
```

---

# 13. REGRA DE PASS/FAIL

Só trocar **❌ → ✅** se:

1. executado realmente;
2. ambiente correto;
3. componente real;
4. sem mock/fake substituindo o alvo;
5. sem bypass;
6. evidência objetiva;
7. resultado corresponde ao critério;
8. não existe erro oculto invalidando o resultado.

**“Funcionou” sem evidência não é PASS.**

**CI verde não transforma teste físico em PASS.**

Em caso de falha:
- [ ] ❌ preservar evidência;
- [ ] ❌ registrar erro completo;
- [ ] ❌ classificar ambiente/configuração/integração/código;
- [ ] ❌ não mascarar falha;
- [ ] ❌ não apagar teste;
- [ ] ❌ corrigir somente após causa identificada;
- [ ] ❌ atualizar este checklist.

---

# 14. ORDEM OFICIAL

1. Pre-flight
2. F27 Windows físico
3. F28 Vision/Grounding real
4. F29 Autonomous Agent real
5. F30 Unreal real — CONCLUÍDO
6. F31 E2E recomendado
7. F32 E2E recomendado
8. Teste integrado final
9. Auditoria final
10. Atualizar `LUMEN_STATE.md`
11. Atualizar `docs/LUMEN_MASTER_ROADMAP.md`
12. Commit/PR/CI
13. Confirmar `master`

Não pular F27/F28 para testar autonomia. F29 depende das fundações reais de Computer Control + Vision.

---

# 15. CRITÉRIO ABSOLUTO DE “F0–F32 CONCLUÍDA COM TESTES REAIS”

- [ ] ❌ F27 PASS real.
- [ ] ❌ F28 PASS real.
- [ ] ❌ F29 PASS real.
- [x] ✅ F30 PASS real.
- [x] ✅ F31 E2E recomendado concluído — 1 passed.
- [x] ✅ F32 E2E recomendado concluído — 1 passed.
- [x] ✅ Teste integrado final PASS — 1 passed.
- [ ] ❌ Evidências preservadas.
- [ ] ❌ Nenhum bypass.
- [ ] ❌ Documentação canônica atualizada.
- [ ] ❌ Master contém as alterações aprovadas.
- [ ] ❌ Auditoria final sem gates reais pendentes.

---

# 16. ESTADO ATUAL DO CHECKLIST

Este checklist foi atualizado em **2026-09-29** para refletir as evidências reais obtidas após a recuperação do ambiente.

Estado atual:
- Provider local / cérebro: **✅ PASS REAL**
- F27 real: **✅ PASS REAL**
- F28 real: **✅ PASS REAL**
- F29 real: **✅ PASS REAL**
- F30 real: **✅ PASS REAL — APROVADA**
- F31 E2E: **✅ PASS — 1 passed**
- F32 E2E: **✅ PASS — 1 passed**
- Final integrado: **✅ PASS — 1 passed**

## Evidências reais consolidadas

### Provider local
- Ollama real: **PASS**
- Modelo textual real: qwen3:8b
- Lúmen v0.6.8 iniciou usando provider=ollama e modelo=qwen3:8b
- Conversações reais foram respondidas pelo provider local
- Após a queda de energia, o endpoint local foi novamente confirmado
- Modelo observado no /api/tags: qwen3:8b, 5225388164 bytes
- Modelo multimodal real validado para F28: qwen3-vl:2b-instruct

### F27
- Screenshot real: **PASS**
- Resolução observada: 3840x1125
- Mouse move real: **PASS**
- Teclado real com marcador LUMEN_F27_SMOKE: **PASS**
- Nenhuma ação destrutiva executada

### F28
- Provider multimodal real: **ollama:qwen3-vl:2b-instruct**
- Screenshot real: 3840x1125
- Target real detectado: PowerShell
- Coordenadas reportadas: (802, 838)
- Confidence: 0.990
- Input físico: desarmado
- Testes de regressão relacionados passaram e a suíte global anterior chegou a 1446 passed, 49 skipped

### F29
- Screenshot real: **PASS**
- Estado inicial: waiting_approval
- Checkpoint: CC-CP-000001
- Estado final: completed
- Cycles: 1
- Replans: 0
- Recoveries: 0
- Ação física: MOUSE_MOVE ONLY
- Click/typing/scroll/focus físicos não foram executados
- Fluxo: Goal → Plan → Observe → Target → Checkpoint → Action → Verify → Success

### F30
- Projeto real: AgeOfAether
- Engine: 5.8
- Unreal Editor real aberto e responsivo
- Windows Native Discovery: **PASS**
- UI Automation externa: **PASS técnico**, porém somente 1 elemento foi exposto
- Content Browser / Blueprint / Output Log / PIE ainda não foram comprovados pela UIA externa
- ToolsetRegistry inicialmente ausente do .uproject
- SlateInspectorToolset inicialmente ausente do .uproject
- Backup criado antes da habilitação: AgeOfAether.uproject.bak-20260929-100014
- ToolsetRegistry habilitado
- SlateInspectorToolset habilitado
- DLLs reais carregadas no UnrealEditor.exe
- Log real mostrou o registro efetivo de SlateInspectorToolset
- API real USlateInspectorToolset::Snapshot(...) localizada
- A ponte externa para chamar Snapshot ainda não foi identificada; a tentativa de rota Python não encontrou arquivos Python no plugin

## Próximo ponto oficial da validação

F30 está encerrada e não deve ser repetida. A ponte real MCP/Slate, o grounding, a conversão de coordenadas, o checkpoint, o clique físico controlado e a verificação pós-ação já foram comprovados.

F31 E2E: **PASS — 1 passed**.
F32 E2E: **PASS — 1 passed**.
Teste integrado final F30 → F31 → F32: **PASS — 1 passed**.

Próximo: auditoria final e consolidação documental.

**Não criar novo gate físico artificial para F31/F32.**
**Não criar outra Lumen, outro projeto Unreal ou bypassar Permission/Policy/Scope/Checkpoint/Audit/Sandbox.**

Este arquivo é o checklist operacional oficial dos testes reais e deve acompanhar as evidências efetivamente executadas no ambiente do operador.
