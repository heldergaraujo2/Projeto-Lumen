# Persistência Estruturada, Recuperação Confiável e Retomada na Lúmen

## Visão Geral

Este documento descreve a arquitetura de persistência estruturada de execuções, recuperação de contexto e retomada de tarefas da Lúmen, atendendo aos requisitos de autonomia, verificabilidade e memória confiável.

---

## 1. Arquitetura da Persistência de Execuções

A persistência de execuções na Lúmen é gerenciada pela classe `ExecutionBundleStore` em `app/memory/execution_store.py`.

A cada término de plano ou tarefa (nos estados `COMPLETED` ou `FAILED`), a Lúmen gera e salva de forma atômica um "bundle" sanitizado contendo:
- Metadados do plano (`plan_id`, `conversation_id`, `workspace`, `lumen_version`, `saved_at`).
- Definição completa do plano (`Plan.to_dict()`).
- Relatório de execução (`ExecutionReport.to_dict()`).
- Registros individuais e estruturados de execução (`ExecutionRecordEntry`).
- Histórico do ciclo de correção automática, quando ativado.

### Gravação Atômica e Sanitização
1. **Redação de Segredos**: Toda string enviada ao `ExecutionBundleStore` passa por `redact_secrets` antes da escrita.
2. **Remoção de Campos Sensíveis**: Saídas brutas de terminal (`stdout`, `stderr`) e conteúdo integral de leitura de arquivos (`content`) são removidos de payloads com formato de `ToolResult`.
3. **Escrita Atômica**: Os bundles são salvos primeiramente em um arquivo temporário (`.json.tmp`) no diretório do workspace/execuções e atomicamente substituídos com `os.replace`.

---

## 2. Modelo de Dados

### 2.1. Enumeração de Estados de Execução (`ExecutionState`)
- `PENDING`: Aguardando execução.
- `RUNNING`: Em andamento.
- `SUCCEEDED`: Concluída com sucesso e verificação válida.
- `FAILED`: Falhou durante a execução ou no manipulador da ferramenta.
- `CANCELLED`: Interrompida ou pulada (ex: `SKIPPED`).
- `TIMED_OUT`: Execução excedeu o tempo limite.
- `VERIFICATION_FAILED`: Ferramenta retornou sem erro, mas a verificação posterior reprovou o resultado.
- `UNKNOWN`: Estado indeterminado.

### 2.2. Registro Estruturado (`ExecutionRecordEntry`)
| Campo | Tipo | Descrição |
|---|---|---|
| `execution_id` | `str` | Identificador único (`EXEC-<plan_id>-<task_id>`) |
| `conversation_id` | `str \| None` | ID da conversa associada |
| `task_id` | `str \| None` | ID da tarefa no plano (`T1`, `T2`...) |
| `parent_execution_id` | `str \| None` | Execução predecessora quando aplicável |
| `tool_name` | `str \| None` | Nome real da ferramenta chamada |
| `tool_version` | `str \| None` | Versão da ferramenta (se disponível) |
| `requested_action` | `str \| None` | Ação ou descrição solicitada |
| `arguments` | `dict` | Parâmetros com segredos redigidos |
| `started_at` | `str \| None` | Timestamp ISO-8601 de início |
| `completed_at` | `str \| None` | Timestamp ISO-8601 de término |
| `status` | `ExecutionState` | Estado estruturado de execução |
| `result` | `Any` | Resultado estruturado retornado |
| `error` | `str \| None` | Erro estruturado quando houver |
| `verification` | `dict` | Resultado da verificação posterior |
| `workspace` | `str \| None` | Workspace associado |
| `evidence` | `list[str]` | Referências a evidências observadas |

---

## 3. Fluxo de Recuperação e Contexto

Ao receber uma pergunta conversacional sobre execuções anteriores:
1. `ToolCallingBridge` consulta `ExecutionBundleStore.query_executions(...)` utilizando `conversation_id`, `task_id` ou workspace.
2. A recuperação lê os dados do registro de execução real preservados no arquivo JSON.
3. Se a ferramenta reportou um caminho resolvido (`resolved_path`) ou status de existência (`exists`), esses dados exatos são repassados ao modelo no contexto conversacional.
4. O modelo responde com base em evidência real preservada, evitando alucinações de caminhos inexistentes (ex: `/workspace/README.md`).

---

## 4. Retomada de Tarefas Interrompidas (Fase F)

O `ToolsController` expõe os métodos:
- `get_interrupted_tasks()`: Consulta registros em estado `PENDING`, `RUNNING`, `FAILED` ou `UNKNOWN`.
- `resume_execution(plan_id)`: Carrega o bundle salvo do plano e reinstancia o `PlanExecutor` para dar continuidade à execução a partir das tarefas pendentes.

---

## 5. Como Executar os Testes

Para executar toda a suíte de validação:

```bash
pytest
```

Para rodar os testes específicos da persistência de execução:

```bash
pytest tests/test_execution_persistence.py
```
