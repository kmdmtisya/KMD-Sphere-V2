"""The latest rate of every active currency against the pivot, with its status (P11-T03.4/.5).

Reads come from the database through a short-lived cache, never from a provider. The cache holds
the stored rows only; the status is computed on every read from the clock, so a cached row can
never be shown as more current than it is. A refresh invalidates the cache."""

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import CacheStore
from app.modules.fx.refresh import active_currencies
from app.modules.fx.status import RateStatus, StatusPolicy
from app.modules.market_data.models import FxRate

_GENERATION = "fx:board:generation"


@dataclass(frozen=True)
class StoredRate:
    currency: str
    rate: Decimal
    provider: str
    rate_type: str
    rate_timestamp: datetime
    retrieved_at: datetime
    path: list[str] | None


@dataclass(frozen=True)
class RateLine:
    """One currency against the pivot. Without any stored rate, everything but the currency and
    `unavailable` is empty."""

    currency: str
    status: RateStatus
    rate: Decimal | None = None
    provider: str | None = None
    rate_type: str | None = None
    rate_timestamp: datetime | None = None
    retrieved_at: datetime | None = None
    path: list[str] | None = None
    age_seconds: int | None = None


async def latest_against(
    session: AsyncSession, pivot: str, currencies: list[str]
) -> list[StoredRate]:
    rows = await session.execute(
        select(FxRate)
        .where(FxRate.base_currency == pivot, FxRate.quote_currency.in_(currencies))
        .ext(distinct_on(FxRate.quote_currency))
        .order_by(
            FxRate.quote_currency,
            FxRate.rate_timestamp.desc(),
            FxRate.retrieved_at.desc(),
            FxRate.provider,
        )
    )
    return [
        StoredRate(
            r.quote_currency,
            r.rate,
            r.provider,
            r.rate_type,
            r.rate_timestamp,
            r.retrieved_at,
            list(r.rate_path) if r.rate_path else None,
        )
        for r in rows.scalars()
    ]


def _encode(rows: list[StoredRate]) -> bytes:
    return json.dumps(
        [
            {
                "currency": r.currency,
                "rate": str(r.rate),
                "provider": r.provider,
                "rate_type": r.rate_type,
                "rate_timestamp": r.rate_timestamp.isoformat(),
                "retrieved_at": r.retrieved_at.isoformat(),
                "path": r.path,
            }
            for r in rows
        ]
    ).encode()


def _decode(raw: bytes) -> list[StoredRate]:
    return [
        StoredRate(
            d["currency"],
            Decimal(d["rate"]),
            d["provider"],
            d["rate_type"],
            datetime.fromisoformat(d["rate_timestamp"]),
            datetime.fromisoformat(d["retrieved_at"]),
            d["path"],
        )
        for d in json.loads(raw)
    ]


class RateBoard:
    def __init__(
        self,
        session: AsyncSession,
        policy: StatusPolicy,
        cache: CacheStore | None = None,
        cache_seconds: int = 60,
    ) -> None:
        self._session = session
        self._policy = policy
        self._cache = cache
        self._ttl = cache_seconds

    async def _key(self, pivot: str, currencies: list[str]) -> str | None:
        if self._cache is None or self._ttl <= 0:
            return None
        generation = await self._cache.get(_GENERATION)
        return f"fx:board:{(generation or b'0').decode()}:{pivot}:{','.join(currencies)}"

    async def stored(self, pivot: str, currencies: list[str]) -> list[StoredRate]:
        key = await self._key(pivot, currencies)
        if key is not None and self._cache is not None:
            hit = await self._cache.get(key)
            if hit is not None:
                return _decode(hit)
        rows = await latest_against(self._session, pivot, currencies)
        if key is not None and self._cache is not None:
            await self._cache.set(key, _encode(rows), self._ttl)
        return rows

    async def lines(self, pivot: str, now: datetime) -> list[RateLine]:
        currencies = [c for c in await active_currencies(self._session) if c != pivot]
        by_currency = {r.currency: r for r in await self.stored(pivot, currencies)}
        lines: list[RateLine] = []
        for currency in currencies:
            r = by_currency.get(currency)
            if r is None:
                lines.append(RateLine(currency, RateStatus.UNAVAILABLE))
                continue
            lines.append(
                RateLine(
                    currency,
                    self._policy.status(r.provider, r.rate_timestamp, now),
                    r.rate,
                    r.provider,
                    r.rate_type,
                    r.rate_timestamp,
                    r.retrieved_at,
                    r.path,
                    max(int((now - r.rate_timestamp).total_seconds()), 0),
                )
            )
        return lines


async def invalidate(cache: CacheStore | None) -> None:
    """Called after a refresh stored new rates."""
    if cache is not None:
        await cache.incr(_GENERATION)
