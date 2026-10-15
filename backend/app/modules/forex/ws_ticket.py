"""Single-use tickets for the forex WebSocket (P14-T13.2, ADR-0018).

A browser must not hold the access token (the web portal keeps it server-side), and a token must
never be in a URL. So the portal asks the API, on the user's behalf, for a ticket: a random value
that stands for the already-verified identity for 30 seconds and one use. The browser opens the
socket and sends `{"type": "auth", "ticket": "..."}` as its first message; the API redeems the
ticket (atomically, so a second use fails) and gets the same claims the token carried, with the
token's own expiry (a ticket never extends a session).

Only a hash of the ticket is stored. Redis is used when it is configured, so any API instance can
redeem a ticket minted by another; the in-memory store serves a single process (development, tests).
"""

import hashlib
import json
import secrets
import time
from collections.abc import Callable
from typing import Protocol

from redis.asyncio import Redis

from app.core.auth import TokenClaims

TTL_SECONDS = 30
_PREFIX = "forex-ws-ticket:"


class TicketStore(Protocol):
    async def put(self, key: str, value: str, ttl_seconds: int) -> None: ...

    async def take(self, key: str) -> str | None:
        """Returns the value and removes it, or None when absent or expired (one use only)."""
        ...


class MemoryTicketStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._items: dict[str, tuple[float, str]] = {}

    async def put(self, key: str, value: str, ttl_seconds: int) -> None:
        now = self._clock()
        self._items = {k: v for k, v in self._items.items() if v[0] > now}
        self._items[key] = (now + ttl_seconds, value)

    async def take(self, key: str) -> str | None:
        item = self._items.pop(key, None)
        if item is None or item[0] <= self._clock():
            return None
        return item[1]


class RedisTicketStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def put(self, key: str, value: str, ttl_seconds: int) -> None:
        await self._redis.set(_PREFIX + key, value, ex=ttl_seconds)

    async def take(self, key: str) -> str | None:
        value = await self._redis.getdel(_PREFIX + key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)


def _key(ticket: str) -> str:
    return hashlib.sha256(ticket.encode()).hexdigest()


class TicketIssuer:
    def __init__(self, store: TicketStore, clock: Callable[[], float] = time.time) -> None:
        self._store = store
        self._clock = clock

    async def mint(self, claims: TokenClaims) -> str:
        """A new ticket for these (already verified) claims."""
        ticket = secrets.token_urlsafe(32)
        payload = json.dumps(
            {
                "issuer": claims.issuer,
                "subject": claims.subject,
                "email": claims.email,
                "email_verified": claims.email_verified,
                "authorized_party": claims.authorized_party,
                "roles": sorted(claims.roles),
                "expires_at": claims.expires_at,
            }
        )
        await self._store.put(_key(ticket), payload, TTL_SECONDS)
        return ticket

    async def redeem(self, ticket: str) -> TokenClaims | None:
        """The claims the ticket stands for, once; None for an unknown, used or expired ticket."""
        raw = await self._store.take(_key(ticket))
        if raw is None:
            return None
        data = json.loads(raw)
        if data["expires_at"] <= self._clock():
            return None  # the token it came from has run out
        return TokenClaims(
            issuer=data["issuer"],
            subject=data["subject"],
            email=data["email"],
            email_verified=data["email_verified"],
            authorized_party=data["authorized_party"],
            roles=frozenset(data["roles"]),
            expires_at=data["expires_at"],
        )
