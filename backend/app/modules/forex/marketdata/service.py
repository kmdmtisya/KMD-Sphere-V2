"""The quote board (P13-T02.5): the latest usable quote of each pair, with its true age and the
feed's status. A pair without one is `unavailable` and carries no price at all."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.forex.marketdata.gateway import QuoteHub
from app.modules.forex.marketdata.quality import Freshness, QualityPolicy, age, freshness
from app.modules.forex.marketdata.repository import StoredQuote, latest_quotes
from app.modules.forex.marketdata.schemas import QuoteOut
from app.modules.forex.marketdata.types import FeedStatus, Quality, ReceivedQuote


def from_received(r: ReceivedQuote) -> StoredQuote:
    q = r.quote
    return StoredQuote(
        q.provider,
        q.instrument,
        q.bid,
        q.ask,
        q.mid,
        q.ts_provider,
        r.ts_received,
        q.data_type.value,
        r.quality.value,
        r.feed_status.value,
    )


def feed_status_of(hub: QuoteHub | None, provider: str) -> FeedStatus:
    """Disconnected unless a feed in this process says otherwise."""
    if hub is None:
        return FeedStatus.DISCONNECTED
    return hub.feed_status.get(provider, FeedStatus.DISCONNECTED)


def quote_out(
    instrument: str,
    stored: StoredQuote | None,
    now: datetime,
    policy: QualityPolicy,
    feed: FeedStatus,
) -> QuoteOut:
    fresh = freshness(stored.ts_provider if stored else None, now, policy)
    if stored is None or fresh is Freshness.UNAVAILABLE:
        return QuoteOut(
            instrument=instrument,
            provider=None,
            bid=None,
            ask=None,
            mid=None,
            ts_provider=None,
            ts_received=None,
            age_seconds=None,
            data_type=None,
            quality=None,
            freshness=Freshness.UNAVAILABLE.value,
            feed_status=feed.value,
        )
    stale = fresh is Freshness.STALE or stored.quality == Quality.STALE.value
    return QuoteOut(
        instrument=instrument,
        provider=stored.provider,
        bid=stored.bid,
        ask=stored.ask,
        mid=stored.mid,
        ts_provider=stored.ts_provider,
        ts_received=stored.ts_received,
        age_seconds=int(age(stored.ts_provider, now) // timedelta(seconds=1)),
        data_type=stored.data_type,
        quality="stale" if stale else "ok",
        freshness=Freshness.STALE.value if stale else Freshness.FRESH.value,
        feed_status=feed.value,
    )


async def quote_board(
    session: AsyncSession,
    provider: str,
    instruments: Sequence[str],
    now: datetime,
    policy: QualityPolicy,
    lookback: timedelta,
    hub: QuoteHub | None,
) -> list[QuoteOut]:
    stored = await latest_quotes(session, provider, instruments, now - lookback)
    feed = feed_status_of(hub, provider)
    return [quote_out(i, stored.get(i), now, policy, feed) for i in instruments]
