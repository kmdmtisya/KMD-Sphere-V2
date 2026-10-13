"""Reads and writes of the forex time series (P13-T02.3). Inserts only: a duplicate (same provider,
pair and time) is dropped by the primary key, so a replayed stream or backfill is harmless."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.forex.marketdata.models import ForexCandle, ForexQuote
from app.modules.forex.marketdata.types import Candle, PriceBasis, ReceivedQuote, Timeframe


@dataclass(frozen=True)
class StoredQuote:
    provider: str
    instrument: str
    bid: Decimal
    ask: Decimal
    mid: Decimal
    ts_provider: datetime
    ts_received: datetime
    data_type: str
    quality: str
    feed_status: str


def _stored(row: ForexQuote) -> StoredQuote:
    return StoredQuote(
        row.provider,
        row.instrument,
        row.bid,
        row.ask,
        row.mid,
        row.ts_provider,
        row.ts_received,
        row.data_type,
        row.quality,
        row.feed_status,
    )


CHUNK = 1000  # rows per statement, well under PostgreSQL's bind-parameter limit


async def _insert(
    session: AsyncSession, model: type[ForexQuote] | type[ForexCandle], rows: list[dict[str, Any]]
) -> int:
    """Inserts `rows`, dropping duplicates. Returns how many were new. Commits."""
    added = 0
    for i in range(0, len(rows), CHUNK):
        statement = insert(model).values(rows[i : i + CHUNK]).on_conflict_do_nothing()
        result = await session.execute(statement)
        added += max(result.rowcount or 0, 0)  # type: ignore[attr-defined]
    await session.commit()
    return added


async def store_quotes(session: AsyncSession, quotes: Sequence[ReceivedQuote]) -> int:
    if not quotes:
        return 0
    rows = [
        {
            "provider": r.quote.provider,
            "instrument": r.quote.instrument,
            "ts_provider": r.quote.ts_provider,
            "ts_received": r.ts_received,
            "bid": r.quote.bid,
            "ask": r.quote.ask,
            "data_type": r.quote.data_type.value,
            "quality": r.quality.value,
            "feed_status": r.feed_status.value,
        }
        for r in quotes
    ]
    return await _insert(session, ForexQuote, rows)


async def store_candles(
    session: AsyncSession, candles: Sequence[Candle], received: datetime
) -> int:
    """Stores complete candles; a forming candle is skipped (it would have to be rewritten)."""
    rows = [
        {
            "provider": c.provider,
            "instrument": c.instrument,
            "timeframe": c.timeframe.value,
            "price_basis": c.price_basis.value,
            "ts": c.ts,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "data_type": c.data_type.value,
            "ts_received": received,
        }
        for c in candles
        if c.complete
    ]
    if not rows:
        return 0
    return await _insert(session, ForexCandle, rows)


async def latest_quotes(
    session: AsyncSession, provider: str, instruments: Sequence[str], since: datetime
) -> dict[str, StoredQuote]:
    """The newest quote of each pair since `since` that is not suspect. A pair with none is
    absent: the caller reports it unavailable and shows no price."""
    if not instruments:
        return {}
    rows = (
        await session.execute(
            select(ForexQuote)
            .where(
                ForexQuote.provider == provider,
                ForexQuote.instrument.in_(list(instruments)),
                ForexQuote.ts_provider >= since,
                ForexQuote.quality != "suspect",
            )
            .order_by(ForexQuote.instrument, ForexQuote.ts_provider.desc())
            .ext(distinct_on(ForexQuote.instrument))
        )
    ).scalars()
    return {r.instrument: _stored(r) for r in rows}


async def stored_candles(
    session: AsyncSession,
    provider: str,
    instrument: str,
    timeframe: Timeframe,
    basis: PriceBasis,
    start: datetime,
    end: datetime,
    limit: int,
) -> list[ForexCandle]:
    return list(
        (
            await session.execute(
                select(ForexCandle)
                .where(
                    ForexCandle.provider == provider,
                    ForexCandle.instrument == instrument,
                    ForexCandle.timeframe == timeframe.value,
                    ForexCandle.price_basis == basis.value,
                    ForexCandle.ts >= start,
                    ForexCandle.ts < end,
                )
                .order_by(ForexCandle.ts)
                .limit(limit)
            )
        ).scalars()
    )


async def newest_candle(
    session: AsyncSession, provider: str, instrument: str, timeframe: Timeframe
) -> datetime | None:
    return await session.scalar(
        select(ForexCandle.ts)
        .where(
            ForexCandle.provider == provider,
            ForexCandle.instrument == instrument,
            ForexCandle.timeframe == timeframe.value,
        )
        .order_by(ForexCandle.ts.desc())
        .limit(1)
    )
