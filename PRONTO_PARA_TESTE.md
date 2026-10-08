# PRONTO PARA TESTE — Projeto-Lumen no Windows

**PR #33 incorporado à branch padrão `master`.** Commit de merge: [`7f7f58ddc79abd9f5096145e7fe8c26609aa2c16`](https://github.com/heldergaraujo2/Projeto-Lumen/commit/7f7f58ddc79abd9f5096145e7fe8c26609aa2c16). Os cinco checks do PR passaram, inclusive `windows`. Suíte rodada novamente sobre a árvore **exata** desse commit de `master`: **1375 passed / 0 failed / 7 skipped** (os skips são ambientais: `tkinter` indisponível no sandbox; não equivalem a validação de Windows/Unreal).

## Comece aqui

**Primeiro leia os [pré-requisitos de `TESTE_LOCAL.md` §1](https://github.com/heldergaraujo2/Projeto-Lumen/blob/master/TESTE_LOCAL.md#1-pr%C3%A9-requisitos).** Use Windows 10/11, Python 3.10+, Unreal Engine 5.0+ (5.3+ recomendado), Git e um projeto `.uproject` de teste. Habilite `RemoteControlAPI` e `PythonScriptPlugin` no projeto; confira os dois controles de execução remota em `Config/DefaultRemoteControl.ini` antes de criar Blueprints.

Em um PowerShell **aberto na raiz de um clone da branch `master`** (por exemplo, clone com `git clone --branch master https://github.com/heldergaraujo2/Projeto-Lumen.git`), substitua o placeholder pelo caminho real do **arquivo** `.uproject` e execute **esta linha única**:

```powershell
.\bootstrap.ps1 -UnrealProjectPath "<CAMINHO_COMPLETO_DO_SEU_PROJETO.uproject>" -LaunchUnreal
```

O bootstrap tenta `git pull --ff-only` na branch atual; confirme que ela é `master`. **Ele prepara e imprime o JSON do servidor MCP, mas não mantém um servidor stdio rodando** — o Claude Desktop/Cline o inicia quando você configurar o cliente conforme [`TESTE_LOCAL.md` §2–3](https://github.com/heldergaraujo2/Projeto-Lumen/blob/master/TESTE_LOCAL.md#2-servidor-mcp).

> **⚠️ Validação manual pendente — 24 verificações.** Os testes automatizados cobrem contratos e mocks; **não** executaram `bootstrap.ps1` no PowerShell 5.1 nem criaram assets em um Unreal real. Faça os blocos abaixo **na ordem**. Comece pela conexão sem escrita; deixe `unreal_add_component` e persistência por último. Para operações de escrita no cliente MCP isolado, `--allow-write` sozinho não aprova checkpoints: só acrescente `--auto-approve` depois de revisar o risco, em um projeto descartável, porque isso elimina a confirmação interativa por operação. `--enable-unreal-bridge` habilita as ferramentas Unreal, mas não concede WRITE por si só.

## Ordem sugerida para as 24 verificações pendentes

### A. Primeiro: ambiente, bootstrap e MCP sem Unreal — 11 verificações

| Ordem | Item do relatório | Verificação |
| ---: | --- | --- |
| 1 | 3.1.1 | Rodar `bootstrap.ps1` de verdade em PowerShell 5.1; confirmar instalação, testes e saída das etapas. |
| 2 | 3.1.2 | Conferir descoberta de Python e seleção do `.uproject` (`Read-Host` sem parâmetro). |
| 3 | 3.1.3 | Testar diagnóstico quando `RemoteControlAPI` não está habilitado; **não** editar um projeto importante para isso. |
| 4 | 3.1.11 | Rodar pytest no Windows e verificar os testes de UI/`tkinter` que foram pulados no sandbox. |
| 5 | 3.1.4 | Configurar o Claude Desktop/Cline para iniciar o subprocesso MCP. |
| 6 | 3.1.5 | Conferir `tools/list` no cliente real; com perfil restrito, apenas leitura. |
| 7 | 3.1.6 | Pedir a leitura de um arquivo de teste do workspace. |
| 8 | 3.1.7 | Confirmar que escrita **sem** `--allow-write` é recusada. |
| 9 | 3.1.8 | Com `--allow-write`, confirmar que a escrita pausa e **nada** é gravado sem autoaprovação; a UI da LUMEN não compartilha o checkpoint desse subprocesso. |
| 10 | 3.1.9 | Configurar `TAVILY_API_KEY` real (ou Brave), habilitar `--enable-web-search` e testar uma busca. Nunca versionar `.env`. |
| 11 | 3.1.10 | Testar o fluxo com um LLM real; até agora o desenvolvimento usou provedores fake/mock. |

### B. Depois: editor conectado, somente operações da RC API pura — 7 verificações

| Ordem | Item do relatório | Verificação |
| ---: | --- | --- |
| 12 | 3.2.1 | Confirmar `GET http://127.0.0.1:30010/remote/info` com o editor aberto. |
| 13 | 3.2.7 | Comparar as rotas reais do editor com as documentadas pela Epic. |
| 14 | 3.2.2 | Habilitar `--enable-unreal-bridge --allow-write` e testar `unreal_get_info` (probe sem mutação). |
| 15 | 3.2.4 | Buscar um asset conhecido via `unreal_search_assets`. |
| 16 | 3.2.3 | Descrever um UObject conhecido via `unreal_describe_object`. |
| 17 | 3.2.6 | Em projeto descartável, alterar propriedade visível com `unreal_set_property` e desfazer com Ctrl+Z. |
| 18 | 3.2.5 | Chamar uma função `BlueprintCallable` segura com `unreal_call_function` e conferir o resultado/Undo. |

### C. Por último: Python no Unreal Editor — 6 verificações (**menor confiança**)

| Ordem | Item do relatório | Verificação |
| ---: | --- | --- |
| 19 | 3.3.1 | Conferir os **dois** portões de `Config/DefaultRemoteControl.ini` e reiniciar o editor. |
| 20 | 3.3.2 | Verificar a resposta real de `ExecutePythonCommandEx` e o `Output Log` da versão instalada. |
| 21 | 3.3.3 | Criar `BP_TestConnection` com `unreal_create_blueprint_class`; confirmar classe pai e asset no Content Browser. |
| 22 | 3.3.5 | Verificar a disponibilidade do método `BlueprintEditorLibrary.open_blueprint` nessa versão. |
| 23 | 3.3.4 | **Mais volátil:** testar `unreal_add_component` em Blueprint descartável, com o editor de Blueprint aberto se necessário. |
| 24 | 3.3.6 | Compilar, salvar, fechar e reabrir o projeto; verificar que o componente persistiu. |

Roteiro detalhado de `BP_TestConnection`: [`TESTE_LOCAL.md` §4](https://github.com/heldergaraujo2/Projeto-Lumen/blob/master/TESTE_LOCAL.md#4-teste-m%C3%ADnimo--valide-a-fase-4-passo-a-passo). Motivos técnicos e riscos por item: [`RELATORIO_FINAL.md` §3](https://github.com/heldergaraujo2/Projeto-Lumen/blob/master/RELATORIO_FINAL.md#3-o-que-precisa-de-valida%C3%A7%C3%A3o-manual-no-seu-pc). **Não trate os 24 itens como funcionalidades já validadas.**
