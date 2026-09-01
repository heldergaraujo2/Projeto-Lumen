# LUMEN

**Assistente de IA desktop para Windows** — versão **0.6.8 (Multi-tarefa via chat + Data-flow seguro + Persistência opt-in do Execution State)**.

A Lumen é uma assistente pessoal que, ao final do projeto, será capaz de
receber comandos em linguagem natural e, de forma progressivamente
autônoma, executar tarefas no computador do usuário: manter memória de
projetos, analisar e criar código, executar comandos, enxergar a tela,
controlar mouse e teclado, automatizar aplicações e trabalhar com
desenvolvimento de jogos na **Unreal Engine**.

O projeto evolui em fases (ver [`docs/ROADMAP.md`](docs/ROADMAP.md)).

- **0.1 (Fundação)** ✅ — arquitetura modular completa, UI Tkinter,
  memória local, tarefas, permissões, logging e testes — sem API externa.
- **0.2 (Cérebro Real)** ✅ — provedores de IA reais configuráveis
  (`OpenAIProvider` e `GeminiProvider`) mantendo o modo offline
  (`MockProvider`), persona
  central com system prompt, limite de contexto, timeout, retry limitado,
  streaming de resposta e normalização de respostas (`AIResponse`).
- **0.3 (Memória Avançada — fundação)** ✅ — memória estruturada em 6
  domínios (projetos, tarefas, conhecimento, decisões, erros, soluções)
  com IDs, timestamps, origem, relacionamentos, deduplicação,
  atualização/supersede, marcação de obsoleto, busca por relevância e
  montagem de contexto com cota (`MemorySystem.build_context()`), além de
  redação de segredos antes de persistir. A conversa cotidiana continua
  na memória linear da 0.1; a ligação do novo sistema ao fluxo do Agent
  fica para a próxima etapa.
- **0.3.x (Expansão de providers)** ✅ — dois novos provedores reais:
  **Groq** (`groq`) e **Together AI** (`together`, modelos Llama 4
  reais) — escolhidos após a Meta encerrar a Llama API em 06/07/2026
  (ver abaixo).

- **0.4 (Planner — fundação)** ✅ — o "cérebro" que transforma um pedido
  em um **plano estruturado** (`app/planner/`): objetivo, análise
  prévia e tarefas ordenadas com dependências (`T1…Tn`), estados
  (`PLANNING/READY/BLOCKED/FAILED/COMPLETED`), validação strict de JSON
  (dependências inexistentes e ciclos rejeitados), falha controlada com
  motivo claro, consulta de **leitura** à memória 0.3 e integração via
  `Agent.request_plan()`. **Nenhuma tarefa é executada** — o plano é
  apenas dados; execução fica para as ferramentas de versões futuras.
- **0.4.x (Executor de Planos — fundação)** ✅ — execução controlada e
  determinística de um plano `READY` (`app/executor/`): ordem e
  dependências respeitadas (tarefa só roda com dependências `DONE`),
  avanço tarefa por tarefa (`step()`) ou até o fim (`run_all()`),
  **fail-fast** (falha → restantes `SKIPPED`, plano `FAILED`),
  resultado/erro/tentativas por tarefa (`TaskRun`), relatório imutável
  (`ExecutionReport`) com linha do tempo de eventos e observer no-op
  preparado para integrações futuras. Handler **simulado/in-memory**
  (`SimulatedHandler`) — nenhuma ferramenta real; a costura futura é
  `Planner → Executor → TaskHandler → ToolRegistry → Tools`.
  Integração: `Agent.execute_plan(plan)`.
- **0.4.x (Checkpoints + Retry + Verificação)** ✅ — **checkpoints**:
  `CheckpointPolicy` pausa a execução antes de ações importantes
  (`PENDING_APPROVAL` → `APPROVED`/`REFUSED`; recusa falha o plano de
  forma controlada; sem UI — API interna pronta para a confirmação
  futura do usuário); **retry controlado**: `RetryPolicy` por tarefa
  (limite estrito — nunca infinito; backoff linear injetável; log de
  cada tentativa com resultado/erro em `AttemptRecord`); **verificação
  de resultado**: `TaskVerifier` simulado — `EXECUTOU → VERIFICOU →
  SUCESSO` (`DONE`/`verified=True`) ou `… → FALHOU` (`REJECTED`/
  `verified=False`, fail-fast); **preparação para correção automática**:
  `CorrectionStrategy`/`CorrectionProposal` (abstrações apenas — o
  Executor não as chama; loop `falha → análise → correção → nova
  tentativa → verificação` é futuro). Tudo offline/in-memory.
- **0.5 (Filesystem Tools — fundação segura)** ✅ — primeira camada de
  **ferramentas reais**: 8 ferramentas de arquivo (`list_directory`,
  `read_file`, `write_file`, `create_file`, `delete_file`,
  `file_exists`, `search_files`, `edit_file`) confinadas a um **workspace autorizado explicitamente**
  (`WorkspaceSandbox`: bloqueia `..`, caminhos fora das raízes,
  traversal, symlinks que escapam, escrita em modo somente leitura e
  exclusão sem opt-in duplo), integradas ao `ToolRegistry` (porteio de
  permissões `READ`/`WRITE`) e **auditadas** (toda tentativa registra
  ferramenta/operação/caminhos/desfecho/tarefa/plano — sem conteúdo de
  arquivos). Ponte `ToolTaskHandler` liga o Executor às ferramentas
  (`Planner → Executor → ToolRegistry → Tools`); `ToolCheckpoints`
  pausa antes de operações destrutivas. A 7ª tool — **`search_files`**
  (busca textual READ-only com limites anti-DoS) — entrou na Fase 11B
  e também está no **Planner Catalog** (planejamento automático OK).
  A 8ª tool — **`edit_file`** (**WRITE**) — entrou na Fase 11C: edição
  cirúrgica literal por **ocorrência exatamente 1** (0 ou ≥2 ⇒ erro
  controlado, nada escrito), destrutiva ⇒ **checkpoint antes de
  escrever**; também no Planner Catalog.
  **Somente filesystem** — sem
  terminal, comandos, mouse, teclado, tela ou Unreal.
- **0.5.x (UI de Workspaces, Permissões, Checkpoints e Auditoria)** ✅ —
  tela **🛡 Ferramentas** na janela principal: autorizar/remover
  **workspaces** (`data/workspaces.json`, validados e normalizados; raiz
  de disco rejeitada; modo somente-leitura/escrita/exclusão visível),
  conceder/revogar **permissões** (CHAT/READ/WRITE; DELETE = opt-in por
  workspace; TERMINAL/COMPUTER_CONTROL não concedíveis), **aprovar ou
  recusar** operações destrutivas (card com o quê/onde/ferramenta/
  operação/permissão; recusa garante que nada roda) e ver a
  **auditoria** persistida em JSONL (`data/audit/audit.jsonl` —
  ferramenta/operacao/caminhos/desfecho/erro/timestamp/tarefa/plano,
  sem conteúdo de arquivos). Startup continua sem efeitos colaterais.
- **0.6 (Terminal Tools — fundação controlada)** ✅ — segunda camada de
  ferramentas reais: `run_command` executa comandos **somente da
  allowlist explícita** (`enable_terminal` do integrador; fora da lista
  = bloqueado antes de qualquer execução), com **denylist permanente**
  (shells/interpretadores como `powershell`/`cmd`/`python`, builders,
  escalonamento, destrutivos e **rede** — jamais allowlistáveis, nem
  como `python.exe`/`/bin/sh`), **sem shell** (argv lista; `&&`, `|`,
  `;`, `>`, `-exec`… bloqueados em argumentos), **cwd confinado ao
  workspace** (args absolutos fora e `..` bloqueados), **timeout
  obrigatório** (mata o processo), **limite de saída** (trunca e falha
  honesto), captura de `stdout`/`stderr`/`exit_code`, ambiente filho
  sanitizado (sem segredos), **checkpoint** antes de cada comando
  (argv/permissão/timeout visíveis; recusa ⇒ nada roda; apenas comandos
  viáveis pedem aprovação) e **auditoria JSONL** (comando sanitizado,
  cwd, exit code, desfecho — sem conteúdo). Permissão `TERMINAL` por
  concessão programática; UI intacta; **nada habilitado no startup**.
  Coding agent/vision/mouse/teclado/Unreal continuam inexistentes. A
  2ª tool do terminal — **`run_pytest`** (Fase 11D; permissão
  **TERMINAL**) — roda a suíte pytest do workspace de forma
  **estruturada**: subprocesso controlado (sem shell; `python`/`pytest`
  seguem na denylist do terminal), `path` relativo confinado ao
  sandbox, `-k` restrito, `maxfail` 1..10, `timeout_s` 10..600,
  truncamento marcado; **checkpoint antes de executar** (aprovação
  roda; recusa ⇒ nada roda); registrada no registry e no **Planner
  Catalog** **somente com o terminal habilitado** (mesma condição de
  `run_command`); saída estruturada (`exit_code`, `summary_line`,
  truncamento) **sem vazar output completo na auditoria**. É o
  primeiro runner dedicado de build/test estruturado na trilha Coding
  Agent. Desde a 11E há **verificação real opt-in**:
  `enable_verification("pytest_result")` no `ToolsController` instala o
  `PytestResultVerifier` — que **não executa nada** (apenas interpreta
  o resultado estruturado da task `run_pytest`) — e o desfecho reflete
  em `verified=True/False` da task (default continua sem verificação;
  verificação real completa, ex. pós-escrita/correção, permanece em
  aberto, por spec). Desde a 11F há **auto-anexo de `run_pytest` após
  WRITE** (também opt-in): quando o terminal está habilitado, a
  verificação 11E está habilitada e o plano contém uma operação WRITE
  (`write_file`/`create_file`/`delete_file`/`edit_file`), o
  `ToolsController.run_plan` anexa 1 task final `run_pytest` (depende
  de todas as anteriores; idempotente — não anexa se `run_pytest` já
  estiver no plano) antes de executar; com plano em 12/12 tasks +
  anexo necessário, **falha antes de executar** (nada roda). Default
  continua sem verificação e sem auto-anexo (comportamento atual
  preservado). Desde a 11G, em modo **corrections** o mesmo vale: o
  verifier 11E se aplica (pytest vermelho **rejeita** a task em vez de
  passá-la como `DONE`) e os sucessores `#C` mantêm a evidência
  `run_pytest` no final quando aplicável (regra 11F reutilizada — sem
  duplicar, respeitando o teto de 12 tasks; sem repair-loop
  automático nem auto-replanning). Default continua sem verificação e
  sem auto-anexo. Desde a 11H esses toggles são **persistentes e
  gerenciáveis na UI**: `ToggleStore` em `data/agent_toggles.json`
  (escrita atômica, **fail-closed** — arquivo ausente/corrompido ⇒
  tudo OFF) guarda `corrections_enabled`/`verification_enabled`,
  restaurados no startup do `ToolsController` (`toggles_file`); a
  tela 🛡 ganhou a seção **AUTOMAÇÃO** (ligar/desligar Correções e
  Verificação real; reflete o estado do controller; persiste ao
  clicar). Os toggles persistem **capacidade, não permissão** —
  TERMINAL segue concessão explícita por sessão. Desde a 11I há
  **export opt-in de relatório de evidências**: com
  `LUMEN_EXPORT_EXECUTION_REPORTS=1`, o fim de cada execução em estado
  terminal (COMPLETED/FAILED) gera um JSON **sanitizado** em
  `data_dir/reports/<plan_id_sanitizado>.json` contendo `plan` +
  `execution_report` + `correction_history` + auditoria **filtrada por
  `plan_id`** (best-effort — falha não quebra a execução; **default OFF**
  = bit-a-bit atual; sem execução, sem permissões). Desde a 11J, a
  estratégia **default** de correções (`EvidenceCorrectionStrategy`
  sobre a conservadora) enriquece falhas de `run_pytest` com a
  **evidência real** (`exit_code`/`summary_line`/`timed_out`/
  `truncated`) extraída do JSON do resultado (somente parse — **sem
  execução escondida**): o desfecho é um **conselho advice-only**
  (`corrected_task=None`) — nada é aplicado automaticamente nem pausa a
  execução; o conselho é registrado no ciclo de correção (JSONL) e no
  relatório 11I; sem auto-replanning, e a aprovação continua obrigatória
  para correções com tarefa. Desde a 11K há **snapshot "before" opt-in**
  (default OFF — bit-a-bit): com `enable_snapshots`, cada tool destrutiva
  de filesystem guarda uma cópia do alvo **antes** de executar (depois do
  checkpoint aprovado; best-effort — falha não interrompe), em
  `data_dir/snapshots/<plan>/<task>/` (manifest + backup; auditoria com
  **somente metadados** — nunca conteúdo); a tool `restore_snapshot`
  (WRITE) faz o **rollback manual mínimo** (restaura os bytes originais
  ou desfaz o create; sem terminal/subprocess; checkpoint pré-validado —
  só pausa se viável, senão a task falha direto). Specs:
  `docs/SPEC-11D-BUILD_TEST.md` +
  `docs/SPEC-11E-REAL_VERIFICATION.md` +
  `docs/SPEC-11F-AUTO_PYTEST_AFTER_WRITE.md` +
  `docs/SPEC-11G-CORRECTIONS_EVIDENCE.md` +
  `docs/SPEC-11H-SETTINGS_UI_TOGGLES.md` +
  `docs/SPEC-11I-REPORT_EXPORT.md` +
  `docs/SPEC-11J-EVIDENCE_CORRECTIONS.md` +
  `docs/SPEC-11K-SNAPSHOT_ROLLBACK.md`.
- **0.6.x (UI de Terminal, Allowlist e Concessão TERMINAL)** ✅ — seção
  **TERMINAL** na tela 🛡: ver/conceder/revogar a permissão `TERMINAL`
  por **ação explícita e auditada** (o caminho genérico de permissões
  segue rejeitando TERMINAL; a concessão vale só na sessão — nunca é
  restaurada do disco), gerenciar a **allowlist** (cadastrar comando com
  aprovação obrigatória ou execução direta; remover; desabilitar o
  terminal esvaziando a lista) persistida em `data/terminal.json`
  (atômico; arquivo só nasce no primeiro cadastro; entradas denylistadas
  no arquivo são descartadas — fail closed), e o **card de aprovação**
  agora mostra **comando, argumentos, diretório de trabalho e timeout**
  separadamente. Toda ação administrativa vai para a auditoria JSONL
  (`terminal_grant`/`terminal_revoke`/`allowlist_add`/
  `allowlist_remove`/`terminal_enable`/`terminal_disable`). A UI fala
  **somente** com o `ToolsController`; todas as proteções da 0.6.0
  intactas.
- **0.4.x (Correção Automática Controlada)** ✅ — o ciclo
  **EXECUTAR → VERIFICAR → FALHA → ANALISAR → PROPOR → VALIDAR →
  APROVAR → APLICAR → RETRY → VERIFICAR** (`app/executor/correction.py`,
  genérico e sem importar `app.tools`): `CorrectionEngine` reexecuta o
  plano com um sucessor imutável (`PLN-…#C1`, tarefa corrigida mantém
  id/ordem), com estados explicitamente separados (`PROPOSED`/
  `INVALID`/`REFUSED`/`APPROVED`/`APPLIED`/`RETRIED`/`SUCCEEDED`/
  `FAILED`/`NO_PROPOSAL`/`EXHAUSTED`), **limites rígidos**
  (`max_cycles`, `max_total_attempts` — nunca retry infinito) e plano
  original **intocado**. Na camada de tools (`app/tools/correction.py`),
  `ToolCorrectionStrategy` (conservadora: só propõe `create_file →
  write_file` quando o arquivo já existe; erros de permissão/sandbox
  **nunca** geram proposta) + validador que exige tool registrada,
  permissão concedida e sandbox/terminal policy aprovando — **sem
  bypass**. Opt-in no `ToolsController` (`enable_corrections`/
  `disable_corrections`), checkpoint de correção na UI (card
  "CORREÇÃO PROPOSTA" com de→para) e auditoria JSONL de todo ciclo
  (`tool=correction`).
- **0.6.3 (Tool Calling / Planner Bridge)** ✅ — a ponte que faltava:
  **CHAT → INTENÇÃO → PLANNER → PLANO (`tool`/`parameters`) →
  VALIDAÇÃO → TOOLS CONTROLLER → PERMISSÕES → WORKSPACE → CHECKPOINT →
  EXECUÇÃO → VERIFICAÇÃO** (`app/core/bridge.py` + `app/planner/catalog.py`).
  O chat agora distingue conversa × ação **via provedor** (protocolo
  estruturado; o Planner ganha um catálogo-allowlist com as ferramentas
  **já existentes** — 6 de filesystem e `run_command` só com terminal
  habilitado). O LLM não pode inventar ferramentas/parâmetros (validação
  de protocolo rejeita tudo fora da allowlist, incluindo paths
  absolutos/`..`); **LLM não é autorização** — permissões, workspace,
  checkpoints e auditoria seguem como autoridade final, intocados.
  MockProvider determinístico planeja `create_file` para o pedido
  canônico "Crie um arquivo chamado X contendo: Y" (offline). Novos
  estados de ciclo (`CONVERSATIONAL`…`REJECTED`); card de aprovação
  mostra o **conteúdo** a gravar.

---

## Objetivo da versão 0.4 — Planner (fundação)

Criar a camada que entende um pedido do usuário e produz um plano de
execução estruturado — dividindo o objetivo em etapas, definindo
dependências e identificando o que precisa ser analisado antes —
**sem executar nada**: sem comandos, arquivos, terminal, mouse, teclado
ou Unreal. O Planner é provider-agnóstico (funciona com qualquer um dos
5 provedores) e consulta a memória 0.3 somente como leitura. Planos
inválidos ou impossíveis de interpretar falham de forma controlada com
o motivo claro. Exemplo: *"Lumen, crie um sistema de evolução de níveis
com recompensa em pontos"* → plano com etapas (entender requisitos →
analisar estrutura → definir dados → implementar → recompensas →
compilar/testar depois), todas apenas **planejadas**.

### O que a 0.4 NÃO faz (de propósito)

- ❌ **Não executa** nenhuma tarefa do plano (sem filesystem, terminal,
  mouse, teclado, visão, Unreal, tool calling real, loops de execução).
- ❌ Sem checkpoints/confirmação de execução e sem UI de planos (futuro).
- ❌ O chat normal (`send_message`) segue exatamente como na 0.3.1.

---

## Objetivo da versão 0.3

Dar à Lumen uma **memória inteligente e persistente** — a fundação que as
futuras versões de agente usarão para recordar projetos, decisões,
soluções e erros ("esse sistema já foi criado anteriormente?") — com
persistência local segura, **sem salvar a conversa indiscriminadamente**
e **sem que segredos jamais entrem na memória**. Nenhuma capacidade de
agente foi adicionada.

### O que a 0.3 NÃO faz (de propósito)

- ❌ Nenhum acesso ao computador: sem arquivos, terminal, execução de
  código, mouse, teclado, tela ou aplicações.
- ❌ Sem Planner, tool calling real, vision ou Unreal.
- ❌ O Agent ainda não consulta a memória estruturada ao responder
  (o gancho `build_context()` existe e será integrado adiante).
- ❌ Sem sumarização de conversas, busca semântica (embeddings),
  múltiplas sessões ou migração para SQLite (futuras 0.3.x).

A Lumen 0.3 **apenas conversa** — agora guardando conhecimento de forma
estruturada e consultável.

### Complemento 0.3.x — Expansão de providers (Groq + Together AI) ✅

Dois provedores reais independentes, no mesmo sistema de cofre, tela ⚙,
TESTAR CONEXÃO, timeout/retry e troca em runtime dos anteriores:

- **Groq** (`LUMEN_PROVIDER=groq`, SDK oficial `groq`) — modelo padrão
  `openai/gpt-oss-120b` (destaque de produção: 131k de contexto,
  raciocínio e tool calling). Também serve os Llama `llama-3.3-70b-versatile`
  e `llama-3.1-8b-instant`.
- **Together AI** (`LUMEN_PROVIDER=together`, SDK oficial `together`) —
  **Llama 4 real**: padrão `meta-llama/Llama-4-Scout-17B-16E-Instruct`
  (109B/17B ativos, function calling, foco em raciocínio sobre codebase);
  alternativa `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8`
  (flagship 400B/17B ativos).

**Por que Together para o Llama**: a Meta encerrou o *Llama API Public
Preview* em **06/07/2026** (a API hoje devolve apenas uma resposta de
encerramento) e a Cerebras removeu todos os Llama do catálogo público
entre 10/2025 e 05/2026 — a Together AI é o host que mantém o Llama 4 em
API pública. Decisão registrada em `LUMEN_STATE.md` e
`docs/ARCHITECTURE.md` §3.7.

Nos dois, o modelo é **opcional** (vazio usa o padrão documentado) e
continua configurável pelo usuário. A sonda TESTAR CONEXÃO não limita
`max_tokens` (modelos com raciocínio podem consumir o orçamento mínimo
pensando e devolver vazio, gerando falso negativo).

### Histórico — objetivo da 0.2

Transformar a Lumen de um chatbot simulado em uma assistente capaz de
usar um **modelo de IA real através de um provedor configurável**
(`mock` offline, `openai` ou `gemini`), com persona, contexto, erros,
timeout/retry, streaming e resposta normalizada — **sem** nenhuma
capacidade de agente. Entregue e verificada (ver `LUMEN_STATE.md`).

---

## Requisitos

- **Python 3.11+** (testado com 3.13).
- **Windows 10/11** (alvo). A camada não-UI roda em Linux/macOS para
  desenvolvimento; a interface requer Tkinter (acompanha o instalador
  oficial do Python no Windows).
- `openai` (SDK oficial — só com `LUMEN_PROVIDER=openai`), `google-genai`
  (SDK oficial do Gemini — só com `LUMEN_PROVIDER=gemini`), `groq` (só
  com `LUMEN_PROVIDER=groq`), `together` (só com
  `LUMEN_PROVIDER=together`), `keyring`
  (cofre de credenciais do SO) e `pytest` (testes), todos em
  `requirements.txt`. O modo mock funciona sem nenhum SDK de provider
  nem `keyring`.

## Instalação (Windows 10/11)

Abra o **PowerShell** (ou o Prompt de Comando) na pasta do projeto:

```powershell
cd Lumen
py -m venv .venv
```

Ative o ambiente virtual:

```powershell
# PowerShell
.\.venv\Scripts\Activate.ps1
# Se o PowerShell bloquear scripts, rode UMA vez no terminal atual:
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

```bat
:: Prompt de Comando (cmd)
.venv\Scripts\activate.bat
```

Instale as dependências e (opcional) crie o `.env`:

```powershell
pip install -r requirements.txt
copy .env.example .env
```

> O `.env` é **opcional** para uso normal: a tela **⚙ Configurações**
> cuida de provider/modelo/API Key. O `.env` segue útil para
> desenvolvimento (precedência: configuração gráfica > ambiente > `.env`).

> Em Linux/macOS (desenvolvimento): `python3 -m venv .venv && source
> .venv/bin/activate` e `cp .env.example .env`.

## Primeiro uso no Windows (passo a passo)

1. Com o venv ativado, execute `python main.py` — a janela **LUMEN** abre.
2. Clique em **⚙ Configurações** (canto superior direito).
3. Em **Provedor**, escolha `openai`, `gemini`, `groq` ou `together`
   (ou deixe `mock` para
   testar offline).
4. Em **Modelo**, informe o modelo (ex.: `gpt-4o-mini` para openai;
   `gemini-2.5-flash` para gemini — no gemini/groq/together, vazio usa o
   padrão do provedor: `gemini-2.5-flash` · `openai/gpt-oss-120b` ·
   `meta-llama/Llama-4-Scout-17B-16E-Instruct`).
5. Em **API Key**, digite sua chave (fica oculta com `•••`; 👁 mostra/
   oculta temporariamente).
6. Clique em **TESTAR CONEXÃO** — deve aparecer `🟢 Conexão estabelecida`.
7. Clique em **SALVAR** — a configuração é aplicada na hora, sem
   reiniciar; o cabeçalho da janela passa a mostrar o novo provedor.
8. Escreva uma mensagem e converse com a Lumen usando a IA real.
9. Feche e reabra a Lumen quando quiser: provedor, modelo e chave são
   recuperados (a chave permanece no cofre e **nunca** é exibida).

## Execução

### Modo simulado (default — sem API key, sem internet)

```powershell
python main.py
```

```text
Você:  Olá Lumen
Lumen: Olá! Eu sou a Lumen. Como posso ajudar?
```

### Modo IA real (OpenAI, Google Gemini, Groq ou Together AI)

Edite o `.env` **ou** use a tela **⚙ Configurações** (ver abaixo):

```ini
# OpenAI
LUMEN_PROVIDER=openai
LUMEN_MODEL=gpt-4o-mini        # obrigatório neste modo
LUMEN_API_KEY=sk-...           # sua chave; NUNCA versione este arquivo
```

```ini
# Google Gemini (chave gerada no Google AI Studio: aistudio.google.com)
LUMEN_PROVIDER=gemini
LUMEN_MODEL=                   # vazio usa o padrão gemini-2.5-flash
LUMEN_API_KEY=AIza...          # sua chave; NUNCA versione este arquivo
```

```ini
# Groq (chave gerada em console.groq.com/keys)
LUMEN_PROVIDER=groq
LUMEN_MODEL=                   # vazio usa o padrão openai/gpt-oss-120b
LUMEN_API_KEY=gsk_...          # sua chave; NUNCA versione este arquivo
```

```ini
# Together AI — Llama 4 real (chave gerada em api.together.ai)
LUMEN_PROVIDER=together
LUMEN_MODEL=                   # vazio usa o padrão meta-llama/Llama-4-Scout-17B-16E-Instruct
LUMEN_API_KEY=tgp_...          # sua chave; NUNCA versione este arquivo
```

Depois rode `python main.py`.

Se faltar a chave ou o modelo, a Lumen falha na inicialização com uma
mensagem explicando exatamente como configurar (e o modo `mock` continua
disponível para trabalhar offline).

A resposta chega **progressivamente** (streaming) na área de conversa; o
cabeçalho mostra provedor/modelo ativos e o status (● Pronta /
● Pensando… / ● Erro) durante a troca.

## Configuração gráfica (⚙ Configurações → Inteligência Artificial)

Na janela principal, o botão **"⚙ Configurações"** abre a tela de
configuração de IA — sem precisar editar o `.env`:

- **Provedor** — `mock` (offline), `openai`, `gemini`, `groq` ou `together`.
- **Modelo** — ex.: `gpt-4o-mini` (obrigatório para `openai`);
  `gemini-2.5-flash`, `openai/gpt-oss-120b` (groq) ou
  `meta-llama/Llama-4-Scout-17B-16E-Instruct` (together) — nos quatro
  providers reais exceto openai, vazio usa o padrão do provedor.
- **API Key** — digitada com `•••` (o botão 👁 mostra/oculta
  temporariamente durante a edição). A chave salva **nunca** é exibida
  de novo; o campo começa vazio e "em branco" significa "manter a chave
  atual".
- **TESTAR CONEXÃO** — faz uma requisição mínima (`max_tokens=1`) com o
  provider/modelo/chave indicados e mostra `🟢 Conexão estabelecida`,
  `🟢 MockProvider funcionando` (offline) ou `🔴 …` com mensagem amigável
  (chave inválida, modelo inválido, timeout, rede, rate limit,
  dependência ausente). Detalhes técnicos ficam no log, sem segredos.
- **SALVAR** — valida, persiste e **aplica imediatamente**: a próxima
  mensagem já usa o novo provider/modelo, sem reiniciar a Lumen.
- **Remover chave salva** — apaga a credencial do cofre (com confirmação).

### Onde a API Key é guardada

- **Windows:** no **Windows Credential Manager** (via pacote `keyring`,
  instalado com `pip install -r requirements.txt`).
- **Fallback** (Linux/macOS sem cofre disponível): arquivo restrito
  `data/.credentials.json` (permissão 0600, escrita atômica, fora do
  Git). Menos seguro que o cofre do SO — documentado como fallback de
  desenvolvimento.

A chave nunca vai para código, Git, README, logs, `data/settings.json`
ou o payload enviado ao modelo.

### Configuração gráfica × `.env` (precedência)

| Prioridade | Fonte |
| ---------- | ----- |
| 1ª | Configuração salva pela tela **⚙ Configurações** (`data/settings.json` + cofre) |
| 2ª | Variáveis de ambiente reais (`LUMEN_*`) |
| 3ª | Arquivo `.env` (desenvolvimento) |
| 4ª | Padrões internos |

A API Key segue a mesma ordem: **cofre → `.env`**. Remover a chave do
cofre faz o sistema cair de volta para a chave do `.env` (se existir).
Para voltar ao `mock`, basta escolher o provedor "mock" e salvar.

## Testes

```powershell
python -m pytest -v
```

1000 testes, todos offline — **995 passed / 5 skipped / 0 failed**.
Os 5 skips são ambientais: introspecção dos SDKs
`google-genai`/`groq`/`together` e do `keyring` quando ausentes, e o
smoke test da UI Tk em ambientes sem display (no Windows ele roda). As chamadas aos provedores (OpenAI, Gemini, Groq,
Together), o cofre de credenciais, a memória estruturada e as
**ferramentas de filesystem** usam fakes/diretórios temporários;
nenhum teste toca API real nem arquivos fora de `tmp`.

## Configuração (`.env`)

| Variável | Padrão | Descrição |
| -------- | ------ | --------- |
| `LUMEN_PROVIDER` | `mock` | `mock` (offline), `openai`, `gemini`, `groq` ou `together` (APIs reais). |
| `LUMEN_MODEL` | vazio | Modelo a usar (obrigatório com `openai`; nos demais, vazio usa o padrão do provedor — ver tabela abaixo). |
| `LUMEN_API_KEY` | vazio | Chave de API (obrigatória com qualquer provider real). Nunca versione. |
| `LUMEN_DATA_DIR` | `data` | Diretório de dados (memória, tarefas, logs). |
| `LUMEN_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `LUMEN_MAX_CONTEXT_MESSAGES` | `50` | Máximo de mensagens de histórico enviadas ao modelo. |
| `LUMEN_REQUEST_TIMEOUT` | `60` | Timeout (segundos) por chamada ao provedor. |
| `LUMEN_MAX_RETRIES` | `2` | Retries extras para erros temporários (rate limit, timeout, rede, 5xx). |
| `LUMEN_MAX_MEMORY_RECORDS` | `12` | Máximo de registros da memória estruturada selecionados como contexto para um pedido (0.3). |

**Modelos por provedor** (padrões fundamentados na documentação oficial
de cada API em 2026-08; configuráveis pelo usuário):

| Provedor | Padrão (modelo vazio) | Alternativas documentadas |
| -------- | --------------------- | ------------------------- |
| `openai` | — (obrigatório) | `gpt-4o-mini`, `gpt-4o`, … |
| `gemini` | `gemini-2.5-flash` | `gemini-2.5-pro`, … |
| `groq` | `openai/gpt-oss-120b` | `openai/gpt-oss-20b`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant` |
| `together` | `meta-llama/Llama-4-Scout-17B-16E-Instruct` | `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8`, Llama 3.3 do catálogo Together |

**Nunca coloque chaves reais no `.env` versionado** — ele está no
`.gitignore`. Os logs aplicam redação automática de segredos e **nunca**
registram API keys nem o conteúdo das conversas.

---

## Estrutura do projeto

```text
Lumen/
├── main.py                  # ponto de entrada (composition root)
├── LUMEN_STATE.md           # estado oficial do projeto
├── README.md
├── requirements.txt         # openai (provider real) + pytest (dev)
├── .env.example
├── .gitignore
│
├── app/
│   ├── __init__.py          # APP_NAME, __version__ = 0.4.0
│   ├── ai/                  # AI PROVIDER
│   │   ├── provider.py      #   AIProvider (ABC), chat()/generate(),
│   │   │                    #   taxonomia de erros, fábrica create_provider()
│   │   ├── openai_provider.py  # OpenAIProvider (SDK oficial, lazy import)
│   │   ├── gemini_provider.py  # GeminiProvider (SDK oficial google-genai, lazy)
│   │   ├── groq_provider.py    # GroqProvider (SDK oficial groq; herda o
│   │   │                       #   núcleo testado do OpenAIProvider — 0.3.x)
│   │   ├── together_provider.py # TogetherProvider (SDK oficial together;
│   │   │                       #   Llama 4 real — 0.3.x)
│   │   ├── mock.py          #   MockProvider (modo simulado, offline)
│   │   └── types.py         #   AIResponse, Usage, ResponseType (FINAL_RESPONSE|
│   │                        #   TOOL_CALL|PLAN — preparação para agente)
│   ├── config/              # CONFIGURAÇÃO
│   │   ├── settings.py      #   Settings (.env próprio) + setup_logging()
│   │   ├── persona.py       #   identidade central + system prompt da Lumen
│   │   ├── user_config.py   #   configuração salva pela UI + precedência
│   │   ├── secrets.py       #   cofre de credenciais (keyring/arquivo)
│   │   └── config_service.py#   ConfigService: salva/aplica/testa conexão
│   ├── core/                # AGENT CORE
│   │   └── agent.py         #   Agent.send_message(): permissão → contexto →
│   │   │                    #   provedor (com system prompt/streaming) → memória
│   │   │                    #   Agent.request_plan(): pedido → Planner (0.4)
│   ├── planner/             # PLANNER (0.4 — fundação)
│   │   ├── models.py        #   Plan/PlannedTask + PlanStatus (dados apenas)
│   │   └── planner.py       #   Planner.create_plan(): prompt JSON strict →
│   │                        #   validação (deps/ciclos) → plano READY/FAILED/
│   │                        #   BLOCKED; memória 0.3 como leitura opcional
│   ├── executor/            # EXECUTOR (0.4.x)
│   │   ├── handlers.py      #   TaskHandler (ABC) + SimulatedHandler
│   │   │                    #   (in-memory; futura costura c/ ToolRegistry)
│   │   ├── checkpoints.py   #   CheckpointPolicy/Request/Status (pausa
│   │   │                    #   antes de ações; aprovação/recusa)
│   │   ├── retry.py         #   RetryPolicy (limite estrito) + AttemptRecord
│   │   ├── verification.py  #   TaskVerifier + SimulatedVerifier
│   │   ├── correction.py    #   abstrações p/ correção futura (não ligadas)
│   │   └── executor.py      #   PlanExecutor: step()/run_all(), dependências,
│   │                        #   fail-fast, TaskRun/ExecutionReport/eventos
│   ├── memory/              # MEMORY (0.3 — memória inteligente)
│   │   ├── store.py         #   MemoryStore + Message (conversa, JSON local)
│   │   ├── sanitization.py  #   redact_secrets/contains_secret — segredos
│   │   │                    #   nunca entram na memória estruturada
│   │   ├── records.py       #   MemoryRecord, MemoryKind (PROJECT|TASK|
│   │   │                    #   KNOWLEDGE|DECISION|ISSUE|SOLUTION), status,
│   │   │                    #   hashes e IDs por domínio
│   │   ├── record_store.py  #   RecordStore — persistência por domínio
│   │   │                    #   (atômica, thread-safe), dedup, obsoletos,
│   │   │                    #   supersede e busca por relevância
│   │   └── system.py        #   MemorySystem — fachada dos 6 domínios +
│   │                        #   conversa; recall() e build_context()
│   ├── tasks/               # TASK SYSTEM
│   │   └── manager.py       #   TaskManager, Task, TaskStatus
│   ├── tools/               # TOOLS (0.5/0.5.x — filesystem confinado + auditado)
│   │   ├── base.py          #   Tool (ABC) + ToolResult/StructuredTool +
│   │   │                    #   ToolRegistry (porteiro de permissões)
│   │   ├── filesystem.py    #   WorkspaceSandbox (política de raízes
│   │   │                    #   autorizadas) + FilesystemAudit + 6 tools
│   │   │                    #   (list/read/write/create/delete/exists)
│   │   ├── handler.py       #   ToolTaskHandler (Executor↔Tools) +
│   │   │                    #   ToolCheckpoints (destrutivas p/ checkpoint)
│   │   ├── workspaces.py    #   WorkspaceStore (autorizações persistidas)
│   │   │                    #   + MultiWorkspaceSandbox (política por raiz)
│   │   ├── audit_log.py     #   auditoria JSONL (sink + leitor)
│   │   ├── control.py       #   ToolsController (fachada da UI) +
│   │   │                    #   PrevalidatedCheckpoints + administração
│   │   │                    #   de terminal (grant/allowlist) (0.6.x)
│   │   ├── terminal.py      #   TERMINAL (0.6): TerminalPolicy
│   │   │                    #   (allowlist+denylist+timeout+limites)
│   │   │                    #   + run_command — subprocess controlado +
│   │   │                    #   TerminalStore (persistência 0.6.x)
│   │   └── run_pytest.py    #   RUN_PYTEST (11D): runner estruturado do
│   │                        #   pytest do workspace (sem shell, sandbox,
│   │                        #   timeout, checkpoint antes de executar)
│   ├── security/            # PERMISSIONS
│   │   └── permissions.py   #   PermissionManager, PermissionLevel
│   └── ui/                  # UI (Tkinter)
│       ├── main_window.py   #   LumenWindow (streaming, status, erros amigáveis,
│       │                    #   ⚙ Configurações + 🛡 Ferramentas)
│       ├── settings_dialog.py # ⚙ Configurações → Inteligência Artificial
│       └── tools_dialog.py  #   🛡 Ferramentas e Segurança (0.5.x)
│
├── data/
│   ├── memory/              # conversation.json + 6 arquivos de domínio
│   │                        # (projects, task_records, knowledge, decisions,
│   │                        #  issues, solutions .json — criados no 1º uso)
│   └── logs/                # lumen.log (runtime)
│
├── tests/                   # 1000 testes pytest (995 passed + 5 skipped; todos offline)
├── tools_dev/               # verificação headless da UI (55 checks)
└── docs/
    ├── ARCHITECTURE.md      # detalhes da arquitetura
    └── ROADMAP.md           # versões futuras
```

Detalhes de camadas, fluxo de mensagens, erros e guias de extensão:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Estado oficial do
projeto: [`LUMEN_STATE.md`](LUMEN_STATE.md).

## Roadmap (resumo)

| Versão | Foco | Status |
| ------ | ---- | ------ |
| 0.1    | Fundação | ✅ |
| 0.2    | IA real (provedor configurável) | ✅ |
| 0.3    | Memória avançada (fundação) | ✅ |
| 0.3.x  | Expansão de providers (Groq + Together) | ✅ |
| 0.4    | Planner (fundação) | ✅ |
| 0.4.x  | Executor de planos (fundação, simulado) | ✅ |
| 0.4.x  | Checkpoints + retry + verificação (simulado) | ✅ |
| 0.5    | Filesystem Tools (workspace + auditoria) | ✅ |
| 0.5.x  | UI de Workspaces, Permissões, Checkpoints e Auditoria | ✅ |
| 0.6    | Terminal Tools (allowlist + timeout + auditoria) | ✅ |
| 0.6.x  | UI de Terminal (allowlist + concessão TERMINAL) | ✅ |
| 0.4.x  | Correção automática controlada (0.6.2) | ✅ |
| 0.6.3  | Tool Calling / Planner Bridge (chat → plano → ferramenta) | ✅ |
| 0.6.6  | Desfecho pós-aprovação exibido no chat (callback da tela 🛡) | ✅ |
| 0.6.7  | Planos multi-tarefa via chat + data-flow `${Tn.data.campo}` (Fases 7/8B) | ✅ |
| 0.6.8  | Persistência opt-in do Execution State — bundles sanitizados em `data/executions` (Fase 9B) | ✅ |
| 0.7    | Coding Agent | ⏳ |
| 0.8    | Vision | ⏳ |
| 0.9    | Mouse + Keyboard | ⏳ |
| 1.0    | Computer Agent | ⏳ |
| 1.x    | Unreal Engine Agent | ⏳ |

Roadmap completo: [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## Segurança

- Por padrão a Lumen possui apenas a permissão `CHAT`.
- **Ferramentas de filesystem (0.5)**: existem, mas **nunca rodam por
  si só** — precisam de (1) registro explícito com um
  `WorkspaceSandbox` cujas **raízes foram autorizadas por quem
  integra**, (2) concessão das permissões `READ`/`WRITE` e (3) política
  que habilite escrita (`writable`) e exclusão (`allow_delete` — opt-in
  duplo). Todo caminho é validado (sem `..`, sem sair das raízes,
  symlinks resolvidos) e toda tentativa é **auditada** (sem conteúdo de
  arquivos). Não existe acesso irrestrito ao Windows.
- **Terminal (0.6)**: existe, mas **não é acesso irrestrito** —
  allowlist explícita do integrador (fora da lista = bloqueado antes de
  executar), denylist permanente (shells/interpretadores/builders/
  escalonamento/destrutivos/rede jamais allowlistáveis, nem como
  `python.exe` ou `/bin/sh`), execução **sem shell** (argv lista;
  operadores e redirecionamentos bloqueados em argumentos), cwd
  confinado aos workspaces, timeout obrigatório, limite de saída,
  ambiente filho sem segredos, checkpoint por comando (recusa ⇒ nada
  roda) e auditoria sem conteúdo. Desde a 0.6.x a tela 🛡 concede/revoga
  `TERMINAL` por **ação explícita dedicada e auditada** (o caminho
  genérico de permissões segue rejeitando TERMINAL; COMPUTER_CONTROL
  permanece inconcedível por qualquer via; a concessão **não persiste**
  entre sessões) e a allowlist é gerenciada pela UI e persistida em
  `data/terminal.json` (fail closed: arquivo ilegível ou entrada
  denylistada ⇒ terminal desabilitado/entrada descartada).
- Nenhuma outra ferramenta sensível existe — nem código para mouse,
  teclado, captura de tela, visão, computer control, Unreal ou rede das
  ferramentas (0.7+; `subprocess` existe somente em
  `app/tools/terminal.py` e `app/tools/run_pytest.py`, ambos
  controlados, garantido por testes AST).
- **Controle humano pela UI (0.5.x)**: workspaces, permissões
  `READ`/`WRITE` e aprovação de operações destrutivas partem **do
  usuário**, na tela 🛡 — a UI **rejeita** conceder níveis futuros
  (`TERMINAL`/`COMPUTER_CONTROL`), workspaces são validados/normalizados
  (raiz de disco nunca aceita), a recusa de um checkpoint **garante que
  nada roda** e a auditoria persistida em JSONL nunca contém conteúdo de
  arquivos.
- O Planner (0.4) **apenas produz planos (dados)** — nenhuma tarefa é
  executada automaticamente; a memória estruturada é consultada por ele
  somente como leitura.
- A API Key vive apenas no `.env` local (fora do versionamento); nunca é
  registrada em log (com redação automática adicional) nem embutida em
  código.
- A memória é **100% local** (JSON em `data/memory/`): o banco de memória
  nunca é enviado a provedores — apenas o contexto selecionado pelo
  futuro fluxo do Agent será. Segredos (API keys, tokens, senhas) são
  **redigidos antes de persistir** em qualquer domínio da memória
  estruturada.
- Logs registram somente metadados (tamanhos, tipos de erro) — nunca o
  conteúdo das mensagens do usuário.
