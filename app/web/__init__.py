"""Infraestrutura de acesso Web da Lumen.

A camada Web é separada de filesystem, terminal e computer control.
Ela fornece políticas de segurança, provedores e ferramentas estruturadas
para pesquisa e obtenção de conteúdo HTTP/HTTPS, sempre protegidas pela
permissão explícita WEB_ACCESS e pelas validações de destino.
"""