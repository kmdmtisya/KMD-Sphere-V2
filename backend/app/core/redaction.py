"""Log redaction: secrets, credentials and financial values never reach log output.

Two layers work together:
1. Key-based: any mapping key that names a credential or a financial quantity has its value
   replaced, whatever the value's type (structured `extra` fields, nested dicts and lists).
2. Pattern-based: free text (messages, exception traces) is scrubbed for bearer tokens, JWTs,
   credentials embedded in URLs and DSNs, `key=value` / `"key": "value"` pairs for the same
   sensitive and financial keys, and sensitive query-string parameters.

Over-redaction is preferred to leakage (CLAUDE.md: do not log secrets or unnecessary sensitive
financial payloads). New sensitive field names are added to the sets below.
"""

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
_MAX_DEPTH = 6

CREDENTIAL_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "authorization",
        "proxy_authorization",
        "api_key",
        "apikey",
        "x_api_key",
        "client_secret",
        "cookie",
        "set_cookie",
        "private_key",
        "credential",
        "credentials",
        "session",
        "session_id",
        "otp",
        "pin",
        "dsn",
        "database_url",
    }
)

FINANCIAL_KEYS = frozenset(
    {
        "amount",
        "gross_amount",
        "net_amount",
        "balance",
        "quantity",
        "unit_price",
        "price",
        "value",
        "market_value",
        "net_worth",
        "fee",
        "fees",
        "tax",
        "taxes",
        "income",
        "salary",
        "holdings",
        "total",
        "target_amount",
        "contribution",
        "principal",
    }
)


def _normalise(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def is_sensitive_key(key: str) -> bool:
    k = _normalise(key)
    return any(k == w or k.endswith("_" + w) for w in CREDENTIAL_KEYS | FINANCIAL_KEYS)


_CRED_WORDS = "|".join(sorted((re.escape(w) for w in CREDENTIAL_KEYS), key=len, reverse=True))
_FIN_WORDS = "|".join(sorted((re.escape(w) for w in FINANCIAL_KEYS), key=len, reverse=True))

_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*")
_URL_CREDENTIALS = re.compile(r"(?<=://)([^/\s:@]*):([^/\s@]+)@")
_KV_CREDENTIAL = re.compile(
    rf"""(?ix)
    (["']?\b(?:[a-z0-9]+[_-])*(?:{_CRED_WORDS})["']?\s*[:=]\s*)
    (["']?)
    [^\s"',;&}}\]]+
    """
)
_KV_FINANCIAL = re.compile(
    rf"""(?ix)
    (["']?\b(?:[a-z0-9]+[_-])*(?:{_FIN_WORDS})["']?\s*[:=]\s*)
    (["']?)
    -?\d[\d,]*(?:\.\d+)?
    """
)


def scrub_text(text: str) -> str:
    text = _URL_CREDENTIALS.sub(rf"\1:{REDACTED}@", text)
    text = _JWT.sub(REDACTED, text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = _KV_CREDENTIAL.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return _KV_FINANCIAL.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)


def redact(value: Any, key: str | None = None, _depth: int = 0) -> Any:
    """Return a redacted copy of `value`. `key` is the mapping key it was found under."""
    if key is not None and is_sensitive_key(key):
        return REDACTED
    if _depth >= _MAX_DEPTH:
        return REDACTED
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, Mapping):
        return {str(k): redact(v, str(k), _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(v, None, _depth + 1) for v in value]
    return value
