"""Conservative, local-only secret redaction for recorded traffic."""

from __future__ import annotations

import re
from typing import Any


SECRET_KEYS = {
    "api_key", "apikey", "authorization", "cookie", "password", "passwd",
    "secret", "token", "access_token", "refresh_token", "client_secret",
    "private_key", "x-api-key", "set-cookie",
}

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
]


def _redact_string(value: str) -> str:
    result = value
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def redact(value: Any, *, key: str | None = None) -> Any:
    if key is not None and key.lower() in SECRET_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value

