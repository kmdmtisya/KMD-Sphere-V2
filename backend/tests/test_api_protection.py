"""API protection (P04-T05): rate limits, body size limits, security headers and CORS."""

import logging
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.types import Message

from app.core.config import Settings
from app.core.http_protection import API_CSP, HSTS, BodySizeLimitMiddleware
from app.core.ratelimit import (
    FallbackCounterStore,
    MemoryCounterStore,
    Policies,
    RateLimit,
    RateLimiter,
    RedisCounterStore,
)
from app.main import create_app
from tests import auth_helpers as ah
from tests.conftest import make_settings
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.security

# --------------------------------------------------------------------------- unit: counters


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_memory_counters_count_within_a_window_and_reset_after_it() -> None:
    clock = FakeClock()
    store = MemoryCounterStore(clock)
    assert await store.hit("k", 60) == (1, 60)
    clock.now += 10
    assert await store.hit("k", 60) == (2, 50)
    assert await store.peek("k") == (2, 50)
    clock.now += 50
    assert await store.peek("k") == (0, 0)
    assert await store.hit("k", 60) == (1, 60)


async def test_memory_counters_stay_bounded() -> None:
    clock = FakeClock()
    store = MemoryCounterStore(clock)
    store.MAX_KEYS = 10
    for i in range(25):
        await store.hit(f"k{i}", 60)
    assert len(store._counters) <= 10


async def test_the_limiter_allows_up_to_the_limit_then_refuses_with_retry_after() -> None:
    clock = FakeClock()
    limiter = RateLimiter(MemoryCounterStore(clock))
    rule = RateLimit("t", limit=3, window_seconds=30)
    assert [(await limiter.hit(rule, "a")).allowed for _ in range(4)] == [True, True, True, False]
    clock.now += 12
    refused = await limiter.hit(rule, "a")
    assert not refused.allowed and refused.retry_after == 18
    assert (await limiter.hit(rule, "b")).allowed  # budgets are per subject
    assert not (await limiter.check(rule, "a")).allowed
    clock.now += 18
    assert (await limiter.check(rule, "a")).allowed


async def test_redis_errors_fall_back_to_per_process_limits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class DownStore:
        async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
            raise RedisConnectionError("down")

        async def peek(self, key: str) -> tuple[int, int]:
            raise RedisConnectionError("down")

    limiter = RateLimiter(FallbackCounterStore(DownStore()))
    rule = RateLimit("t", limit=2, window_seconds=60)
    with caplog.at_level(logging.WARNING):
        results = [(await limiter.hit(rule, "a")).allowed for _ in range(3)]
        assert not (await limiter.check(rule, "a")).allowed
    assert results == [True, True, False]  # still limited, never unlimited
    warnings = [r for r in caplog.records if "redis unavailable" in r.getMessage()]
    assert len(warnings) == 1  # logged once, not per request


def test_auth_budgets_are_stricter_than_general_ones() -> None:
    p = Policies.from_settings(Settings(_env_file=None))

    def per_minute(rule: RateLimit) -> float:
        return rule.limit * 60 / rule.window_seconds

    assert per_minute(p.auth) < per_minute(p.user) < per_minute(p.ip)
    assert per_minute(p.auth_failures) < per_minute(p.user)


@pytest.mark.integration
async def test_redis_counters_share_a_window_and_expire() -> None:
    settings = Settings(environment="test")
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1)
    try:
        await redis.ping()
    except Exception:
        await redis.aclose()
        pytest.skip("redis not reachable")
    store = RedisCounterStore(redis)
    key = f"ws:rl:test:{uuid.uuid4().hex}"
    try:
        assert await store.peek(key) == (0, 0)
        assert await store.hit(key, 30) == (1, 30)
        count, ttl = await store.hit(key, 30)
        assert count == 2 and 0 < ttl <= 30
        count, ttl = await store.peek(key)
        assert count == 2 and 0 < ttl <= 30
    finally:
        await redis.delete(key)
        await redis.aclose()


# ---------------------------------------------------------------------------- app: limits


def _app(**overrides: Any) -> FastAPI:
    application = create_app(make_settings(**overrides), readiness_checks={})

    @application.get("/api/v1/auth/_ping")
    async def auth_ping() -> dict[str, str]:
        return {"ok": "auth"}

    @application.get("/api/v1/_ping")
    async def ping() -> dict[str, str]:
        return {"ok": "general"}

    @application.post("/api/v1/_echo")
    async def echo(body: dict[str, Any]) -> dict[str, int]:
        return {"keys": len(body)}

    return application


@pytest.fixture
def client_at() -> Callable[[FastAPI, str], httpx.AsyncClient]:
    def build(application: FastAPI, ip: str = "203.0.113.7") -> httpx.AsyncClient:
        transport = httpx.ASGITransport(
            app=application, raise_app_exceptions=False, client=(ip, 50000)
        )
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    return build


def _assert_429(r: httpx.Response) -> None:
    assert r.status_code == 429
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"].endswith("/rate-limited")
    assert int(r.headers["Retry-After"]) >= 1
    assert r.headers["X-Correlation-ID"] == r.json()["correlation_id"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"


async def test_exceeding_the_general_limit_returns_429_with_retry_after(
    client_at: Callable[..., httpx.AsyncClient],
) -> None:
    app = _app(rate_limit_ip_requests=3, rate_limit_ip_window_seconds=60)
    async with client_at(app) as c:
        assert [(await c.get("/api/v1/_ping")).status_code for _ in range(3)] == [200] * 3
        r = await c.get("/api/v1/_ping")
        _assert_429(r)
        assert int(r.headers["Retry-After"]) <= 60
    async with client_at(app, "198.51.100.9") as other:
        assert (await other.get("/api/v1/_ping")).status_code == 200  # per client IP


async def test_auth_routes_have_a_stricter_budget(
    client_at: Callable[..., httpx.AsyncClient],
) -> None:
    app = _app(rate_limit_auth_requests=2, rate_limit_ip_requests=10)
    async with client_at(app) as c:
        assert (await c.get("/api/v1/auth/_ping")).status_code == 200
        assert (await c.get("/api/v1/auth/_ping")).status_code == 200
        _assert_429(await c.get("/api/v1/auth/_ping"))
        assert (await c.get("/api/v1/_ping")).status_code == 200  # general budget untouched


async def test_repeated_authentication_failures_block_the_client(
    client_at: Callable[..., httpx.AsyncClient],
) -> None:
    app = _app(rate_limit_auth_failures=3, rate_limit_auth_failure_window_seconds=300)
    async with client_at(app) as c:
        for _ in range(3):
            r = await c.get("/api/v1/me", headers=ah.bearer("not-a-token"))
            assert r.status_code == 401
        blocked = await c.get("/api/v1/_ping")  # every request, not only authenticated ones
        _assert_429(blocked)
        assert 1 <= int(blocked.headers["Retry-After"]) <= 300
    async with client_at(app, "198.51.100.9") as other:
        assert (await other.get("/api/v1/_ping")).status_code == 200


async def test_probes_are_never_rate_limited(
    client_at: Callable[..., httpx.AsyncClient],
) -> None:
    app = _app(rate_limit_ip_requests=1)
    async with client_at(app) as c:
        assert all([(await c.get("/health/live")).status_code == 200 for _ in range(5)])


async def test_limits_can_be_disabled(client_at: Callable[..., httpx.AsyncClient]) -> None:
    app = _app(rate_limit_enabled=False, rate_limit_ip_requests=1)
    async with client_at(app) as c:
        assert [(await c.get("/api/v1/_ping")).status_code for _ in range(3)] == [200] * 3


# ------------------------------------------------------------------- per-account budget


@pytest.fixture(scope="module")
async def db_app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    settings = migrated_settings.model_copy(
        update={"rate_limit_user_requests": 2, "rate_limit_ip_requests": 100}
    )
    application = create_app(settings, readiness_checks={}, token_verifier=ah.verifier())
    yield application
    await application.state.db.dispose()


@pytest.mark.integration
async def test_each_account_has_its_own_budget(
    db_app: FastAPI, client_at: Callable[..., httpx.AsyncClient]
) -> None:
    alice = ah.bearer(ah.token(f"alice-{uuid.uuid4()}"))
    bob = ah.bearer(ah.token(f"bob-{uuid.uuid4()}"))
    async with client_at(db_app) as c:
        assert (await c.get("/api/v1/me", headers=alice)).status_code == 200
        assert (await c.get("/api/v1/me", headers=alice)).status_code == 200
        _assert_429(await c.get("/api/v1/me", headers=alice))
        assert (await c.get("/api/v1/me", headers=bob)).status_code == 200


# ----------------------------------------------------------------------------- body size


async def test_bodies_over_the_limit_are_refused_by_content_length(
    client_at: Callable[..., httpx.AsyncClient],
) -> None:
    app = _app(max_request_body_bytes=64)
    async with client_at(app) as c:
        ok = await c.post("/api/v1/_echo", json={"a": 1})
        assert ok.status_code == 200
        r = await c.post("/api/v1/_echo", json={"a": "x" * 100})
        assert r.status_code == 413
        assert r.headers["content-type"].startswith("application/problem+json")
        assert r.headers["X-Content-Type-Options"] == "nosniff"


async def test_streamed_bodies_over_the_limit_are_refused(
    client_at: Callable[..., httpx.AsyncClient],
) -> None:
    app = _app(max_request_body_bytes=64)

    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"a": "'
        for _ in range(10):
            yield b"x" * 20
        yield b'"}'

    async with client_at(app) as c:
        r = await c.post(
            "/api/v1/_echo", content=chunks(), headers={"Content-Type": "application/json"}
        )
        assert "content-length" not in r.request.headers  # really streamed
        assert r.status_code == 413
        assert r.headers["content-type"].startswith("application/problem+json")


async def test_a_malformed_content_length_is_refused() -> None:
    sent: list[Message] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        raise AssertionError("must not reach the app")

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/_echo",
        "headers": [(b"content-length", b"-1")],
        "state": {},
    }
    await BodySizeLimitMiddleware(app, max_bytes=64)(scope, receive, send)
    assert sent[0]["status"] == 413


# ------------------------------------------------------------------------------- headers


async def test_security_headers_are_on_every_response(
    client_at: Callable[..., httpx.AsyncClient],
) -> None:
    app = _app()
    async with client_at(app) as c:
        for r in (
            await c.get("/api/v1/_ping"),
            await c.get("/api/v1/me"),  # 401
            await c.get("/api/v1/nothing-here"),  # 404
        ):
            h = r.headers
            assert h["X-Content-Type-Options"] == "nosniff", r.url
            assert h["X-Frame-Options"] == "DENY"
            assert h["Referrer-Policy"] == "no-referrer"
            assert h["Content-Security-Policy"] == API_CSP
            assert h["Cache-Control"] == "no-store"
            assert h["Cross-Origin-Resource-Policy"] == "same-origin"
            assert "Strict-Transport-Security" not in h  # local/test is plain HTTP


async def test_swagger_ui_is_not_blocked_by_the_api_csp(
    client_at: Callable[..., httpx.AsyncClient],
) -> None:
    async with client_at(_app()) as c:
        r = await c.get("/docs")
        assert r.status_code == 200
        assert "Content-Security-Policy" not in r.headers
        assert r.headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize("environment", ["staging", "production"])
async def test_deployed_environments_send_hsts(
    environment: str, client_at: Callable[..., httpx.AsyncClient]
) -> None:
    async with client_at(_app(environment=environment)) as c:
        r = await c.get("/health/live")
        assert r.headers["Strict-Transport-Security"] == HSTS


# ---------------------------------------------------------------------------------- CORS


async def test_cors_is_off_by_default(client_at: Callable[..., httpx.AsyncClient]) -> None:
    async with client_at(_app()) as c:
        r = await c.options(
            "/api/v1/_ping",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in r.headers


async def test_cors_allows_only_configured_origins(
    client_at: Callable[..., httpx.AsyncClient],
) -> None:
    app = _app(cors_allowed_origins=["https://app.wealthsphere.example"])
    async with client_at(app) as c:
        ok = await c.get("/api/v1/_ping", headers={"Origin": "https://app.wealthsphere.example"})
        assert ok.headers["access-control-allow-origin"] == "https://app.wealthsphere.example"
        assert "access-control-allow-credentials" not in ok.headers
        evil = await c.get("/api/v1/_ping", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in evil.headers


@pytest.mark.parametrize("origin", ["*", "https://*.example.com", "http://app.example.com"])
def test_wildcard_or_plain_http_origins_are_rejected(origin: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(cors_allowed_origins=[origin])
