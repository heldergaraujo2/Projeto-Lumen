# Threat Model — Lumen F0

## Ativos protegidos

API keys e secrets; arquivos/workspaces; comandos do sistema; mouse/teclado;
screenshots; memória; logs; integridade do runtime; regras de segurança;
experimentos/candidatos; identidade e contratos arquiteturais.

## Ameaças

| ID | Ameaça | Impacto | Controle |
|---|---|---|---|
| T01 | Prompt injection externo | Alto | conteúdo externo sem autoridade |
| T02 | Bypass de Permission | Crítico | porteiro central + testes |
| T03 | Traversal/symlink escape | Alto | sandbox + resolução final |
| T04 | Comando fora da allowlist | Crítico | TerminalPolicy + denylist + checkpoint |
| T05 | Modelo controlando driver diretamente | Crítico | Tool/Policy/Permission/Checkpoint |
| T06 | Screenshot sensível em Provider externo | Alto | consentimento, escopo, crop, retenção |
| T07 | Secret em logs/memória | Alto | sanitização e redaction |
| T08 | Experimento quebrando runtime | Alto | laboratório isolado + promoção |
| T09 | Evolução enfraquecendo controles | Crítico | Human Approval Gate |
| T10 | Falso sucesso | Alto | Verification + evidência |
| T11 | Dependência de Provider | Médio | contratos abstratos + routing |
| T12 | Snapshot/artifact sensível | Alto | limites, sanitização e retenção |

## Cadeia de autoridade

Goal → Planning → Tool contract → Permission → Policy → Scope → Checkpoint
→ Execution → Audit → Verification.

Nenhuma resposta do modelo deve saltar diretamente para Execution.

## Prompt injection

Webpages, documentos, issues, READMEs, screenshots e demais conteúdo externo
são dados não-confiáveis. Instruções encontradas neles não são comandos para
a Lumen.

## Dados visuais

Screenshots podem conter credenciais, documentos, mensagens privadas e dados
pessoais. F7/F8 devem definir minimização, consentimento, escopo e retenção.

## Evolução

LES pode propor e experimentar, mas não pode alterar seus próprios limites
de autoridade sem Human Approval.

## Aceitação

A meta não é risco zero. A meta é superfície reduzida, fail-closed,
decisões auditáveis, regressões mensuráveis e recuperação possível.
