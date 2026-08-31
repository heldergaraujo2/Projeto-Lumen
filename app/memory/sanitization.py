"""Proteção de segredos na memória da Lumen.

Regra da 0.3: **segredos, API keys e credenciais nunca entram na
memória**. Todo registro gravado pelos domínios de memória passa por
:func:`redact_secrets` antes da persistência — padrões conhecidos são
substituídos por ``***`` e o texto permanece útil para contexto.
"""
from __future__ import annotations

import re

#: Padrões de credencial (parcial, intencionalmente conservadores para
#: não mutilar conteúdo técnico normal).
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Chaves estilo OpenAI/Genérico "sk-..."
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    # Chaves do Google (AI Studio/Gemini) "AIza..."
    re.compile(r"\bAIza[A-Za-z0-9_\-]{10,}\b"),
    # Tokens de autorização "Bearer eyJ..."
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    # Atribuições explícitas: api_key=..., password: ..., Bearer ...
    re.compile(
        r"(?i)\b(api[_\-]?key|apikey|password|passwd|secret|credential|"
        r"bearer|access[_\-]?token|refresh[_\-]?token)\b\s*[:=]\s*\S+"
    ),
)

_REDACTED = "***"


def redact_secrets(text: str) -> tuple[str, bool]:
    """Substitui segredos por ``***``.

    Returns:
        ``(texto_redigido, encontrou_segredo)``
    """
    redacted = text
    found = False
    for pattern in _SECRET_PATTERNS:
        new_text, n = pattern.subn(_REDACTED, redacted)
        if n:
            found = True
            redacted = new_text
    return redacted, found


def contains_secret(text: str) -> bool:
    """Verifica se o texto contém algum padrão de credencial."""
    _, found = redact_secrets(text)
    return found
