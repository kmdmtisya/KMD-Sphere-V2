import json
import logging

import httpx

from app.core.config import Settings
from app.core.correlation import correlation_id_var
from app.core.logging import CorrelationIdFilter, JsonFormatter
from tests.conftest import make_settings


def test_no_default_secrets() -> None:
    # The class defaults themselves (independent of any environment) must not contain secrets.
    fields = Settings.model_fields
    assert fields["postgres_password"].default.get_secret_value() == ""
    assert fields["redis_password"].default.get_secret_value() == ""
    assert fields["postgres_user"].default == ""


def test_secrets_are_masked_in_repr() -> None:
    s = make_settings(postgres_password="s3cret-value", redis_password="another-secret")
    assert "s3cret-value" not in repr(s)
    assert "another-secret" not in str(s)


def test_dsn_and_url_quote_special_characters() -> None:
    s = make_settings(
        postgres_user="user@x",
        postgres_password="p@ss:w/rd#1",
        postgres_db="db",
        redis_password="r@d:is",
    )
    assert s.database_dsn == "postgresql://user%40x:p%40ss%3Aw%2Frd%231@127.0.0.1:5433/db"
    assert s.redis_url == "redis://:r%40d%3Ais@127.0.0.1:6380/0"


def test_redis_url_without_password_has_no_auth() -> None:
    assert make_settings().redis_url == "redis://127.0.0.1:6380/0"


async def test_docs_are_disabled_in_production() -> None:
    from app.main import create_app

    app = create_app(make_settings(environment="production"), readiness_checks={})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/openapi.json")).status_code == 404
        assert (await c.get("/docs")).status_code == 404


def test_json_formatter_emits_valid_json_with_correlation_id() -> None:
    record = logging.LogRecord("x.y", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.custom = "extra-field"
    token = correlation_id_var.set("cid-42")
    try:
        CorrelationIdFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        correlation_id_var.reset(token)
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "x.y"
    assert payload["correlation_id"] == "cid-42"
    assert payload["custom"] == "extra-field"
    assert payload["ts"].endswith("+00:00")


def test_json_formatter_includes_exception() -> None:
    try:
        raise ValueError("bad")
    except ValueError:
        import sys

        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: bad" in payload["exception"]
