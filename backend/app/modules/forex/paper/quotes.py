"""The stored quotes paper trading reads (P13-T09.2): the latest tradable-side quote, the quotes
after a time in order, and the conversion rates as of a time. Suspect quotes are never used; a
missing quote is never invented."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.forex.marketdata.models import ForexQuote
from app.modules.forex.paper.book import Tick
from app.modules.forex.risk.conversion import Rate

MAX_TICKS = 20_000  # quotes evaluated per order or position per pass


def _tick(q: ForexQuote) -> Tick:
    return Tick(q.ts_provider, q.bid, q.ask, q.data_type)


async def latest_tick(
    session: AsyncSession, provider: str, instrument: str, at: datetime, max_age: timedelta
) -> Tick | None:
    """The newest usable quote at `at`, no older than `max_age`."""
    q = await session.scalar(
        select(ForexQuote)
        .where(
            ForexQuote.provider == provider,
            ForexQuote.instrument == instrument,
            ForexQuote.ts_provider <= at,
            ForexQuote.ts_provider >= at - max_age,
            ForexQuote.quality != "suspect",
        )
        .order_by(ForexQuote.ts_provider.desc())
        .limit(1)
    )
    if q is None or q.ask < q.bid:
        return None
    return _tick(q)


async def ticks_after(
    session: AsyncSession, provider: str, instrument: str, after: datetime, until: datetime
) -> list[Tick]:
    rows = (
        await session.execute(
            select(ForexQuote)
            .where(
                ForexQuote.provider == provider,
                ForexQuote.instrument == instrument,
                ForexQuote.ts_provider > after,
                ForexQuote.ts_provider <= until,
                ForexQuote.quality != "suspect",
            )
            .order_by(ForexQuote.ts_provider)
            .limit(MAX_TICKS)
        )
    ).scalars()
    return [_tick(q) for q in rows if q.ask >= q.bid]


async def rates_at(
    session: AsyncSession,
    provider: str,
    instruments: list[str],
    indicative: set[str],
    at: datetime,
    lookback: timedelta,
) -> dict[str, Rate]:
    """Each pair's newest mid at `at` (within `lookback`), for converting P/L at that time."""
    rows = (
        await session.execute(
            select(ForexQuote)
            .where(
                ForexQuote.provider == provider,
                ForexQuote.instrument.in_(instruments),
                ForexQuote.ts_provider <= at,
                ForexQuote.ts_provider >= at - lookback,
                ForexQuote.quality != "suspect",
            )
            .order_by(ForexQuote.instrument, ForexQuote.ts_provider.desc())
            .ext(distinct_on(ForexQuote.instrument))
        )
    ).scalars()
    out = {}
    for q in rows:
        if q.mid > 0:
            types = {q.data_type} | ({"indicative_rate"} if q.instrument in indicative else set())
            out[q.instrument] = Rate(q.mid, q.ts_provider, frozenset(types))
    return out
