# Spec 11H — Settings/UI para toggles do ToolsController (persistência + exposição)

**Status:** **IMPLEMENTADA + TESTADA (entregue em 2026-08-31).**
(O status original DRAFT é preservado no Histórico do documento, abaixo.)

**Escopo:** definir como **persistir** e **expor na UI** (Tkinter) os toggles de
capacidade do ToolsController: **Correções** (0.6.x) e **Verificação real**
(11E), além do comportamento **11F** (auto-append de `run_pytest` após WRITE).

**Fora do escopo (MVP):** conceder permissões pela UI de toggles; novo
verifier além de `"pytest_result"`; opt-out explícito do 11F (TBD, §8);
migrar provider/model da `ConfigService` (outro eixo de configuração).

> Baseline da suíte na data do DRAFT: **982 passed / 5 skipped / 0 failed**
> (987 coletados) — baseline pós-11G (commit `0ee79e5`).

---

## 1. Status

- **IMPLEMENTADA + TESTADA (entregue em 2026-08-31)** — MVP implementado
  como decidido neste DRAFT: `ToggleStore` + wiring do `ToolsController`
  + seção "Automação" do `ToolsDialog` + `toggles_file` no `main.py`
  (ver "Evidências (implementação e testes)" abaixo).
- Pré-requisitos entregues: 11D (`run_pytest`), 11E (verificação real),
  11F (auto-append), 11G (corrections + evidência) — todos commitados.
- Pontos abertos restantes (evoluções futuras) em §8; o status DRAFT
  original fica preservado no Histórico.

## 2. Evidência do estado atual (mapeamento — COMANDO 055 1/3)

- **`app/config/user_config.py :: UserConfigStore`** — `data/settings.json`,
  `_ALLOWED_KEYS = ("provider", "model")`, contrato `dict[str, str]`.
  **Limitado a provider/model** (string): não comporta toggles booleanos de
  tools sem violar o contrato nem a responsabilidade da `ConfigService`
  (provider/secrets/Agent). **Não será estendida** para este fim.
- **`app/ui/settings_dialog.py :: SettingsDialog`** — o único padrão de
  configuração persistente na UI hoje (provider/model/key), via
  `ConfigService.save()` (valida → persiste → aplica sem reiniciar).
- **`app/ui/tools_dialog.py :: ToolsDialog`** — já controla: aprovações
  (pendentes), workspaces (persistidos em `data/workspaces.json`),
  permissões CHAT/READ/WRITE (**somente sessão**), TERMINAL (permissão
  **somente sessão**; allowlist persistida em `data/terminal.json`, lida no
  startup **fail-closed** por `ToolsController._load_terminal`).
- **Correções (0.6.x) e Verificação (11E)** — opt-ins programáticos
  (`enable_corrections` / `enable_verification("pytest_result")`), com
  propriedades `corrections_enabled` / `verification_enabled` — **sem UI e
  sem persistência** (reinicia ⇒ volta OFF).
- **11F (auto-append)** — **não tem toggle próprio**: derivado por
  construção (terminal habilitado + verification ON + WRITE + guardrails de
  tamanho/íntegra).
- **Fluxo de criação (`main.py::main`)**: `Settings.load()` →
  `build_app(settings)` → `tk_root()` → `ToolsController(agent.permissions,
  workspaces_file=…, audit_file=…, terminal_file=…)` →
  `agent.set_tools_controller(controller)` → `LumenWindow(root, agent,
  config_service=…, tools_controller=…)`.

## 3. Princípios de segurança (normativo)

1. **Toggles persistentes NUNCA concedem permissões.** Persistir um toggle
   reativa *capacidade* (corrections/verification); **não** concede
   TERMINAL nem qualquer outro level do `PermissionManager`. A permissão
   TERMINAL segue a regra 0.6.x: concessão explícita por sessão, **nunca
   restaurada** no startup.
2. **Fail-closed obrigatório.** Arquivo de toggles ausente ⇒ tudo OFF
   (comportamento de hoje, inalterado). Arquivo **corrompido/inválido ⇒
   tudo OFF + erro registrado** — nunca habilitar "por otimismo" (mesmo
   padrão de `_load_terminal`).
3. **A UI só altera capacidade/config, não permissões.** A seção nova do
   `ToolsDialog` (Automação) é vizinha, porém **independente**, da seção
   TERMINAL: clicar nela nunca altera `terminal_status()["permission_granted"]`
   nem a allowlist.
4. **Sem efeitos colaterais no load.** Ler o arquivo de toggles não cria
   diretórios, não grava nada e não audita nada (auditoria só na escrita).
5. **Bit-a-bit no default:** com arquivo ausente, o comportamento do app é
   idêntico ao atual (corrections OFF, verification OFF, 11F derivado como
   hoje).

## 4. Proposta de persistência

- **Novo arquivo:** `data/agent_toggles.json` (nome sujeito a ajuste fino;
  padrão de localização igual a `terminal.json`/`workspaces.json`).
- **Store:** nova classe `ToggleStore` (ou equivalente) em `app/tools/`,
  espelhando `TerminalStore`: `load()`/`save()` **atômico** (tmp +
  `os.replace`), **schema versionado simples** (`{"version": 1, "toggles":
  {...}}`), `ToggleStoreError` para arquivo ilegível/inválido.
- **Chaves do MVP:**
  - `corrections_enabled: bool` (default `false`)
  - `verification_enabled: bool` (default `false`; quando ON, usa o
    verifier `"pytest_result"` — único do escopo)
- **Auto-append 11F:**
  - **default: derivado** (terminal habilitado + `verification_enabled` +
    WRITE) — comportamento atual, mantido;
  - **decisão do MVP (recomendada e adotada neste DRAFT): SEM flag própria**
    para o 11F — um 4º toggle criaria divergência de estado (ex.: 11E ON com
    anexo OFF contradiz o MVP 11F);
  - **opcional futuro (TBD, §8):** `auto_pytest_after_write_optout: bool`
    como opt-out explícito persistido no mesmo arquivo.
- **Métodos no `ToolsController` (proposta):**
  - construtor: novo parâmetro opcional `toggles_file: Path | None = None`
    (`None` ⇒ sem persistência, bit-a-bit atual; testes atuais não mudam);
  - `_load_toggles()` no `__init__` (fail-closed, sem efeitos colaterais);
  - `set_corrections_enabled(bool)` / `set_verification_enabled(bool)` —
    aplicam na hora (`enable_corrections()`/`enable_verification()` ou
    `disable_*`) **e persistem** + registram auditoria admin;
  - propriedades de leitura já existem: `corrections_enabled`,
    `verification_enabled` (a UI só as reflete).

## 5. Aplicação no startup

1. `main.py` cria o controller com o arquivo:
   `ToolsController(…, toggles_file=settings.data_dir / "agent_toggles.json")`.
2. **Após a criação do controller** (e antes de
   `agent.set_tools_controller`), o `__init__` do controller já aplicou os
   toggles persistidos: `corrections_enabled` ⇒ `enable_corrections()`;
   `verification_enabled` ⇒ `enable_verification("pytest_result")`.
   (Aplicação no `__init__` = mesmo padrão de `_load_terminal`; `main.py`
   não precisa de bloco extra.)
3. **Terminal: a permissão continua por sessão** — o arquivo de toggles
   NUNCA restaura `TERMINAL`; apenas a allowlist já é restaurada hoje via
   `terminal.json` (fail-closed), sem mudança.
4. Ordem garantida: toggles aplicados **antes** de qualquer `run_plan`
   possível (startup), e antes da UI existir.

## 6. UI (ToolsDialog — seção "Automação")

- Nova seção **"AUTOMAÇÃO (11H)"** no `ToolsDialog`, entre as seções
  existentes (padrão visual das demais: header + label explicativo +
  controles + status).
- **2 checkboxes:**
  - **Correções automáticas** (0.6.x) — reflete
    `controller.corrections_enabled`;
  - **Verificação real** (11E) — reflete `controller.verification_enabled`.
- Ao clicar: chamar o setter do controller (§4), que aplica + persiste;
  mensagem de status no estilo das seções atuais (ex.: "🟢 Verificação real
  habilitada (pytest_result). Alteração persistida.") e `refresh()` do
  estado.
- **Reflexo imediato:** o estado refletido vem do controller (fonte única);
  nenhum checkbox guarda estado próprio além do instante do clique.
- A seção **não** expõe permissão TERMINAL, allowlist nem opt-out do 11F
  (TBD).
- `LumenWindow`/`main.py`: sem mudança além do `toggles_file` no
  construtor do controller — `ToolsDialog` já recebe o controller.

## 7. Plano de testes (quando implementada)

- **Persistência:** salvar toggle ⇒ arquivo escrito com `version: 1`; nova
  instância de `ToolsController` no mesmo arquivo ⇒ toggle aplicado
  (padrão dos testes de persistência do terminal/workspaces).
- **Fail-closed:** arquivo corrompido (JSON inválido / schema inválido) ⇒
  tudo OFF, `ToggleStoreError` registrada, app funcional; arquivo ausente ⇒
  bit-a-bit atual.
- **Startup sem permissões:** toggles ON persistidos ⇒ ao recarregar,
  corrections/verification ON **e** `terminal_status()["permission_granted"]`
  continua `false` (nada concedido).
- **UI (fake_tk/headless):** checkbox chama o setter do controller e o
  arquivo é persistido; reflexo do estado após `refresh()`; seção Automação
  não altera estado do terminal.
- **Regressão completa:** suíte inteira sem regressão; baseline 11G
  (982/5/0) como piso.

## 8. Decisões (2026-08-31) e pontos restantes (TBD)

**Resolvidos na implementação (2026-08-31):**

- **Nome do arquivo/classe (item 4 do DRAFT):** como proposto —
  `data/agent_toggles.json` + `ToggleStore`/`ToggleState`/
  `ToggleStoreError` em `app/tools/toggles_store.py`.
- **Compatibilidade de versões (item 3 do DRAFT):** política atual é
  **recusar** `version` desconhecida (fail-closed + aviso no log — arquivo
  ignorado, tudo OFF). Caminho de *migração* para versões futuras segue
  indefinido (TBD abaixo).
- **Mensagens/UX básicas (item 2 do DRAFT, parcialmente):** a seção
  AUTOMAÇÃO mostra o estado atual (ON/OFF) e o clique exibe mensagem de
  status na própria dialog ("… habilitada (pytest_result) (persistida;
  permissões inalteradas).").

**Ainda abertos (evoluções futuras — TBD):**

1. **Opt-out explícito do 11F:** haverá `auto_pytest_after_write_optout`?
   O MVP entregue **não** tem flag do 11F (comportamento derivado, §4);
   reabrir só se o produto exigir desligar o anexo sem desligar a
   verificação.
2. **UX fora da dialog:** onde mostrar "verificação ligada" fora do
   ToolsDialog (status bar? relatório de plano com `verified`?) — não
   entregue na 11H.
3. **Migração de versões futuras:** o código atual rejeita
   `version > 1` (fail-closed); política de migração ainda indefinida.

## Evidências (implementação e testes)

**Implementação (2026-08-31):**

- `app/tools/toggles_store.py` (novo) — `ToggleState` + `ToggleStore`
  (escrita atômica tmp+`os.replace`; `load()` **nunca levanta**: arquivo
  ausente/corrompido ⇒ tudo OFF; `SCHEMA_VERSION = 1`).
- `app/tools/control.py` — `toggles_file` no construtor do
  `ToolsController` (default `data/agent_toggles.json`);
  `_apply_persisted_toggles` no `__init__` (SÓ capacidade — nunca concede
  permissão); `set_corrections_enabled`/`set_verification_enabled`
  (aplicam na hora + persistem + auditam `tool="toggles"`, inclusive
  falha de escrita); properties `corrections_persisted`/
  `verification_persisted`.
- `app/ui/tools_dialog.py` — seção **AUTOMAÇÃO (11H)** (toggles que
  refletem o controller ao abrir; persistem ao clicar; status 🔴/🟢;
  janela 640x680).
- `main.py` — `toggles_file=settings.data_dir / "agent_toggles.json"` na
  criação do controller.

**Testes (5 novos, 2026-08-31):**

- `tests/test_tools_control.py` — 3 testes: persistência/restauração de
  corrections (payload exato `version: 1` + novo controller no mesmo
  arquivo); persistência/restauração de verification (ON e OFF); arquivo
  corrompido ⇒ fail-closed (tudo OFF, sem crash) + recuperação. Em todos:
  `terminal_status()["permission_granted"] is False` — persistência não
  concede permissão.
- `tests/test_tools_dialog.py` — 2 testes headless (fake_tk): clique nos
  toggles da seção Automação chama os setters persistentes, reflete o
  estado no widget, restaura em novo controller e NÃO concede TERMINAL.

**Baseline (pós-11H):** **987 passed / 5 skipped / 0 failed (992
coletados)** — suíte completa (medida 2026-08-31). Baseline pré-11H
preservada: 982/5/0 (987 coletados, pós-11G).

---

## Histórico

- **2026-08-31 — Sincronização com a implementação entregue (11H).**
  Status DRAFT → **IMPLEMENTADA + TESTADA**: store `app/tools/toggles_store.py`,
  wiring no `ToolsController` (load/apply no `__init__` + setters
  persistentes), seção AUTOMAÇÃO no `ToolsDialog`, `toggles_file` no
  `main.py`; +5 testes (3 persistência no controller + 2 UI headless);
  baseline pós-11H 987/5/0 (992 coletados) — baseline do DRAFT (982/5/0,
  987) preservada. §8 passou a "Decisões e pontos restantes" (nome e
  compatibilidade de versões RESOLVIDOS; opt-out do 11F, UX fora da
  dialog e migração futura seguem TBD).
- **2026-08-31 — DRAFT inicial (11H).** Mapeamento de settings/UI
  (COMANDO 055 1/3): `UserConfigStore` limitado a provider/model;
  `ToolsDialog` já gerencia terminal/workspaces/permissões (sessão);
  corrections/verification sem UI nem persistência; 11F derivado. Decisões
  do DRAFT: store `data/agent_toggles.json` (fail-closed, atômico,
  versionado); sem flag própria do 11F no MVP; permissões NUNCA persistidas
  (TERMINAL segue por sessão); aplicação no `__init__` do controller via
  `toggles_file`; nova seção "Automação" no `ToolsDialog`. Baseline de
  referência: 982/5/0 (pós-11G).
