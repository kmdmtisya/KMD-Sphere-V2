"""Rate limiting: fixed-window counters in Redis, with an in-process fallback.

Three budgets protect the API (limits come from Settings):

- **auth**: requests to authentication routes (`AUTH_PATH_PREFIXES`), per client IP. The strictest.
- **auth_failures**: failed authentications (401 responses), per client IP. Once spent, every
  request from that IP gets 429 until the window ends, so bearer tokens cannot be guessed.
- **ip**: every other API request, per client IP; a coarse flood ceiling.
- **user**: every authenticated request, per verified subject (`enforce_user_limit`, called by
  `current_user`), so one account cannot monopolise the API whichever IPs it uses.

Exceeding a budget returns 429 problem+json with `Retry-After` (whole seconds). If Redis is
unavailable, limits are kept per process in memory instead (limits still apply, approximately),
and the outage is logged; requests are never let through unlimited.
Passwords are never sent to this API: Keycloak's brute-force detection protects sign-in.
"""

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from fastapi import Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import problem_response

logger = logging.getLogger(__name__)

AUTH_PATH_PREFIXES: tuple[str, ...] = ("/api/v1/auth/",)
EXEMPT_PATH_PREFIXES: tuple[str, ...] = ("/health", "/metrics")
KEY_PREFIX = "ws:rl:"


@dataclass(frozen=True)
class RateLimit:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int


class RateLimitedError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("rate limited")
        self.retry_after = retry_after


class CounterStore(Protocol):
    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Counts one request; returns (count in the current window, seconds until it ends)."""

    async def peek(self, key: str) -> tuple[int, int]:
        """Current (count, seconds until the window ends) without counting."""


_HIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


class RedisCounterStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._script = redis.register_script(_HIT_SCRIPT)

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        count, ttl = await self._script(keys=[key], args=[window_seconds])
        return int(count), int(ttl)

    async def peek(self, key: str) -> tuple[int, int]:
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.get(key)
            pipe.ttl(key)
            value, ttl = await pipe.execute()
        return (int(value) if value is not None else 0), max(int(ttl), 0)


class MemoryCounterStore:
    """Per-process counters, used in tests and while Redis is unavailable."""

    MAX_KEYS = 50_000

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._counters: dict[str, tuple[int, float]] = {}

    def _live(self, key: str) -> tuple[int, float] | None:
        entry = self._counters.get(key)
        if entry is not None and entry[1] <= self._clock():
            del self._counters[key]
            return None
        return entry

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        now = self._clock()
        entry = self._live(key)
        if entry is None:
            if len(self._counters) >= self.MAX_KEYS:
                self._prune(now)
            entry = (0, now + window_seconds)
        count, expires = entry[0] + 1, entry[1]
        self._counters[key] = (count, expires)
        return count, max(1, int(expires - now + 0.999))

    async def peek(self, key: str) -> tuple[int, int]:
        entry = self._live(key)
        if entry is None:
            return 0, 0
        return entry[0], max(1, int(entry[1] - self._clock() + 0.999))

    def _prune(self, now: float) -> None:
        for k in [k for k, (_, exp) in self._counters.items() if exp <= now]:
            del self._counters[k]
        if len(self._counters) >= self.MAX_KEYS:  # still full: drop the oldest windows
            for k in sorted(self._counters, key=lambda k: self._counters[k][1])[
                : len(self._counters) // 2
            ]:
                del self._counters[k]


class FallbackCounterStore:
    """Redis first; on a Redis error, the in-memory store (logged at most once a minute)."""

    def __init__(
        self,
        primary: CounterStore,
        fallback: CounterStore | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or MemoryCounterStore()
        self._clock = clock
        self._last_warning = -float("inf")

    def _warn(self, exc: Exception) -> None:
        if self._clock() - self._last_warning >= 60:
            self._last_warning = self._clock()
            logger.warning(
                "rate limiter: redis unavailable, using per-process limits",
                extra={"error": type(exc).__name__},
            )

    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        try:
            return await self._primary.hit(key, window_seconds)
        except (RedisError, OSError) as e:
            self._warn(e)
            return await self._fallback.hit(key, window_seconds)

    async def peek(self, key: str) -> tuple[int, int]:
        try:
            return await self._primary.peek(key)
        except (RedisError, OSError) as e:
            self._warn(e)
            return await self._fallback.peek(key)


class RateLimiter:
    def __init__(self, store: CounterStore) -> None:
        self._store = store

    @staticmethod
    def _key(limit: RateLimit, subject: str) -> str:
        digest = hashlib.sha256(subject.encode()).hexdigest()[:32]  # no raw IPs or ids in Redis
        return f"{KEY_PREFIX}{limit.name}:{digest}"

    async def hit(self, limit: RateLimit, subject: str) -> Decision:
        count, ttl = await self._store.hit(self._key(limit, subject), limit.window_seconds)
        return Decision(count <= limit.limit, max(ttl, 1))

    async def check(self, limit: RateLimit, subject: str) -> Decision:
        """Whether budget is left, without spending any."""
        count, ttl = await self._store.peek(self._key(limit, subject))
        return Decision(count < limit.limit, max(ttl, 1))


@dataclass(frozen=True)
class Policies:
    auth: RateLimit
    auth_failures: RateLimit
    ip: RateLimit
    user: RateLimit

    @classmethod
    def from_settings(cls, settings: Settings) -> "Policies":
        s = settings
        return cls(
            auth=RateLimit("auth", s.rate_limit_auth_requests, s.rate_limit_auth_window_seconds),
            auth_failures=RateLimit(
                "auth_failures",
                s.rate_limit_auth_failures,
                s.rate_limit_auth_failure_window_seconds,
            ),
            ip=RateLimit("ip", s.rate_limit_ip_requests, s.rate_limit_ip_window_seconds),
            user=RateLimit("user", s.rate_limit_user_requests, s.rate_limit_user_window_seconds),
        )


def client_ip(scope: Scope) -> str:
    """The direct peer. Behind a proxy, run uvicorn with --proxy-headers and --forwarded-allow-ips
    so this is the real client; X-Forwarded-For is never trusted here."""
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


class RateLimitMiddleware:
    """Per-IP limits (auth routes, failed authentications, general ceiling) before routing."""

    def __init__(self, app: ASGIApp, limiter: RateLimiter, policies: Policies) -> None:
        self.app = app
        self.limiter = limiter
        self.policies = policies

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or path.startswith(EXEMPT_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return
        ip = client_ip(scope)
        blocked = await self.limiter.check(self.policies.auth_failures, ip)
        if not blocked.allowed:
            await too_many_requests(scope, blocked.retry_after)(scope, receive, send)
            return
        policy = self.policies.auth if path.startswith(AUTH_PATH_PREFIXES) else self.policies.ip
        decision = await self.limiter.hit(policy, ip)
        if not decision.allowed:
            await too_many_requests(scope, decision.retry_after)(scope, receive, send)
            return

        async def send_counting_failures(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] == 401:
                await self.limiter.hit(self.policies.auth_failures, ip)
            await send(message)

        await self.app(scope, receive, send_counting_failures)


def too_many_requests(scope: Scope, retry_after: int) -> JSONResponse:
    return problem_response(
        scope,
        429,
        "rate-limited",
        "Too Many Requests",
        "Too many requests. Try again later.",
        headers={"Retry-After": str(retry_after)},
    )


async def enforce_user_limit(request: Request, subject: str) -> None:
    """Per-account budget for authenticated requests. Raises RateLimitedError when spent."""
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    policies: Policies | None = getattr(request.app.state, "rate_limit_policies", None)
    if limiter is None or policies is None:
        return
    decision = await limiter.hit(policies.user, subject)
    if not decision.allowed:
        raise RateLimitedError(decision.retry_after)
