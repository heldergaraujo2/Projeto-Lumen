# Web Research — implementação

## Estado

A Lumen possui uma camada Web real, porém desabilitada por padrão pela permissão `WEB_ACCESS`.

Fluxo:
```
Agent/Planner
  -> web_search | web_fetch
  -> ToolProtocol
  -> ToolsController
  -> PlanExecutor
  -> ToolTaskHandler
  -> ToolRegistry
  -> PermissionManager(WEB_ACCESS)
  -> WebSecurityPolicy
  -> SafeHttpClient
  -> provedor Web
```

## Ferramentas

- `web_search`: busca via DuckDuckGo HTML e retorna fontes estruturadas.
- `web_fetch`: HTTP/HTTPS, extrai texto de HTML/texto e nunca executa JavaScript.

## Segurança

- WEB_ACCESS não é concedida por padrão.
- somente HTTP/HTTPS;
- credenciais embutidas são rejeitadas;
- localhost, loopback, link-local, multicast, unspecified e reserved são bloqueados;
- redes privadas RFC1918 são bloqueadas por padrão;
- DNS é validado antes da conexão;
- redirects são desabilitados no cliente e seguidos manualmente, validando cada destino;
- timeout e limite de bytes;
- conteúdo não textual é rejeitado no fetch;
- auditoria não persiste consulta nem URL completa: somente metadados sanitizados.

## Testes

Os testes unitários são offline e cobrem permissão, política URL, registro, contrato e bloqueios.

O teste real deve validar, no PC, nesta ordem:

1. ativação explícita de WEB_ACCESS;
2. `web_search` contra a Internet;
3. `web_fetch` de uma fonte pública;
4. redirect público;
5. bloqueio de localhost/privado;
6. auditoria sem conteúdo/segredos;
7. recuperação após falha de rede.

O acesso real ainda não deve ser considerado comprovado até esses testes serem executados no ambiente do usuário.
