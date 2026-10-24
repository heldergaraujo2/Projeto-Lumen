# Mem0 local na Lúmen

## Segurança e compatibilidade

- Mem0 é um índice semântico **opcional**; fica desligado por padrão.
- Os arquivos JSON atuais continuam sendo a fonte de verdade, inclusive
  `data/memory/conversation.json`. Não migra, apaga nem reescreve o histórico.
- Os resultados semânticos são tratados apenas como referências: a Lúmen relê
  o registro no armazenamento JSON e descarta IDs inexistentes ou obsoletos.
- O código usa Mem0 OSS com Ollama e Qdrant em modo local. Não requer chave
  Mem0 Platform nem API paga; a telemetria do SDK é desativada antes da importação.
- Os dados do Qdrant e o histórico interno do Mem0 ficam em
  `data/memory/mem0/`, dentro dos dados da Lúmen.
- Se Mem0, Ollama ou o modelo falhar, a busca lexical/JSON continua disponível.
- Registros estruturados novos e atualizados são indexados quando Mem0 está
  ativo. Os registros antigos continuam pesquisáveis pela busca lexical; eles
  não são migrados automaticamente para o índice semântico.

## Instalação isolada no Windows

Execute no PowerShell, na raiz do projeto, com o ambiente virtual da Lúmen ativado:

```powershell
python -m pip install -r requirements-mem0.txt
ollama list
ollama pull nomic-embed-text:latest
```

O modelo de conversa do Mem0 deve ser um modelo **já instalado** no Ollama.
Use o nome exato mostrado por `ollama list`:

```powershell
$env:LUMEN_MEM0_ENABLED = "1"
$env:LUMEN_MEM0_LLM_MODEL = "NOME_EXATO_DO_MODELO_INSTALADO"
$env:LUMEN_MEM0_EMBED_MODEL = "nomic-embed-text:latest"
$env:LUMEN_MEM0_EMBEDDING_DIMS = "768"
```

Essas variáveis valem para o terminal atual. Não alteram `data/settings.json`,
não mudam o provider principal da Lúmen e não ativam Mem0 em outros terminais.
Se quiser testar o modo sem Mem0, abra um terminal novo ou remova
`LUMEN_MEM0_ENABLED`.

## Testes

Primeiro rode os testes offline, sem chamar o Ollama:

```powershell
python -m pytest -q tests/test_mem0_index.py tests/test_mem0_memory_system.py tests/test_mem0_local_integration.py tests/test_memory.py tests/test_memory_system.py
```

O teste real de integração fica ignorado por padrão. Para executá-lo depois que
Ollama estiver ativo, os modelos estiverem disponíveis e as variáveis acima
estiverem definidas:

```powershell
$env:LUMEN_MEM0_INTEGRATION_TESTS = "1"
python -m pytest -q tests/test_mem0_local_integration.py -s
```

Depois, rode a suíte completa:

```powershell
python -m pytest -q
```

A integração só deve ser considerada validada quando os testes offline passarem,
o teste real recuperar a referência semântica e a suíte completa não introduzir
regressões. O código remoto ainda não substitui essa verificação no PC.
