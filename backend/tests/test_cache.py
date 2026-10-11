"""The analytics response cache (P06-T09): storage, failures and the invalidation middleware."""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from pydantic import BaseModel
from redis.exceptions import RedisError
from starlette.types import Message, Receive, Scope, Send

from app.core.cache import InvalidationMiddleware, MemoryCacheStore, ResponseCache

USER = uuid.UUID(int=7)


class Out(BaseModel):
    n: int


class Counter:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> Callable[[], Awaitable[Out]]:
        async def compute() -> Out:
            self.calls += 1
            return Out(n=self.calls)

        return compute


async def test_memory_store_expires_and_counts() -> None:
    now = [100.0]
    store = MemoryCacheStore(clock=lambda: now[0])
    await store.set("k", b"v", 10)
    assert await store.get("k") == b"v"
    now[0] = 110.0
    assert await store.get("k") is None
    assert [await store.incr("g"), await store.incr("g")] == [1, 2]
    assert await store.get("g") == b"2"  # like Redis INCR: readable as a value
    now[0] = 1e12
    assert await store.get("g") == b"2"  # counters do not expire


async def test_hits_parameters_and_invalidation() -> None:
    cache, count = ResponseCache(MemoryCacheStore(), 60), Counter()
    assert (await cache.cached(USER, "a", {"p": 1}, Out, count())).n == 1
    assert (await cache.cached(USER, "a", {"p": 1}, Out, count())).n == 1  # hit
    assert (await cache.cached(USER, "a", {"p": 2}, Out, count())).n == 2  # other parameters
    assert (await cache.cached(USER, "b", {"p": 1}, Out, count())).n == 3  # other name
    assert (await cache.cached(uuid.UUID(int=8), "a", {"p": 1}, Out, count())).n == 4  # other user
    await cache.invalidate(USER)
    assert (await cache.cached(USER, "a", {"p": 1}, Out, count())).n == 5
    assert (await cache.cached(uuid.UUID(int=8), "a", {"p": 1}, Out, count())).n == 4  # untouched


async def test_failures_are_not_cached() -> None:
    cache = ResponseCache(MemoryCacheStore(), 60)

    async def boom() -> Out:
        raise LookupError("not found")

    with pytest.raises(LookupError):
        await cache.cached(USER, "a", {}, Out, boom)
    count = Counter()
    assert (await cache.cached(USER, "a", {}, Out, count())).n == 1


async def test_without_a_store_everything_is_computed() -> None:
    cache, count = ResponseCache(None, 60), Counter()
    await cache.invalidate(USER)
    assert [(await cache.cached(USER, "a", {}, Out, count())).n for _ in range(2)] == [1, 2]


class BrokenStore:
    def __init__(self, fail_on: set[str]) -> None:
        self.fail_on = fail_on
        self.inner = MemoryCacheStore()

    async def get(self, key: str) -> bytes | None:
        if "get" in self.fail_on:
            raise RedisError("down")
        return await self.inner.get(key)

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        if "set" in self.fail_on:
            raise RedisError("down")
        await self.inner.set(key, value, ttl_seconds)

    async def incr(self, key: str) -> int:
        if "incr" in self.fail_on:
            raise RedisError("down")
        return await self.inner.incr(key)


@pytest.mark.parametrize("fail_on", [{"get"}, {"set"}, {"incr"}])
async def test_a_redis_outage_computes_without_the_cache(
    fail_on: set[str], caplog: pytest.LogCaptureFixture
) -> None:
    cache, count = ResponseCache(BrokenStore(fail_on), 60), Counter()
    first = await cache.cached(USER, "a", {}, Out, count())
    await cache.invalidate(USER)  # never raises
    assert first.n == 1
    assert "analytics cache" in caplog.text or fail_on == {"incr"}


# ------------------------------------------------------------------------------------ middleware


class Spy:
    def __init__(self) -> None:
        self.invalidated: list[uuid.UUID] = []

    async def invalidate(self, user_id: uuid.UUID) -> None:
        self.invalidated.append(user_id)


def app_answering(
    status: int, user: uuid.UUID | None
) -> Callable[[Scope, Receive, Send], Awaitable[None]]:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if user is not None:
            scope.setdefault("state", {})["user_id"] = user
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return app


async def run(method: str, path: str, status: int, user: uuid.UUID | None) -> tuple[Spy, list[str]]:
    spy, order = Spy(), []
    middleware = InvalidationMiddleware(app_answering(status, user), spy)  # type: ignore[arg-type]

    async def send(message: Message) -> None:
        order.append(f"{message['type']}:{len(spy.invalidated)}")

    async def receive() -> Message:
        return {"type": "http.request"}

    await middleware({"type": "http", "method": method, "path": path}, receive, send)
    return spy, order


async def test_a_successful_write_invalidates_before_the_response() -> None:
    spy, order = await run("POST", "/api/v1/portfolios", 201, USER)
    assert spy.invalidated == [USER]
    assert order[0] == "http.response.start:1"  # invalidated before the client hears back


@pytest.mark.parametrize(
    ("method", "path", "status", "user"),
    [
        ("GET", "/api/v1/dashboard", 200, USER),  # a read
        ("POST", "/api/v1/portfolios", 422, USER),  # a failed write
        ("DELETE", "/api/v1/goals/x", 404, USER),
        ("POST", "/api/v1/forecasts/compound", 200, USER),  # computes, stores nothing
        ("POST", "/api/v1/portfolios", 201, None),  # no signed-in user
    ],
)
async def test_nothing_else_invalidates(
    method: str, path: str, status: int, user: uuid.UUID | None
) -> None:
    spy, _ = await run(method, path, status, user)
    assert spy.invalidated == []


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
async def test_every_write_method_invalidates(method: str) -> None:
    spy, _ = await run(method, "/api/v1/goals/x", 204, USER)
    assert spy.invalidated == [USER]


async def test_other_scopes_pass_through() -> None:
    seen = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    middleware = InvalidationMiddleware(app, Spy())  # type: ignore[arg-type]
    await middleware({"type": "lifespan"}, None, None)  # type: ignore[arg-type]
    assert seen == ["lifespan"]


class FakeRedis:
    """The three Redis calls the store uses; `decoded` mimics decode_responses=True."""

    def __init__(self, decoded: bool = False) -> None:
        self.data: dict[str, object] = {}
        self.expiries: dict[str, int] = {}
        self.decoded = decoded

    async def get(self, key: str) -> object:
        value = self.data.get(key)
        return value.decode() if self.decoded and isinstance(value, bytes) else value

    async def set(self, key: str, value: bytes, ex: int) -> None:
        self.data[key] = value
        self.expiries[key] = ex

    async def incr(self, key: str) -> int:
        current = self.data.get(key, b"0")
        value = int(current) + 1 if isinstance(current, bytes) else 1
        self.data[key] = str(value).encode()
        return value


@pytest.mark.parametrize("decoded", [False, True])
async def test_redis_store(decoded: bool) -> None:
    from app.core.cache import RedisCacheStore

    fake = FakeRedis(decoded)
    store = RedisCacheStore(fake)  # type: ignore[arg-type]
    assert await store.get("missing") is None
    await store.set("k", b"value", 300)
    assert await store.get("k") == b"value" and fake.expiries["k"] == 300
    assert [await store.incr("g"), await store.incr("g")] == [1, 2]
    cache, count = ResponseCache(store, 300), Counter()
    assert (await cache.cached(USER, "a", {}, Out, count())).n == 1
    assert (await cache.cached(USER, "a", {}, Out, count())).n == 1
