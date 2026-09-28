"""Testes da política de segurança Web (W1)."""
from __future__ import annotations

import ipaddress

import pytest

from app.web.security import WebSecurityError, WebSecurityPolicy


def test_https_public_literal_ip_is_allowed():
    policy = WebSecurityPolicy()
    assert policy.validate_url("https://1.1.1.1/", resolve_dns=False) == "https://1.1.1.1/"


@pytest.mark.parametrize(
    "url",
    (
        "file:///etc/passwd",
        "ftp://example.com/resource",
        "javascript:alert(1)",
        "data:text/plain,hello",
    ),
)
def test_unsafe_schemes_are_rejected(url):
    with pytest.raises(WebSecurityError):
        WebSecurityPolicy().validate_url(url, resolve_dns=False)


@pytest.mark.parametrize(
    "url",
    (
        "http://127.0.0.1/",
        "http://localhost/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/",
        "http://[::1]/",
    ),
)
def test_local_and_private_destinations_are_rejected(url):
    with pytest.raises(WebSecurityError):
        WebSecurityPolicy().validate_url(url, resolve_dns=False)


def test_embedded_credentials_are_rejected():
    with pytest.raises(WebSecurityError):
        WebSecurityPolicy().validate_url("https://user:pass@example.com/", resolve_dns=False)


def test_url_length_is_limited():
    policy = WebSecurityPolicy(max_url_length=32)
    with pytest.raises(WebSecurityError):
        policy.validate_url("https://example.com/" + "a" * 64, resolve_dns=False)


def test_dns_private_result_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "app.web.security.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("192.168.1.10", 0)),
        ],
    )
    with pytest.raises(WebSecurityError):
        WebSecurityPolicy().validate_url("https://attacker.example/", resolve_dns=True)


def test_dns_public_result_is_allowed(monkeypatch):
    monkeypatch.setattr(
        "app.web.security.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("93.184.216.34", 0)),
        ],
    )
    assert WebSecurityPolicy().validate_url("https://example.com/", resolve_dns=True) == "https://example.com/"


def test_policy_does_not_execute_http():
    policy = WebSecurityPolicy()
    assert not hasattr(policy, "get")
    assert not hasattr(policy, "request")
    assert ipaddress.ip_address("127.0.0.1").is_loopback
