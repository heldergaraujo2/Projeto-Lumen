"""Políticas de segurança para acesso HTTP/HTTPS.

Esta camada não executa requisições. Ela valida destinos antes que uma
futura ferramenta Web faça qualquer conexão. O objetivo é impedir, por
padrão, esquemas perigosos, destinos locais/privados e URLs ambíguas.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit


class WebSecurityError(ValueError):
    """Destino Web rejeitado pela política de segurança."""


@dataclass(frozen=True)
class WebSecurityPolicy:
    """Política conservadora para destinos HTTP/HTTPS."""

    allowed_schemes: tuple[str, ...] = ("http", "https")
    allow_private_networks: bool = False
    allow_localhost: bool = False
    max_url_length: int = 4096
    max_redirects: int = 5

    def validate(self) -> None:
        schemes = tuple(s.lower() for s in self.allowed_schemes)
        if not schemes or any(s not in {"http", "https"} for s in schemes):
            raise WebSecurityError("Apenas os esquemas http e https são permitidos.")
        if self.max_url_length <= 0:
            raise WebSecurityError("max_url_length deve ser positivo.")
        if self.max_redirects < 0:
            raise WebSecurityError("max_redirects não pode ser negativo.")

    def validate_url(self, url: str, *, resolve_dns: bool = True) -> str:
        """Valida e normaliza uma URL sem realizar uma requisição HTTP."""
        self.validate()
        if not isinstance(url, str) or not url.strip():
            raise WebSecurityError("URL vazia ou inválida.")

        value = url.strip()
        if len(value) > self.max_url_length:
            raise WebSecurityError("URL excede o limite de tamanho.")

        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if scheme not in self.allowed_schemes:
            raise WebSecurityError(f"Esquema não permitido: {scheme or '<ausente>'}.")

        if parsed.username is not None or parsed.password is not None:
            raise WebSecurityError("URLs com credenciais embutidas não são permitidas.")

        hostname = parsed.hostname
        if not hostname:
            raise WebSecurityError("URL sem hostname.")

        hostname = hostname.rstrip(".").lower()
        if hostname == "localhost" and not self.allow_localhost:
            raise WebSecurityError("localhost não é permitido.")

        addresses = self._resolve(hostname) if resolve_dns else self._literal_addresses(hostname)
        if not addresses:
            if self._looks_like_ip(hostname):
                raise WebSecurityError("Endereço IP inválido.")
            # Sem resolução DNS não há como avaliar SSRF de hostname.
            # A execução real deve sempre usar resolve_dns=True.
            if resolve_dns:
                raise WebSecurityError("Hostname não pôde ser resolvido.")

        for address in addresses:
            if not self.allow_private_networks and self._is_private_or_local(address):
                raise WebSecurityError(
                    f"Destino de rede privada/local não permitido: {address}."
                )

        return parsed.geturl()

    @staticmethod
    def _looks_like_ip(hostname: str) -> bool:
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            return False

    @staticmethod
    def _literal_addresses(hostname: str) -> tuple[ipaddress._BaseAddress, ...]:
        try:
            return (ipaddress.ip_address(hostname),)
        except ValueError:
            return ()

    @staticmethod
    def _resolve(hostname: str) -> tuple[ipaddress._BaseAddress, ...]:
        try:
            infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise WebSecurityError("Hostname não pôde ser resolvido.") from exc

        addresses: list[ipaddress._BaseAddress] = []
        for info in infos:
            raw = info[4][0]
            try:
                address = ipaddress.ip_address(raw)
            except ValueError as exc:
                raise WebSecurityError("Resposta DNS contém endereço inválido.") from exc
            if address not in addresses:
                addresses.append(address)
        return tuple(addresses)

    @staticmethod
    def _is_private_or_local(address: ipaddress._BaseAddress) -> bool:
        return (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        )
