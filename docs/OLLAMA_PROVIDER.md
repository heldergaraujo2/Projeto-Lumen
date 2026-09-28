# Lumen — Ollama Provider (F1)

## Objetivo

A F1 adiciona o Ollama como Provider local oficial da Lumen. O Agent continua
dependendo apenas de AIProvider; Ollama é um adaptador substituível.

### Padrões

- endpoint: http://127.0.0.1:11434
- modelo padrão: qwen2.5-coder:7b-instruct-q8_0
- API: /api/chat e /api/tags
- streaming: NDJSON
- API key: não utilizada
- pull automático de modelos: não realizado

## Configuração

No .env:

    LUMEN_PROVIDER=ollama
    LUMEN_MODEL=qwen2.5-coder:7b-instruct-q8_0
    LUMEN_OLLAMA_BASE_URL=http://127.0.0.1:11434
    LUMEN_OLLAMA_KEEP_ALIVE=5m
    LUMEN_OLLAMA_THINK=0
    LUMEN_REQUEST_TIMEOUT=60
    LUMEN_MAX_RETRIES=2

O modelo precisa estar instalado no Ollama. A Lumen não baixa modelos
automaticamente.

## Contrato

    Agent
      -> AIProvider
         -> OllamaProvider
            -> HTTP /api/chat
               -> AIResponse

O histórico, system prompt, streaming, modelo final e contadores de tokens
são normalizados para os tipos internos da Lumen.

## Saúde

health_check() consulta /api/tags sem alterar o estado do Ollama.
`LUMEN_OLLAMA_THINK=0` mantém o modo de reasoning/thinking desativado por padrão, evitando que limites pequenos de geração sejam consumidos integralmente pelo raciocínio antes da resposta textual. Use `1` quando quiser habilitá-lo.
list_models() lista apenas modelos instalados.

## Segurança e privacidade

O Provider é local por padrão. Nenhuma chave é exigida e o adaptador não envia
dados para um serviço externo. A política de privacidade continua pertencendo
à Lumen e aos Providers de cada ambiente.

## Limitações explícitas da F1

- Tool calling nativo do Ollama ainda não é habilitado por este Provider.
- Vision continua separada do Provider textual.
- A validação real do daemon/modelo precisa ocorrer em uma máquina com Ollama instalado.
