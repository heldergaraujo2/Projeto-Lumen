# Validação final — estado e evidências (2026-10-24)

## Escopo

Registro da auditoria estática do branch `feat/external-mcp-voice-runtime` antes de qualquer atualização da instalação local. Este documento separa evidência de repositório/CI de validação física no Windows.

## Estado do código auditado

- Commit base informado para o PC: `4fd6cc9`.
- Commit `51518a7`: remove declaração duplicada de `persist_execution_state`.
- Commit `2fa0479`: corrige a gravação de `data/conversation_id.txt` para usar uma quebra de linha real, em vez dos caracteres literais `\n`.
- Commit `328f76d`: adiciona teste de regressão que verifica UUID válido, newline real e persistência estável do ID.
- O teste novo foi incluído no workflow `Lumen Tests`.

## Evidência automatizada

Para o commit `328f76d00f7cbe43bd2dfeb49f007b49ee47b75b`:

- **Lumen Tests: PASS** — 1732 passed, 9 skipped, 20.52 s.
- **Lumen F23 Validation: PASS** — jobs Ubuntu e Windows concluídos com sucesso.
- **Lumen Windows Validation:** estava em execução quando este registro foi criado. Consultar o estado atual do GitHub Actions antes de promover o commit.
- Os resultados locais previamente informados pelo usuário (1698 passed, 42 skipped) são históricos do commit anterior e não substituem os resultados deste commit.

CI hospedada não prova que o provider externo, o servidor MCP de desktop, o microfone, os alto-falantes ou as ações físicas funcionem na máquina do usuário.

## Matriz de evidências

### OrcaRouter / DeepSeek

- **CONFIRMADO (código):** existe `OrcaRouterProvider`, usando endpoint OpenAI-compatible `https://api.orcarouter.ai/v1` e modelo padrão `deepseek/deepseek-v4.1-flash-free`.
- **CONFIRMADO (testes):** há testes automatizados do provider, executados na suíte CI.
- **DESCONHECIDO (execução real):** nenhuma chamada autenticada foi feita nesta auditoria. A presença do provider e o sucesso dos testes não provam que a chave local seja válida, que a conta tenha cota disponível ou que a resposta real seja recebida. O modelo gratuito pode aplicar rate limits; HTTP 429 deve ser tratado como limite, não como defeito do código por si só.

### Servidores MCP externos

- **CONFIRMADO (código):** transporte stdio com handshake MCP, `tools/list`, `tools/call`, allow-list exata, timeout, fechamento do processo, permissão `COMPUTER_CONTROL` e checkpoint explícito.
- **CONFIRMADO (configuração versionada):** `config/mcp_servers.example.json` é um modelo desabilitado, com allow-list vazia.
- **CONFIRMADO (testes):** os testes de protocolo usam um processo MCP de teste/fake.
- **DESCONHECIDO (execução real):** não foi confirmado que o servidor desktop externo esteja instalado, que o comando/argumentos configurados sejam os oficiais e atuais, que a UI real exponha a ferramenta ou que uma ação inofensiva tenha alterado e depois verificado o estado do desktop. Não habilitar comandos ou ferramentas por suposição.

### Interface e voz

- **CONFIRMADO (código/documentação):** existe a especificação da missão de voz e um verificador que exige evidência de todos os critérios de aceitação.
- **CONFIRMADO (inspeção estática):** a janela principal atual não apresenta controles de voz, captura de microfone, STT, TTS ou reprodução de áudio. `docs/VOICE_CHAT_CONTINUITY.md` também declara que o fluxo completo não está implementado nem testado fisicamente.
- **DESCONHECIDO / PENDENTE:** não há evidência de um ciclo integrado UI → microfone → STT → Agent → TTS → alto-falantes → próximo turno. Não marcar a missão de voz como concluída. Se a entrega exigir voz integrada, essa lacuna precisa ser implementada e testada no repositório antes de tratar a validação final como concluída.

### Recuperação segura de execução

- **CONFIRMADO (código):** persistência opt-in; snapshots antes da execução do handler; retomada explícita; validação do plano/relatório; bloqueio de bundles legados sem identidade e de identidade divergente; tarefas `IN_PROGRESS` ou estados ambíguos não devem ser repetidos automaticamente; checkpoints/aprovações não são restaurados.
- **CONFIRMADO (limite atual):** `data/conversation_id.txt` identifica o histórico local desta instalação. O código não fornece ainda um identificador distinto para múltiplas conversas independentes dentro da mesma instalação. O isolamento por ID fornecido é validado, mas o isolamento entre várias conversas da UI não está implementado como capacidade separada.
- **DESCONHECIDO (execução real):** não foi feita nesta auditoria uma interrupção controlada de processo real seguida de retomada, nem uma inspeção do sistema-alvo para demonstrar que uma ação externa ambígua não foi duplicada.

## Próximos gates

1. Confirmar que todos os workflows estão verdes no HEAD final do branch.
2. No Windows do usuário, auditar branch, commit, árvore Git e os arquivos locais não rastreados antes de qualquer pull. Não usar operações destrutivas.
3. Testar OrcaRouter por uma chamada mínima com a chave mantida no cofre/ambiente local; nunca imprimir a chave nem o cabeçalho Authorization. Registrar modelo/resposta/erro sanitizados e distinguir rate limit de falha de autenticação.
4. Confirmar a documentação oficial atual do servidor MCP escolhido antes de configurar o executável e argumentos. Manter o servidor desabilitado até validar a allow-list mínima.
5. Testar a UI/MCP com uma ação não destrutiva, checkpoint explícito e observação independente do estado final.
6. Tratar a voz como pendente até existir e passar um teste E2E real com microfone e alto-falantes.
7. Tratar isolamento por conversa de UI como pendente caso a Lúmen passe a suportar múltiplas conversas na mesma instalação.

## Segurança operacional

Não registrar chaves, tokens, áudio bruto, conteúdo integral de arquivos, saídas sensíveis de ferramentas ou capturas de tela em logs. Não declarar uma integração funcional com base apenas em configuração, mocks ou testes unitários.
