# Roadmap da Lumen

**Status atual: `0.6.8` (base oficial) + fases internas 9A×2, 9B, 10A, 10B, 11A,
11B, 11C, 11D, 11E, 11F, 11G, 11H, 11I e 11J concluídas sem bump de
versão — ver "Estado real" abaixo.**

Cada versão entrega um incremento fechado e testado. Regra de ouro do
projeto: **nenhuma capacidade sensível entra sem que a camada de
permissões e o fluxo de confirmação do usuário estejam prontos antes**.

---

## Estado real (2026-08-31) — base 0.6.8 + fases internas 9A–11J

Concluído sobre a 0.6.8, **sem bump de versão** (engenharia interna;
detalhes em `LUMEN_STATE.md`):

- **9A×2** — auditorias read-only da cadeia de execução.
- **9B** — persistência opt-in do execution state (bundles
  sanitizados em `data/executions`; default OFF).
- **10A/10B** — Advanced Planning MVP: guardrails do Planner
  (12 tarefas, profundidade 6, 16 KiB/campo, 4 refs/parâmetro),
  refinador conservador em 2 estágios (default OFF), data-flow
  `${Tn.data.campo}` validado no planejamento, `success_criteria`
  (metadado). R4 (replanning automático) PROIBIDO/adiado.
- **11A** — auditoria + spec do Coding Agent (read-only).
- **11B** — tool `search_files` (READ-only): 7ª tool de filesystem no
  registry default **e presente no Planner Catalog** (planejamento
  automático OK); 19 testes dedicados; PROBE oficial 22/22.
- **11C** — tool `edit_file` (**WRITE**): edição **literal com
  ocorrência exatamente 1** (0 ⇒ `NO_MATCH`; ≥2 ⇒ `MULTIPLE_MATCHES`;
  nada é escrito em falha); tool **destrutiva ⇒ checkpoint
  obrigatório** antes de escrever (aprovação aplica; recusa mantém o
  arquivo intacto); presente no **Planner Catalog** (planejamento
  automático OK); +7 testes dedicados e +2 de integração de
  checkpoint. Spec: `docs/SPEC-11C-EDIT_FILE.md`.
- **11D** — tool `run_pytest` (**TERMINAL**): runner dedicado que roda
  a suíte pytest do workspace de forma **estruturada** (subprocesso
  controlado, sem shell — `python`/`pytest` seguem na denylist do
  terminal, sem liberar nada no `run_command`); **checkpoint
  obrigatório antes de executar** (aprovação executa; recusa não
  executa); registrada no registry e no **Planner Catalog** somente
  com o terminal habilitado; saída estruturada (`exit_code`,
  `summary_line`, truncamento) sem vazar output completo na
  auditoria; +2 testes de integração de checkpoint e +4 de
  validação de protocolo/catálogo. Spec:
  `docs/SPEC-11D-BUILD_TEST.md`.
- **11E** — **verificação real opt-in**: `enable_verification("pytest_result")`
  no `ToolsController` (default OFF) instala o
  `PytestResultVerifier` — **interpretativo, não executa nada** (a
  execução real é a task `run_pytest` da 11D, com TERMINAL +
  checkpoint); o verifier lê o JSON do `ToolResult`: verde ⇒
  `verified=True`, vermelho ⇒ task `REJECTED` e plano falha
  (fail-fast); `applied=False` para tasks não aplicáveis mantém
  `verified=None`; +4 testes (flag `applied` + e2e verde/vermelho).
  Spec: `docs/SPEC-11E-REAL_VERIFICATION.md`.
- **11F** — **auto-anexo de `run_pytest` após WRITE** (opt-in): em
  `ToolsController.run_plan`, quando terminal habilitado + verificação
  11E habilitada + plano contém WRITE (`write_file`/`create_file`/
  `delete_file`/`edit_file`), é anexada 1 task final `run_pytest`
  (depende de todas as anteriores) antes de executar; idempotente
  (não anexa se `run_pytest` já estiver no plano; default continua sem
  auto-anexo); guardrail: plano em 12/12 tasks + anexo necessário ⇒
  **falha antes de executar** (FAILED, tudo SKIPPED, nada roda); +3
  testes. Spec: `docs/SPEC-11F-AUTO_PYTEST_AFTER_WRITE.md`.
- **11G** — **evidência real em modo corrections** (sem bypass): em
  modo corrections o verifier 11E agora se aplica
  (`verifier_factory` no `CorrectionEngine`) — pytest vermelho ⇒ task
  `REJECTED` (não `DONE`); cada sucessor `#C` passa por hook
  `plan_transform` que reutiliza a regra 11F para manter a evidência
  `run_pytest` ao final quando aplicável (idempotente; respeita o teto
  de 12 tasks — falha controlada se não puder anexar, sem executar o
  sucessor). Sem bypass (pytest sempre via task com checkpoint) e sem
  repair-loop automático/auto-replanning; +2 testes. Spec:
  `docs/SPEC-11G-CORRECTIONS_EVIDENCE.md`.
- **11H** — **toggles persistentes de automação (Settings/UI)**:
  `ToggleStore` (`app/tools/toggles_store.py`) persiste
  `data/agent_toggles.json` (escrita atômica, schema `version: 1`,
  **fail-closed** — arquivo ausente/corrompido ⇒ tudo OFF, sem
  exceção) com `corrections_enabled`/`verification_enabled`; o
  `ToolsController` restaura/aplica no startup via `toggles_file`
  (`main.py` passa `settings.data_dir / "agent_toggles.json"`) e os
  setters persistem na hora (auditados); `ToolsDialog` ganhou a seção
  **AUTOMAÇÃO (11H)** (ligar/desligar Correções e Verificação real —
  reflete o controller ao abrir; persiste ao clicar). **Os toggles
  nunca concedem permissão** — TERMINAL continua concessão explícita
  por sessão (regra 0.6.x); +5 testes (3 persistência no controller +
  2 UI headless). Spec:
  `docs/SPEC-11H-SETTINGS_UI_TOGGLES.md`.
- **11I** — **export de relatório de evidências (opt-in)**: flag
  `LUMEN_EXPORT_EXECUTION_REPORTS` (Settings, **default OFF** — bit-a-bit
  atual); em estado terminal (COMPLETED/FAILED), o funil `_final`
  exporta (best-effort — **falha não quebra a execução**) um JSON
  **sanitizado** em `data_dir/reports/<plan_id_sanitizado>.json`
  contendo `plan` + `execution_report` + `correction_history` +
  auditoria **filtrada por `plan_id`** (módulo puro
  `app/tools/report_export.py`; sanitização reutilizada do 9B —
  segredos redigidos, strings truncadas, sem stdout). **Sem execução,
  sem permissões**; +2 testes (export ON sanitizado / OFF bit-a-bit).
  Spec: `docs/SPEC-11I-REPORT_EXPORT.md`.
- **11J** — **correções com evidência (advice-only)**: a estratégia
  **default** de `enable_corrections` agora é
  `EvidenceCorrectionStrategy` sobre a conservadora
  `ToolCorrectionStrategy` (strategy custom nunca é sobrescrita); para
  falhas de `run_pytest` (REJECTED/FAILED), ela extrai a evidência real
  (`exit_code`/`summary_line`/`timed_out`/`truncated`) do JSON do
  `ToolResult` em `run.result` (somente parse — **sem execução
  escondida**) e produz **conselho** (`corrected_task=None`) registrado
  no ciclo de correção (JSONL) e no relatório 11I — o ciclo encerra
  **sem pausa** (nada é aplicado, sem card; não aplica task
  automaticamente). Sem auto-replanning (R4 continua proíbido);
  correções **com tarefa** continuam exigindo aprovação explícita; +1
  teste. Spec: `docs/SPEC-11J-EVIDENCE_CORRECTIONS.md`.

**Suíte completa: 990 passed / 5 skipped / 0 failed (995 coletados).**

**Próximos tópicos da trilha Coding Agent (0.7) — NÃO AUTORIZADOS /
NÃO IMPLEMENTADOS:** verificação real completa, repair-loop (reparo
via CorrectionEngine), wiring Settings→Planner. O runner dedicado de
build/test estruturado (`run_pytest`) foi entregue na 11D, a
verificação real (opt-in) na 11E, o auto-anexo após WRITE na 11F, a
evidência em modo corrections na 11G, os toggles persistentes
(Settings/UI) na 11H, o export de relatório de evidências (opt-in) na
11I e o conselho com evidência nas correções (advice-only) na 11J.
Restrições vigentes preservadas: R4 (sem replanning automático) e F17
(sem Computer Control / vision / Unreal / Blueprint / C++).

## Lumen 0.1 — Fundação ✅

- Arquitetura modular em camadas (UI → Agent Core → AI Provider →
  Memory → Task System → Tools → Permissions).
- Interface Tkinter (conversa, entrada, envio, indicador de estado).
- `AIProvider` (abstração) + `MockProvider` — funciona sem API externa.
- Memória de conversa local (JSON, escrita atômica).
- Task Manager inicial (`id`, `title`, `status`, `created_at`; sem execução).
- Contrato de ferramentas (`Tool` + `ToolRegistry`) — nenhuma tool concreta.
- Permissões (`CHAT`, `READ`, `WRITE`, `TERMINAL`, `COMPUTER_CONTROL`);
  apenas `CHAT` por padrão.
- Configuração `.env`, logging com redação de segredos, testes pytest.

## Lumen 0.2 — Cérebro Real ✅

- **`OpenAIProvider`** (SDK oficial, import lazy) selecionável via
  `LUMEN_PROVIDER=openai`; `mock` continua como modo offline padrão.
- **`GeminiProvider`** (complemento) — Google Gemini via SDK oficial
  `google-genai`, modelo padrão GA `gemini-2.5-flash`, no mesmo sistema
  de cofre/troca de provider/TESTAR CONEXÃO da tela ⚙ Configurações.
- Configuração validada na inicialização: API key/modelo ausentes geram
  mensagens claras explicando como configurar o `.env`.
- **Persona central** (`app/config/persona.py`): nome Lumen, assistente
  feminina, papel de desenvolvimento, idioma português — e **system
  prompt** único, organizado em seções (identidade, papel, idioma,
  estilo, honestidade/limitações, futuro).
- **Contexto**: o Agent envia system prompt + histórico limitado
  (`LUMEN_MAX_CONTEXT_MESSAGES`) + mensagem atual; timestamps são
  removidos do payload.
- **Streaming**: resposta exibida progressivamente na UI via callback
  `on_delta` (fila + `after`); sem retry após deltas emitidos (evita
  duplicação visível).
- **Timeout** (`LUMEN_REQUEST_TIMEOUT`) e **retry limitado**
  (`LUMEN_MAX_RETRIES`) apenas para erros temporários (rate limit,
  timeout, rede, 5xx); nunca para autenticação/configuração.
- **Taxonomia de erros**: key ausente, autenticação inválida, modelo
  inválido, rate limit, timeout, rede, 5xx, dependência ausente,
  inesperado — todos com mensagem amigável e detalhes técnicos no log.
- **`AIResponse` normalizada** (content, model, usage de tokens,
  finish_reason) + `ResponseType` (FINAL_RESPONSE | TOOL_CALL | PLAN)
  preparando o futuro de agente sem reescrever o Agent Core.
- UI: cabeçalho com provedor/modelo, status ● Pensando…, erros amigáveis,
  resposta progressiva.
- Testes: 104 (todos offline; chamadas OpenAI simuladas por client fake).

## Lumen 0.3 — Memória avançada ✅ *(fundação entregue)*

Escopo real entregue nesta etapa (fundação da memória inteligente,
conforme a spec: *"apenas a parte de memória"*):

- **Memória estruturada em 6 domínios** — projetos, tarefas,
  conhecimento, decisões, erros e soluções (`MemoryKind` +
  `RecordStore` por domínio, JSON local com escrita atômica) — separada
  da conversa cotidiana (que continua linear como na 0.1).
- **Registros completos**: id sequencial por domínio (`PRJ-`, `TASK-`,
  `KN-`, `DEC-`, `ERR-`, `SOL-0001`), timestamps, origem, tags,
  `project_id`, relacionamentos (`related_ids`, bidirecionais via
  `relate()`), `supersedes` e `content_hash`.
- **Ciclo de vida**: deduplicação por hash entre ACTIVE; `update`
  imutável (recalcula hash, rejeita colisão); `mark_obsolete`;
  `supersede` cria o sucessor e preserva a trilha do antecessor.
- **Busca por relevância**: título 3 > tag 2 > conteúdo 1, +1 quando
  todos os termos casam; acento-insensível; obsoletos penalizados (×0,2)
  e excluídos por padrão.
- **Contexto para a IA**: `MemorySystem.build_context(query)` monta o
  pacote (registros estruturados primeiro, conversa completa a cota,
  excertos ≤400 chars) limitado por `LUMEN_MAX_MEMORY_RECORDS` — o ganho
  pronto para o fluxo futuro do Agent (0.4+).
- **Segurança**: `redact_secrets` roda **antes** de persistir em
  qualquer domínio; arquivo corrompido/inválido → erro claro
  (`RecordStoreError`); memória 100% local, nunca enviada a provedores.

**Ainda NÃO entregue (adiei de propósito — ver 0.3.x):** a integração
da memória ao fluxo do Agent (o Agent ainda não consulta
`build_context()` ao responder), sumarização, busca semântica, múltiplas
sessões e SQLite — os quatro primeiros itens abaixo vieram do ROADMAP
original da 0.3 e foram re-escalonados para não inflar esta etapa:

## Lumen 0.3.x — Provider Expansion ✅ *(complemento entregue 2026-08-28)*

Expansão da camada de providers, sem tocar Agent/UI/memória além da
integração já existente (escopo fechado; detalhes em `LUMEN_STATE.md`):

- **`GroqProvider`** (`app/ai/groq_provider.py`, SDK oficial `groq`) —
  padrão `openai/gpt-oss-120b`; também serve os Llama
  `llama-3.3-70b-versatile`/`llama-3.1-8b-instant`.
- **`TogetherProvider`** (`app/ai/together_provider.py`, SDK oficial
  `together`) — **Llama 4 real**: padrão
  `meta-llama/Llama-4-Scout-17B-16E-Instruct`; alternativa Maverick.
  Escolhido após a Meta **encerrar a Llama API em 06/07/2026** e a
  Cerebras remover os Llama do catálogo público (decisão documentada em
  `docs/ARCHITECTURE.md` §3.7).
- Ambos no registro da fábrica (`mock | openai | gemini | groq |
  together`), na tela ⚙ (descoberta dinâmica), no cofre de credenciais,
  TESTAR CONEXÃO, timeout/retry/streaming e troca em runtime — mesma
  taxonomia de erros e contratos do `AIProvider`.

## Lumen 0.3.x — Memória avançada (continuação, futura)

> **Entregue nesta linha em 2026-08-28:** o complemento **Provider
> Expansion** (Groq + Together AI/Llama 4) — ver `LUMEN_STATE.md`.
> Os itens abaixo seguem pendentes.

- Integrar a memória estruturada ao fluxo do Agent (consultar
  `build_context()` antes de responder; armazenar conhecimento após a
  resposta) — pré-requisito natural da 0.4.
- Sumarização de conversas longas; memória de longo prazo por projeto.
- Múltiplas conversas/sessões; busca semântica (embeddings locais ou API).
- Migração do armazenamento (ex.: SQLite) sem mudar os contratos.
- Controle de uso de tokens acumulado (a partir do `Usage` já preservado).

## Lumen 0.4 — Planner ✅ *(fundação entregue)*

Escopo real entregue (somente planejamento; **nada é executado**):

- **`app/planner/`** — `Planner.create_plan(pedido)`: prompt de
  planejador com protocolo JSON strict → provedor de IA via abstração
  `AIProvider` (agnóstico: mock/openai/gemini/groq/together) →
  validação (tarefas ≥1, descrições, dependências existentes, sem
  ciclos via ordenação topológica) → `Plan`.
- **Estruturas**: `Plan` (id `PLN-0001`…, objetivo, status, análise
  prévia, timestamps) e `PlannedTask` (id `T1…Tn`, descrição, ordem,
  dependências, estado, resultado, erro) — dados imutáveis.
- **Estados do plano**: `PLANNING` (transitório), `READY` (válido),
  `BLOCKED` (pré-condição do ambiente ausente, ex.: provider sem
  chave), `FAILED` (plano inválido/erro do provedor — motivo claro em
  `error`, nunca traceback) e `COMPLETED` (reservado ao executor
  futuro).
- **Integração com o Agent**: `Agent.request_plan(pedido)` — usa o
  provider vigente (troca em runtime) e o histórico como contexto; o
  fluxo de conversa (`send_message`) permanece intocado.
- **Memória 0.3**: consultada em **somente leitura** (`recall`) para
  enriquecer o planejamento — nunca gravada nem duplicada.
- **Segurança**: nenhuma execução — sem terminal/arquivos/mouse/teclado/
  Unreal/tool calling (garantido por testes estáticos).

**Ainda NÃO entregue (adiei de propósito — ver 0.4.x):** os itens do
ROADMAP original da 0.4 que dependem de execução:

## Lumen 0.4.x — Executor de Planos — fundação ✅

Entregue (simulado/in-memory, sem nenhuma ferramenta real):

- **`app/executor/`** — `PlanExecutor` executa um plano `READY`
  respeitando ordem e dependências (tarefa só roda com dependências
  `DONE`); avanço tarefa por tarefa (`step()`) ou até o fim
  (`run_all()`); **fail-fast** (falha → restantes `SKIPPED`, plano
  `FAILED`); `TaskRun` (resultado/erro/tentativas por tarefa) e
  `ExecutionReport` imutável (eventos, timestamps, `to_dict()`).
- **`TaskHandler` (ABC) + `SimulatedHandler`** — a ação de cada tarefa
  vive no handler; futuramente ferramentas reais (0.5+) entram como
  handlers sobre o `ToolRegistry` (que segue vazio) sem mudar o núcleo:
  `Planner → Executor → TaskHandler → ToolRegistry → Tools`.
- **`ExecutionObserver` (no-op)** + campos `attempts`/`result`/`error`:
  abstrações mínimas preparadas para checkpoints, retry, verificação e
  correção — **não implementados**.
- **`Agent.execute_plan(plan, handler?)`** — gate `CHAT`; não altera
  conversa, memória 0.3 nem providers.
- Estados: plano `RUNNING → COMPLETED|FAILED`; tarefas
  `PENDING → DONE|FAILED|SKIPPED`.

## Lumen 0.4.x — Checkpoints + Retry + Verificação ✅

Entregue (tudo simulado/in-memory; sem UI e sem ferramentas reais):

- **Checkpoints** (`app/executor/checkpoints.py`): `CheckpointPolicy`
  (ABC · `NeverCheckpoints` padrão · `EveryTaskCheckpoints`) — pausa a
  execução antes de ações importantes com `CheckpointRequest`/
  `CheckpointStatus` (`PENDING_APPROVAL` = necessário/execução pausada
  aguardando confirmação · `APPROVED` = aprovado/retoma · `REFUSED` =
  recusado ⇒ plano `FAILED` controlado, tarefa não executada).
  Aprovação/recusa via `executor.approve_checkpoint()`/`refuse_checkpoint()`.
- **Retry controlado** (`app/executor/retry.py`): `RetryPolicy`
  (`max_attempts ≥ 1` validado — **impossível retry infinito**;
  backoff linear injetável) + `AttemptRecord` por tentativa (número,
  resultado, erro) no `TaskRun.attempt_log`; erros inesperados do
  handler não são repetidos.
- **Verificação de resultado** (`app/executor/verification.py`):
  `TaskVerifier` (ABC) + `SimulatedVerifier`; `EXECUTOU → VERIFICOU →
  SUCESSO` (`DONE`/`verified=True`) ou `… → FALHOU` (`REJECTED`/
  `verified=False` com resultado preservado; fail-fast; não consome
  retry).
- **Preparação para correção automática** (`app/executor/correction.py`):
  `CorrectionStrategy` (ABC) + `CorrectionProposal` +
  `NoopCorrectionStrategy` — **abstrações apenas**: o Executor não
  importa/chama o módulo (auditoria AST); o loop
  `falha → análise → correção → nova tentativa → verificação` é futuro.
- `Agent.execute_plan(plan, handler?, verifier?, retry?, checkpoints?)`;
  `ExecutionReport` ganha `checkpoints` (histórico) e
  `pending_checkpoint` (pausa ativa).

## Lumen 0.4.x — Planner/Executor (continuação, futura)

- **Correção automática real**: ligar `CorrectionStrategy` ao fluxo
  (análise da falha — via provider — → proposta → nova tentativa →
  verificação), com limites claros.
- Conectar ferramentas reais ao Executor via handlers sobre o
  `ToolRegistry` (exige as tools da 0.5+ e o porteiro de permissões).
- `TaskStatus`/`TaskManager` integrados à execução e UI para
  exibir/aprovar planos e checkpoints (hoje: aprovação via API interna).
- Respostas do modelo representando `PLAN`/`TOOL_CALL`
  (`ResponseType` já preparado).

## Lumen 0.5 — Filesystem Tools ✅ *(fundação segura)*

Escopo real entregue (somente filesystem; **tudo confinado, permitido e
auditado**):

- **Ferramentas** (`app/tools/filesystem.py`): `list_directory`,
  `read_file` (UTF-8, limite de tamanho), `write_file`
  (cria/sobrescreve), `create_file` (não sobrescreve), `delete_file`
  (opt-in duplo) e `file_exists` — contratos claros, entradas validadas
  e **resultados estruturados** (`ToolResult` em JSON: operação, caminho
  solicitado/resolvido, dados, erro amigável).
- **Sandbox/workspace** (`WorkspaceSandbox`): acesso apenas a diretórios
  **explicitamente autorizados** (raízes absolutas, resolvidas);
  bloqueia `..`/traversal (sempre, até internamente), caminhos fora das
  raízes, caminhos inválidos (vazios, caracteres de controle, tipo
  errado), symlinks que escapam, **escrita em modo somente leitura**
  (default) e exclusão sem `allow_delete=True` + `writable=True`.
- **Permissões**: leitura exige `READ`; escrita/criação/exclusão exigem
  `WRITE` — porteio pelo `ToolRegistry` (o código da ferramenta nem
  roda sem permissão). Concessões continuam explícitas (default: só
  `CHAT`); `main.py`/startup sem efeitos colaterais e **sem permissão
  global nova** (nada de "acesso a todo o Windows").
- **Ponte com o Executor** (`app/tools/handler.py`): `ToolTaskHandler`
  despacha tarefas com `tool`/`parameters` (campos novos e opcionais em
  `PlannedTask`; o protocolo do Planner **não** emite ferramentas —
  planos com tools são montados programaticamente) via `ToolRegistry`;
  tarefa sem ferramenta falha honestamente (nada simulado);
  `ToolCheckpoints` pausa antes de ferramentas destrutivas
  (`write_file`/`create_file`/`delete_file`) — aprovar executa, recusar
  bloqueia (consentimento sem UI obrigatória).
- **Auditoria** (`FilesystemAudit`): toda tentativa (sucesso, bloqueio
  de política/gate de permissão ou erro) registra ferramenta, operação,
  caminho solicitado, caminho resolvido, desfecho, erro, timestamp e
  tarefa/plano de origem — **sem conteúdo de arquivos** (apenas
  metadados: tamanhos/contagens/flags).

**Ainda NÃO entregue na 0.5 (base):** protocolo do Planner emitindo
chamadas de ferramenta; níveis granulares de acesso além da política
atual (ex.: `EXECUTE` — que continua proibido até a 0.6).
*(UI de workspaces/permissões/checkpoints e persistência de auditoria
foram entregues na 0.5.x — seção seguinte.)*

## Lumen 0.5.x — UI de Workspaces, Permissões, Checkpoints e Auditoria ✅

Camada **visual e de controle** para usar as ferramentas com segurança
(toda a lógica no `ToolsController`, testável sem UI; os diálogos são
apenas apresentação):

- **Workspaces** (`app/tools/workspaces.py`): diretórios
  **explicitamente autorizados** com política própria
  (`WorkspaceEntry`: somente leitura · escrita · escrita+exclusão);
  `WorkspaceStore` persiste em `data/workspaces.json` (atômico; arquivo
  só nasce na 1ª autorização) com **validação e normalização**
  (absoluto, existente, diretório, resolvido, sem duplicatas, **raiz de
  disco/Windows inteiro rejeitada**); `MultiWorkspaceSandbox` aplica a
  política **por raiz** (workspace somente-leitura bloqueia escrita
  nele mesmo que outro permita); conjunto vazio ⇒ tudo bloqueado.
  Pela UI (🛡): visualizar/adicionar/remover e ver o modo claramente.
- **Permissões** (`ToolsController`): visualizar/conceder/revogar
  `CHAT`/`READ`/`WRITE` (CHAT segue padrão; READ/WRITE exigem
  concessão explícita); `DELETE` **não** é nível — é o opt-in por
  workspace (escrita + permitir excluir), exibido como tal;
  `TERMINAL`/`COMPUTER_CONTROL` são **rejeitados** pela camada
  (nenhuma concessão silenciosa de níveis futuros).
- **Checkpoints** (`PrevalidatedCheckpoints` + UI): operações
  destrutivas viáveis **pausam** para aprovação; a tela mostra **o
  que** (descrição), **onde** (caminho solicitado → resolvido +
  workspace), **qual ferramenta**, **qual operação/permissão** e
  botões **APROVAR/RECUSAR** — recusa garante que **nada roda**
  (testado); operações inviáveis (sem permissão/fora da política) nem
  chegam a pedir aprovação: falham controladas com o motivo real
  (bloqueio honesto, sem aprovação decorativa).
- **Auditoria** (`app/tools/audit_log.py`): persistência **JSONL**
  (`data/audit/audit.jsonl`, append thread-safe, diretório criado na
  1ª escrita) via sink da 0.5; visualização na UI com ferramenta,
  operação, caminho solicitado/resolvido, ✓/✗, erro, timestamp e
  tarefa/plano — **sem conteúdo de arquivos** (separado do conteúdo
  dos arquivos por construção); leitor tolera linhas corrompidas.
- **Integração**: tela **🛡 Ferramentas** na janela principal
  (`app/ui/tools_dialog.py`); `main.py` compõe o `ToolsController`
  **sem efeitos colaterais** (nenhum arquivo/permissão no startup);
  chat, memória, providers (5), Executor e sandbox da 0.5 intocados
  (suíte 0.5 preservada).

## Lumen 0.6 — Terminal Tools ✅ *(fundação controlada)*

> **Entregue em 2026-08-28 (0.6.0)** — com uma decisão **mais rígida**
> que o item original abaixo: comando fora da allowlist é
> **bloqueado antes de qualquer execução** (não "confirmado e
> executado"). Detalhes em `docs/ARCHITECTURE.md` §17 e
> `LUMEN_STATE.md`.

- **`run_command`** (`app/tools/terminal.py` — `subprocess` controlado
  (2º módulo autorizado na 11D: `run_pytest.py`), garantido por testes
  AST): executa **argv lista sem
  shell**, captura `stdout`/`stderr` separadas com teto, `exit_code`,
  `timed_out` e `truncated`, tudo em `ToolResult` estruturado.
- **Allowlist explícita** (`TerminalPolicy.allow`/
  `ToolsController.enable_terminal`) — nada executa sem estar na lista;
  cada `AllowedCommand` define se exige aprovação (default **sim**),
  timeout próprio e argumentos fixos opcionais; `full_path` exige match
  exato (`/tmp/evil/git` nunca casa com `git`).
- **Denylist permanente** (137 nomes normalizados): shells
  (`sh`/`powershell`/`cmd`…), interpretadores (`python`/`node`…),
  builders (`make`/`dotnet`/`docker`…), escalonamento (`sudo`/`runas`),
  destrutivos/administrativos (`rm`/`shutdown`/`reg`/`chmod`…) e
  **rede** (`curl`/`ssh`…) — jamais allowlistáveis; normalização mata
  aliases (`python.exe`, `POWERSHELL`, `/bin/sh`).
- **Argumentos blindados**: operadores de shell/redirecionamento
  (`&&`, `|`, `;`, `>`, `$(`…), argumentos-perigo (`-exec`, `/c`,
  `-EncodedCommand`), `..` e caminhos absolutos fora dos workspaces —
  todos bloqueados (salvo `allow_operators` explícito).
- **cwd confinado** aos workspaces autorizados (mesmo contrato do
  filesystem 0.5); **timeout obrigatório** (default 10 s, teto 60 s,
  mata o processo); **limite de saída** (64 KiB — trunca e falha
  honesto); **ambiente filho sanitizado** (sem `*KEY*`/`*TOKEN*`/
  `*SECRET*`/`*PASSWORD*` — `printenv` nunca vaza credenciais).
- **Permissão `TERMINAL`** exigida pelo `ToolRegistry` antes de
  qualquer código da ferramenta (concessão programática explícita; a UI
  segue concedendo apenas CHAT/READ/WRITE).
- **Checkpoint** antes de cada comando `requires_approval`
  (`PrevalidatedTerminalCheckpoints` — mesma lógica 0.5.1: só operações
  viáveis pausam; inviáveis falham direto com o motivo real). O card
  mostra **argv completo, permissão e timeout**; recusa ⇒ nada roda.
- **Auditoria JSONL**: comando sanitizado (argv truncado p/ trilha),
  cwd, `exit_code`, `timed_out`/`truncated`, duração, desfecho, erro,
  tarefa/plano — **nunca stdout/stderr/conteúdo**.
- **Plano Executor/Planner intactos** (agnósticos); registro só via
  `enable_terminal` — **nada habilitado no startup**.
- Itens originais cumpridos: allowlist ✔ timeout ✔ captura de saída ✔
  sandbox (cwd) ✔ permissão `TERMINAL` ✔.

## Lumen 0.6.x — UI de Terminal, Allowlist e Concessão TERMINAL ✅

Fechamento do **ciclo humano** do terminal (como a 0.5.x foi para a
0.5): quem concede, cadastra e remove é o usuário, pela tela 🛡 — a UI
fala **somente** com o `ToolsController` (nenhuma lógica de segurança na
interface; testes garantem por AST/inspeção):

- **Concessão `TERMINAL` explícita e auditada**: ver estado, conceder e
  revogar por botão dedicado (`grant_terminal`/`revoke_terminal`); o
  caminho **genérico** de permissões segue **rejeitando** TERMINAL
  (nenhuma concessão silenciosa ou "por engano"); `COMPUTER_CONTROL`
  permanece inconcedível por qualquer via; a concessão **vale só na
  sessão** — nunca é persistida nem restaurada do disco. A UI deixa
  claro o que TERMINAL permite: **apenas comandos da allowlist**, dentro
  dos workspaces, com timeout, limite de saída, ambiente sem segredos e
  checkpoint por comando (shells/interpretadores/rede proibidos).
- **Allowlist gerenciável pela UI**: cadastrar comando (com aprovação
  obrigatória — default — ou execução direto), remover, e desabilitar o
  terminal (esvazia a lista). Persistência em `data/terminal.json`
  (`TerminalStore`: escrita atômica; arquivo só nasce no primeiro
  cadastro; **fail closed** — arquivo ilegível ⇒ terminal desabilitado,
  entrada inválida/denylistada ⇒ descartada com aviso; defaults da
  política restaurados). O primeiro cadastro habilita a allowlist (o
  ato explícito de habilitar) — **sem conceder permissão**.
- **Card de aprovação completo**: comando, **argumentos**, **diretório
  de trabalho** e **timeout** em linhas separadas (além de
  ferramenta/operação/permissão); checkpoints da 0.6 intactos (recusa ⇒
  nada roda; só operações viáveis pausam).
- **Auditoria administrativa** em JSONL (`tool=terminal_admin`):
  `terminal_grant`, `terminal_revoke`, `allowlist_add`,
  `allowlist_remove`, `terminal_enable`, `terminal_disable` — inclusive
  tentativas rejeitadas (denylist), sem conteúdo sensível.
- **Startup sem efeitos colaterais preservado**: nenhum
  `terminal.json`/concessão nasce sem ação do usuário; `main.py` apenas
  aponta o caminho do arquivo (leitura).

## Lumen 0.4.x — Correção Automática Controlada ✅ *(0.6.2)*

O mecanismo adiado desde a 0.4.x, agora **real e controlado** — não é
uma autorização para a Lumen fazer qualquer coisa: é o ciclo
**EXECUTAR → VERIFICAR → SUCESSO continua / FALHA → ANALISAR → GERAR
PROPOSTA → CHECKPOINT/APROVAÇÃO quando necessário → APLICAR → RETRY →
VERIFICAR**, limitado ao sistema de ferramentas **já autorizado**.

- **`app/executor/correction.py`** (novo, genérico): `CorrectionEngine`
  + `CorrectionStrategy`/`CorrectionProposal` reais, com estados
  claramente separados (`PROPOSED`, `INVALID`, `REFUSED`, `APPROVED`,
  `APPLIED`, `RETRIED`, `SUCCEEDED`, `FAILED`, `NO_PROPOSAL`,
  `EXHAUSTED`); **planos sucessores imutáveis** (`PLN-…#C1`, `#C2`…;
  tarefa corrigida mantém id/ordem, dependências filtradas; plano
  original intocado — testado); **limites rígidos**: `max_cycles`
  (aplicadas) e `max_total_attempts` (acumuladas) — **nunca retry
  infinito**; `max_cycles=0` desabilita o loop; correção sem
  validação **não executa** (INVALID, nada aplicado, nem pausa);
  recusa ⇒ nada executado depois; falha definitiva ⇒ `FAILED`/
  `EXHAUSTED` + plano `FAILED`. **Não importa `app.tools`**
  (garantido por AST).
- **`app/tools/correction.py`** (novo): `ToolCorrectionStrategy`
  **conservadora** — propõe apenas `create_file → write_file` quando o
  erro é "arquivo já existe"; erros com marcadores de segurança
  (permissão negada, allowlist, fora do workspace, traversal, somente
  leitura, operador de shell…) **nunca** geram proposta (sem bypass);
  `build_proposal_validator` exige tool registrada + permissão
  concedida + sandbox/`TerminalPolicy` aprovando antes de qualquer
  aplicação.
- **`ToolsController`**: `enable_corrections(strategy?, max_cycles=2,
  max_total_attempts=8)` / `disable_corrections` (opt-in do integrador;
  validação dos limites); pendências roteiam transparentemente
  correção × checkpoint de operação (`approve`/`refuse`/`has_pending`/
  `pending_approval`); auditoria JSONL de **todo** ciclo
  (`tool=correction`, `correction_<status>`, sucesso=False para
  desfechos negativos, sem conteúdo sensível).
- **UI 🛡**: card **CORREÇÃO PROPOSTA** (ferramenta de→para, falha de
  execução/verificação, parâmetros original/corrigido); Aprovar aplica
  e segue para o checkpoint da operação; Recusar mantém a falha —
  nada executado depois.
- **Nada além disso**: sem execução arbitrária, shell livre, mouse,
  teclado, screenshot, vision, computer control, Unreal, coding agent,
  acesso fora dos workspaces, bypass de permissões/checkpoints.
  Planner segue sem lógica de execução.

**Validação (2 ambientes):** 771 testes (766 passam + 5 pulam) no
sandbox e na venv limpa; `pyflakes` 0; `pip check` ok; `import main`
ok; harness headless de UI 55/55; auditoria AST/anti-futuro verde.

## Lumen 0.6.3 — Tool Calling / Planner Bridge ✅

A ponte que faltava entre o chat e as ferramentas (diagnóstico 0.6.2:
o chat era puramente conversacional e nenhum pedido chegava ao
Planner/ferramentas). Agora uma solicitação em linguagem natural pode
virar tarefa estruturada — **sem criar nenhum poder novo**:

**CHAT → INTENÇÃO → PLANNER → PLANO (`tool`/`parameters`) → VALIDAÇÃO →
TOOLS CONTROLLER → PERMISSÕES → WORKSPACE → CHECKPOINT → EXECUÇÃO →
VERIFICAÇÃO.**

- **`app/planner/catalog.py`** (novo): allowlist de **protocolo** com as
  ferramentas já existentes (6 filesystem; `run_command` **somente**
  com terminal habilitado). Validação estrita: tool vazia/inventada,
  parâmetros ausentes/desconhecidos/tipos errados, paths absolutos/`..`
  → falha controlada (nada executa, nunca parcialmente).
- **`app/planner/planner.py`**: modo planejamento com ferramentas
  (`create_tool_plan` → `ToolPlanResult` `plan`/`conversation`/
  `invalid`); prompt com a allowlist embutida; tarefas ganham
  `tool`/`parameters` validados.
- **`app/core/bridge.py`** (novo): `ToolCallingBridge` +
  `RequestState` (10 estados: `CONVERSATIONAL`, `PLANNING`,
  `PLAN_READY`, `PLAN_INVALID`, `WAITING_APPROVAL`, `EXECUTING`,
  `VERIFYING`, `COMPLETED`, `FAILED`, `REJECTED`). Conversa segue o
  fluxo clássico (streaming); ação vai ao `ToolsController.run_plan`.
- **`Agent`**: `process_message` (decide conversa × ação via bridge),
  `request_tool_plan`, `set_tools_controller` (injetado pelo `main.py`;
  sem ela o comportamento 0.6.2 é preservado).
- **`MockProvider`**: modo planejador determinístico (offline) — o
  pedido canônico "Crie um arquivo chamado teste_lumen.txt … contendo:
  TESTE LUMEN 0.6.3" gera exatamente `create_file` +
  `{"path": …, "content": …}`; pedidos vagos/destrutivos/injection são
  conversa.
- **Autoridade inalterada**: LLM não é autorização. Permissões (nada
  concedido automaticamente), workspace/sandbox, checkpoints
  (create_file continua pausando para aprovação — agora com o
  **conteúdo** no card), auditoria JSONL e correção 0.6.2 (funciona
  via chat) intactos. Providers 5 preservados; Executor segue sem
  importar `app.tools`; Planner segue sem executar nada.

**Validação (2 ambientes):** 868 testes (863 passam + 5 pulam) no
sandbox E na venv limpa; `pyflakes` 0; `pip check` ok; `import main`
ok; harness headless 55/55; auditoria AST/anti-futuro verde
(`subprocess` só em `terminal.py`; planner/core sem `app.tools`).

## Lumen 0.6.6 — Desfecho pós-aprovação no chat ✅

Correção de UX do fluxo 0.6.3 (diagnóstico: a aprovação do checkpoint
acontecia fora do ciclo do bridge e a janela principal nunca ficava
sabendo do resultado). Agora, depois de APROVAR/RECUSAR na tela 🛡, o
chat exibe a mensagem final (✔ concluído / ✖ falhou / recusa):

- **`app/core/bridge.py`**: `outcome_for_report(request, plan_id,
  report)` público (mesma lógica; `request=None` registra só o desfecho
  na memória linear).
- **`app/ui/tools_dialog.py`**: callback opcional
  `on_plan_finished(report)` (default `None` = comportamento anterior);
  invocado após APROVAR e RECUSAR; falhas do callback não afetam o
  diálogo.
- **`app/ui/main_window.py`**: `_open_tools` fornece
  `_on_plan_finished`, que formata via bridge, injeta `("reply", …)` na
  fila existente e registra na memória linear.
- **Nenhum** sistema novo de eventos/memória; nenhuma mudança em
  permissões/sandbox/registry/executor/checkpoints/ferramentas.

**Validação (2 ambientes):** 880 testes (875 passam + 5 pulam) no
sandbox E na venv limpa; +8 testes de UI pós-aprovação; pyflakes 0;
pip check ok; import main ok; harness 55/55; AST/anti-futuro verde.

## Lumen 0.7 — Coding Agent

> Status (2026-08-31): 11B (`search_files`), 11C (`edit_file`), 11D
> (`run_pytest` — runner estruturado de build/test), 11E (verificação
> real opt-in), 11F (auto-anexo `run_pytest` após WRITE), 11G
> (evidência real em modo corrections), 11H (toggles persistentes de
> automação + UI), 11I (export de relatório de evidências) e 11J
> (conselho com evidência nas correções — advice-only) entregues.
> Próximos tópicos da trilha (verificação real completa, reparo) —
> **NÃO AUTORIZADOS / NÃO IMPLEMENTADOS**.

- Criar e modificar código; rodar testes; iterar sobre erros.
- Fluxos para projetos de desenvolvimento (git, ambientes, builds).

## Lumen 0.8 — Vision

- Captura de tela e análise por visão computacional.
- Compreensão de janelas, diálogos e estados de aplicações.

## Lumen 0.9 — Mouse + Keyboard

- Controle de mouse e teclado (permissão `COMPUTER_CONTROL`).
- Ações visíveis, limitadas e confirmadas; modo de segurança/kill-switch.

## Lumen 1.0 — Computer Agent

- Autonomia completa com planejamento → execução → verificação.
- Abrir e operar aplicações do dia a dia com checkpoints do usuário.

## Lumen 1.x — Unreal Engine Agent

- Ferramentas específicas para Unreal: criar/abrir projetos, manipular
  Blueprints e assets, disparar builds/cook, ler logs do editor.
- Suporte a fluxos de desenvolvimento de jogos end-to-end.

---

### Princípios valem para todas as fases

1. Permissão antes de poder: sem grant explícito, a ferramenta não roda.
2. Confirmação antes de qualquer ação potencialmente destrutiva.
3. Erros nunca silenciosos: log completo + mensagem clara ao usuário.
4. Testes automatizados acompanham cada incremento.
5. A arquitetura em camadas permanece intocada — só se estende.
