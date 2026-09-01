# SPEC CC-01 — Computer Control MVP (LUMEN)

**Status:** Draft (CC-1 / doc-first)    
**Escopo:** Definir o MVP de Computer Control (CC) com coleira de segurança, sem implementar driver OS ainda.

---

## 1) Princípios (imutáveis)

**North Star:** LUMEN é um Agent desktop para Windows que executa trabalho real no PC do usuário sob uma coleira de segurança (com verificação/evidência e auditoria).

**Regra central:** **INTELIGÊNCIA ≠ AUTORIDADE**    
Providers (LLMs) fornecem apenas inteligência/orientação. **Nunca executam** e **nunca têm autoridade** sobre Tools/PC. A LUMEN executa sob controles explícitos.

---

## 2) Objetivo do CC MVP

Criar a base segura para Computer Control que:
- respeite a coleira (permissão + policy + scope + checkpoint + audit),
- seja validável com **FakeDriver** (testes unitários),
- permita futuramente um driver real de Windows (mouse/teclado/screenshot),
- não quebre guards AST existentes.

---

## 3) Não-objetivos (fora do MVP)

- OCR/visão/interpretação de tela (sem extrair texto de imagem)
- Unreal Engine pack / automação do Unreal Editor
- Automação avançada (image matching, accessibility tree, detecção de widgets)
- Persistir bytes de screenshot no audit JSONL
- Registrar texto digitado no audit (proibido)

---

## 4) Restrição crítica: guards AST

Há guards AST que proíbem imports/tokens perigosos em `app/tools/*.py` (ex.: `ctypes`, `pyautogui`, `pynput`, `win32*`, `socket`, `requests`, `urllib`, `shutil`, etc.).

**Consequência obrigatória:**
- `app/tools/` terá apenas **fachadas finas** (sem libs OS).
- Implementação/driver OS deve ficar fora de `app/tools/` (ex.: `app/computer_control/windows/driver.py`).

---

## 5) Coleira CC (não-negociável) + fail-closed

Toda ação CC deve seguir SEM BYPASS:

**PermissionManager → Policy → Sandbox/Escopo → Checkpoint → Tool/ComputerControl → Audit → Resultado**

**Fail-closed:** por padrão, CC nega. Só executa se:
- permissão `COMPUTER_CONTROL` estiver concedida na sessão,
- existir um **CC Scope** válido que autorize a ação,
- policy permitir,
- checkpoint (quando exigido) for aprovado,
- audit metadados-only for registrado.

---

## 6) Permissão `COMPUTER_CONTROL` por sessão (grant dedicado)

- Concessão deve ser **explícita**, **sessão-only** e **auditada** (admin audit).
- Não pode ser persistida em `agent_toggles.json` (toggles persistem capacidade, não permissão).
- Deve existir um fluxo dedicado similar a `grant_terminal()`:
  - `grant_computer_control()` (concede na sessão)
  - `revoke_computer_control()` (revoga na sessão)
- Revogar automaticamente ao encerrar sessão; opcionalmente por timeout.

---

## 7) CC Scope (consentimento granular)

Um **CC Scope** é o objeto de consentimento granular emitido pela LUMEN (após checkpoint quando aplicável) que define **o que** pode ser controlado no desktop e **por quanto tempo**, com limites quantitativos.

**Sem scope válido, nenhuma ação de Computer Control executa** (fail-closed).

### 7.1 Campos mínimos (MVP)
Um scope deve conter, no mínimo:

- `scope_id`: string (ex.: UUID)
- `created_at`: timestamp
- `expires_at`: timestamp (**obrigatório**; default curto)
- `target`: alvo permitido (MVP; metadados mínimos)
  - `app_name` e/ou `process_name` (string)
  - e/ou `window_title_pattern` (string; substring/regex simples)
- `allowed_actions`: conjunto/enum
  - MVP recomendado iniciar com: `SCREENSHOT`
  - Futuro: `MOUSE_MOVE`, `MOUSE_CLICK`, `SCROLL`, `KEY_TYPE`, `KEY_COMBO`
- `limits`: objeto (**obrigatório**, fail-closed)
  - `max_actions_total`: int > 0
  - `max_actions_per_minute`: int > 0 (ou cooldown equivalente)
  - (opcional) `max_session_seconds`
  - (futuro) `allowed_region`: (x, y, w, h) para restringir área de clique

### 7.2 Validade e expiração
- Se `now >= expires_at` → scope inválido (nega)
- Se limites excedidos → scope inválido (nega até novo scope)
- Scopes devem ser listáveis e revogáveis.

---

## 8) Policy CC (hard-deny)

A policy de CC deve negar explicitamente:
- qualquer ação sem `COMPUTER_CONTROL` concedido **na sessão**
- qualquer ação sem scope aplicável e válido
- qualquer ação fora de `allowed_actions`
- qualquer ação após expiração do scope
- qualquer ação que exceda limites
- qualquer tentativa de registrar conteúdo sensível no audit (ver §10)

**Nota:** o MVP não inclui OCR/visão. Qualquer tentativa de “ler tela” além do permitido (ex.: extrair texto) deve ser tratada como fora de escopo (hard-deny).

---

## 9) Checkpoints (prevalidated; sem decorativos)

- `cc_request_scope` (criar/emitir scope) exige **checkpoint prevalidated**.
- `cc_revoke_scope` (redução de privilégio) pode ser sem checkpoint (preferível).
- Ações CC podem exigir checkpoint dependendo do risco:
  - MVP (iniciando com `SCREENSHOT` via FakeDriver): decisão conservadora recomendada (exigir checkpoint no primeiro uso ou sempre), a ser fixada em CC-2/CC-3.
  - Futuro (mouse/teclado): checkpoint obrigatório em ações sensíveis e/ou no primeiro uso por scope.

---

## 10) Audit CC (metadados-only; proibido conteúdo)

### 10.1 Princípio
Audit deve registrar **apenas metadados** para evidência e diagnóstico, sem vazar conteúdo sensível.

### 10.2 Proibições explícitas (não-negociável)
Audit JSONL **NUNCA** deve conter:
- bytes de screenshot (nem raw, nem base64)
- texto digitado (nem parcial, nem completo)
- conteúdo extraído de tela (OCR/visão)
- dumps de buffers/frames

**Opcionalmente sensível:** coordenadas exatas (x,y). Se forem registradas no futuro, devem ser minimizadas/quantizadas e justificadas. No MVP, preferir não registrar coordenadas.

### 10.3 Campos recomendados (MVP)
- `operation`: `cc_grant`, `cc_revoke`, `cc_scope_created`, `cc_scope_revoked`, `cc_action_attempted`, `cc_action_denied`, `cc_action_done`
- `timestamp`
- `scope_id` (quando aplicável)
- `action_type`
- `target_summary` (sanitizado; mínimo necessário)
- `decision`: `allowed` / `denied`
- `denied_reason` (quando aplicável)
- `duration_ms` (quando aplicável)
- `artifact_ref` (opcional; **apenas referência**, nunca bytes)


---

## 11) Tools previstas (CC-3) — fachada fina (sem libs OS)

As tools CC devem existir como **fachadas finas** em `app/tools/`:

- Sem imports de automação/OS (para respeitar guards AST),
- Apenas aplicando coleira (permission/policy/scope/checkpoint) e audit,
- Delegando a execução para o núcleo/driver em `app/computer_control/*`.

MVP mínimo sugerido:

- `cc_request_scope` (COMPUTER_CONTROL; **checkpoint**) — emite um scope
- `cc_list_scopes` (read-only) — lista scopes ativos (metadados)
- `cc_revoke_scope` — revoga scope
- `cc_screenshot` (COMPUTER_CONTROL; exige scope com `SCREENSHOT`) — no MVP via FakeDriver

**Nota:** o MVP não inclui mouse/teclado; estes entram depois que o desenho estiver validado.

---

## 12) Driver e camadas (para não quebrar guards)

- **Core puro (CC-2):** `app/computer_control/*` (dataclasses/interfaces/policy/audit/scope)
- **FakeDriver (CC-2):** simula ações para testes unitários; não toca no PC
- **Driver Windows real (CC-4, futuro):** `app/computer_control/windows/driver.py`
  Imports OS (WinAPI/ctypes/win32) ficam **somente aqui**, fora de `app/tools/`.

---

## 13) Plano de testes

### 13.1 Unit tests (FakeDriver; cross-platform)
Objetivo: validar segurança e comportamento fail-closed sem automação real.

- Scopes: expiração, limites, allowed_actions
- Policy: hard-deny (sem permissão, sem scope, scope expirado/limite excedido)
- Audit: garantir **metadados-only** (nenhum byte de screenshot, nenhum texto digitado)

### 13.2 Smoke Windows (skip fora do Windows)
Objetivo: validar wiring mínimo do driver real quando existir.

- Deve ser marcado como `skip` fora do Windows e/ou sem ambiente adequado.
- Não substitui testes unit.

---

## 14) Roadmap imediato (pós CC-1)

- **CC-1:** esta SPEC (doc-only)
- **CC-2:** núcleo puro + FakeDriver + testes unit
- **CC-3:** tools fachada + `grant_computer_control()` sessão-only + wiring registry (OFF por padrão)
- **CC-4:** driver Windows real + smoke (skip)
- **CC-5:** UI: grant CC e gestão de scopes
- **CC-6+:** mouse/teclado sob scope/limites + audit metadados-only

---

## 15) Checklist de aceitação (para fechar CC-1)

- [ ] Define coleira CC e fail-closed
- [ ] Define `COMPUTER_CONTROL` por sessão (grant dedicado; não persistir)
- [ ] Define CC Scope (campos mínimos, expiração, limites)
- [ ] Define audit metadados-only (nunca bytes de screenshot no JSONL; nunca texto digitado)
- [ ] Define plano de testes (FakeDriver unit + smoke Windows skip)
- [ ] Lista não-objetivos (OCR/visão, Unreal pack, automação avançada)

