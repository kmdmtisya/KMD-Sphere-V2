"""Response cache for analytics (P06-T09): Redis, with per-user generations for invalidation.

- Keys are `ws:an:<user id>:<generation>:<name>:<hash of the parameters>`, so a cached answer is
  only ever read for the user who caused it, and only successful answers are stored (the routes
  authorise before anything is computed or cached).
- Every successful write by a user (`InvalidationMiddleware`) increments that user's generation
  before the response is sent, so the next read misses and recomputes: ledger postings and
  reversals, valuations, liabilities, goals and portfolio changes all invalidate.
- Entries also expire after `analytics_cache_seconds`, which bounds how long figures that depend
  on the clock or on market data (the latest FX rates) can be served unchanged.
- If Redis fails, requests are computed without the cache (logged); nothing is served stale
  beyond the TTL.
"""

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

KEY_PREFIX = "ws:an:"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Writes that change no stored data (forecasts are computed from the request alone).
NOT_DATA_WRITES = ("/api/v1/forecasts/",)


class CacheStore(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None: ...
    async def incr(self, key: str) -> int: ...


class RedisCacheStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> bytes | None:
        value = await self._redis.get(key)
        if value is None or isinstance(value, bytes):
            return value
        return str(value).encode()  # a client configured to decode responses

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        await self._redis.set(key, value, ex=ttl_seconds)

    async def incr(self, key: str) -> int:
        return int(await self._redis.incr(key))


class MemoryCacheStore:
    """Per-process store for tests and local runs without Redis."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._values: dict[str, tuple[bytes, float]] = {}

    async def get(self, key: str) -> bytes | None:
        entry = self._values.get(key)
        if entry is None or entry[1] <= self._clock():
            self._values.pop(key, None)
            return None
        return entry[0]

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        self._values[key] = (value, self._clock() + ttl_seconds)

    async def incr(self, key: str) -> int:
        """Like Redis INCR: the counter is an ordinary value (readable with `get`), kept
        without expiry."""
        current = await self.get(key)
        value = int(current or b"0") + 1
        self._values[key] = (str(value).encode(), float("inf"))
        return value

    def keys(self) -> list[str]:
        return list(self._values)


class ResponseCache:
    def __init__(self, store: CacheStore | None, ttl_seconds: int) -> None:
        self._store = store
        self._ttl = ttl_seconds

    async def cached[M: BaseModel](
        self,
        user_id: uuid.UUID,
        name: str,
        params: dict[str, Any],
        model: type[M],
        compute: Callable[[], Awaitable[M]],
    ) -> M:
        """The cached answer for this user, name and parameters, or `compute()` (stored when
        it succeeds). Exceptions from `compute` propagate and nothing is stored."""
        if self._store is None:
            return await compute()
        try:
            generation = await self._store.get(_generation_key(user_id))
            key = _key(user_id, (generation or b"0").decode(), name, params)
            hit = await self._store.get(key)
        except RedisError:
            logger.warning("analytics cache unavailable; computing without it")
            return await compute()
        if hit is not None:
            return model.model_validate_json(hit)
        result = await compute()
        try:
            await self._store.set(key, result.model_dump_json().encode(), self._ttl)
        except RedisError:
            logger.warning("analytics cache unavailable; result not stored")
        return result

    async def invalidate(self, user_id: uuid.UUID) -> None:
        if self._store is None:
            return
        try:
            await self._store.incr(_generation_key(user_id))
        except RedisError:
            logger.error("analytics cache invalidation failed; entries expire within the TTL")


def _generation_key(user_id: uuid.UUID) -> str:
    return f"{KEY_PREFIX}{user_id}:generation"


def _key(user_id: uuid.UUID, generation: str, name: str, params: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()
    return f"{KEY_PREFIX}{user_id}:{generation}:{name}:{digest[:32]}"


class InvalidationMiddleware:
    """Invalidates the signed-in user's analytics after a successful write, before the response
    is sent (so a read that follows the response never sees the old figures)."""

    def __init__(self, app: ASGIApp, cache: ResponseCache) -> None:
        self.app = app
        self.cache = cache

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in WRITE_METHODS
            or scope["path"].startswith(NOT_DATA_WRITES)
        ):
            await self.app(scope, receive, send)
            return

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start" and 200 <= message["status"] < 300:
                user_id = scope.get("state", {}).get("user_id")
                if user_id is not None:
                    await self.cache.invalidate(user_id)
            await send(message)

        await self.app(scope, receive, wrapped)
