# `archive/` — código removido do runtime (Fase 0)

Este diretório guarda o que foi **removido do caminho de execução** na Fase 0 da
limpeza (2026-10-08), após a auditoria técnica registrar que **~36% de `app/`
era código inalcançável**.

**Nada aqui é importado por `main.py`, pela UI ou por qualquer módulo vivo.**
O `pytest.ini` na raiz declara `norecursedirs = archive`, então nada aqui é
coletado pela suíte.

---

## O que foi arquivado e por quê

Critério objetivo: um pacote foi arquivado se **nenhum** caminho de execução a
partir de `main.py` / `app/ui/` chegava até ele. Verificado por busca de
importações — `ComputerControlService`, por exemplo, era instanciado **apenas
em testes**.

| Pacote | LOC | Motivo |
| --- | --- | --- |
| `app/evolution/` | 4.719 | Nenhum importador de produção (só `StackLayer`, extraída) |
| `app/computer_control/` | 1.908 | `ComputerControlService` nunca instanciado fora de testes |
| `app/computer/` | 708 | Só era importado por `app/unreal/` (também arquivado) |
| `app/unreal/` | 409 | Só gerava atalhos de teclado; nenhuma ponte real com o Unreal |
| `app/workflows/` | 364 | Cadeia morta via `app/unreal/` |
| `app/experience/` | 355 | Nenhum importador de produção |
| `app/autonomy/` | 224 | Nenhum importador de produção |
| `app/learning/` | 132 | Cadeia morta via `app/workflows/` |

**Total arquivado: ~8.819 LOC** em 8 pacotes, mais **38 arquivos de teste**.

Os testes correspondentes foram para `archive/tests/` porque verificavam
exatamente o código removido. A suíte viva caiu de ~1.393 para **991 testes
passando** — a queda é a medida da remoção, não uma perda de cobertura do que
continua no runtime.

---

## O que NÃO foi arquivado, e por quê

### `app/validation/` (64 LOC) — **mantido**

Embora também não seja importado pelo runtime, é um **detector de ambiente
fail-closed** (`.github/workflows/f23-validation.yml` o executa como gate de
CI) e é pequeno o suficiente para não pesar. Arquivá-lo exigiria remover um
workflow de CI — fora do escopo de uma limpeza.

### `app/ai/provider_runtime.py` — **mantido, com import corrigido**

Dependia de `app.evolution.intelligence_stack.StackLayer` — uma **dependência
invertida** de código vivo para código morto. `StackLayer` foi extraída para
`app/ai/stack_layer.py` e o import atualizado. Nenhuma semântica mudou.

---

## Isto é reversível

Tudo aqui veio de `git mv`, então o histórico é preservado e a restauração é
direta:

```bash
git mv archive/app/evolution app/evolution
git mv archive/tests/test_evolution_foundation.py tests/
```

Se algum destes subsistemas for retomado (ex.: o controle de computador
autônomo), restaure o pacote **e** o teste, e reconecte-o a um caminho de
execução real — não basta mover de volta.
