import base64
import json
import logging
import sys

import pytest

from app.core.logging import CorrelationIdFilter, JsonFormatter
from app.core.redaction import REDACTED, is_sensitive_key, redact, scrub_text


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# Built at runtime so the repository contains no JWT-shaped literal for secret scanners to flag.
JWT = ".".join(
    [
        _b64(b'{"alg":"RS256","typ":"JWT"}'),
        _b64(b'{"sub":"test-user","iss":"https://issuer.invalid"}'),
        _b64(b"not-a-real-signature-value"),
    ]
)


@pytest.mark.parametrize(
    ("text", "leaked"),
    [
        (f"Authorization: Bearer {JWT}", JWT),
        ("auth header Bearer abcdef0123456789xyz", "abcdef0123456789xyz"),
        (f"token {JWT} expired", JWT),
        ("connect failed postgresql://wealth:Sup3rS3cret@db.internal:5432/app", "Sup3rS3cret"),
        ("redis://:r3d1s-pass@cache:6379/0 refused", "r3d1s-pass"),
        ("password=hunter2 rejected", "hunter2"),
        ('{"password": "hunter2", "user": "ann"}', "hunter2"),
        ("db_password: 'correct horse battery'", "correct"),
        ("GET /cb?access_token=abc123def456&state=x", "abc123def456"),
        ("client_secret=s3cr3t-value&grant_type=code", "s3cr3t-value"),
        ("api_key=AKIA-NOT-REAL-12345 used", "AKIA-NOT-REAL-12345"),
        ('{"amount": "1234.56", "currency": "USD"}', "1234.56"),
        ("posting amount=987654.32 for portfolio", "987654.32"),
        ('{"balance": 1500000, "net_worth": 2400000.5}', "1500000"),
        ("unit_price: 175.43 quantity: 1,200", "175.43"),
    ],
)
def test_text_scrubbing_removes_secrets_and_amounts(text: str, leaked: str) -> None:
    assert leaked not in scrub_text(text)
    assert REDACTED in scrub_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "readiness check failed",
        "GET /health/ready 200",
        "portfolio 7f9c1b2e created",
        "request completed in 12 ms",
        "user signed in",
    ],
)
def test_ordinary_text_is_untouched(text: str) -> None:
    assert scrub_text(text) == text


@pytest.mark.parametrize(
    "key",
    ["password", "Authorization", "access_token", "x-api-key", "db_password", "Set-Cookie",
     "amount", "gross_amount", "net_worth", "Balance", "unit_price", "total_value", "holdings"],
)  # fmt: skip
def test_sensitive_keys_detected(key: str) -> None:
    assert is_sensitive_key(key)


@pytest.mark.parametrize(
    "key", ["path", "status", "correlation_id", "method", "duration_ms", "check"]
)
def test_operational_keys_not_flagged(key: str) -> None:
    assert not is_sensitive_key(key)


def test_structured_redaction_is_recursive_and_type_agnostic() -> None:
    data = {
        "user": "ann",
        "amount": 1234.56,
        "nested": {
            "password": "p",
            "items": [{"token": "t", "ok": "fine"}, "Bearer abcdef0123456789"],
        },
        "tags": ("a", "b"),
    }
    out = redact(data)
    assert out["user"] == "ann"
    assert out["amount"] == REDACTED
    assert out["nested"]["password"] == REDACTED
    assert out["nested"]["items"][0] == {"token": REDACTED, "ok": "fine"}
    assert "abcdef0123456789" not in json.dumps(out)
    assert out["tags"] == ["a", "b"]


def test_redact_does_not_mutate_input_and_caps_depth() -> None:
    original = {"a": {"password": "x"}}
    redact(original)
    assert original == {"a": {"password": "x"}}
    deep: dict[str, object] = {}
    cursor = deep
    for _ in range(20):
        nxt: dict[str, object] = {}
        cursor["n"] = nxt
        cursor = nxt
    assert REDACTED in json.dumps(redact(deep))


def _format(record: logging.LogRecord) -> dict[str, object]:
    CorrelationIdFilter().filter(record)
    parsed: dict[str, object] = json.loads(JsonFormatter().format(record))
    return parsed


def test_log_message_and_extra_fields_are_redacted() -> None:
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "login failed password=%s for %s", ("hunter2", "ann"), None
    )
    record.amount = "99999.99"
    record.token = JWT
    record.path = "/api/v1/portfolios"
    payload = _format(record)
    raw = json.dumps(payload)
    assert "hunter2" not in raw
    assert "99999.99" not in raw
    assert JWT not in raw
    assert payload["path"] == "/api/v1/portfolios"
    assert payload["message"] == f"login failed password={REDACTED} for ann"


def test_exception_text_is_scrubbed() -> None:
    try:
        raise ConnectionError("could not connect to postgresql://wealth:Sup3rS3cret@db:5432/app")
    except ConnectionError:
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "db down", (), sys.exc_info())
    raw = json.dumps(_format(record))
    assert "Sup3rS3cret" not in raw
    assert "ConnectionError" in raw


def test_end_to_end_log_line_never_contains_secret(capsys: pytest.CaptureFixture[str]) -> None:
    from app.core.logging import configure_logging

    configure_logging("INFO")
    logging.getLogger("audit").warning(
        "posted transaction", extra={"amount": "1,000,000.00", "authorization": f"Bearer {JWT}"}
    )
    err = capsys.readouterr().err
    assert "posted transaction" in err
    assert "1,000,000.00" not in err
    assert JWT not in err
