"""One-minute candle sync (P13-T03): fetches the provider's own one-minute candles for each
active pair since the newest stored one and stores the complete ones. A gap that a provider
outage leaves stays a gap; nothing is interpolated. The first run fetches at most
`max_span` of history. The provider is the `ForexProvider` interface, so a real vendor works the
same way as the simulated feed (DEC-19)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.forex.marketdata.provider import ForexProvider
from app.modules.forex.marketdata.repository import newest_candle, store_candles
from app.modules.forex.marketdata.types import PriceBasis, Timeframe
from app.modules.market_data.providers.errors import ProviderError

MINUTE = timedelta(minutes=1)


@dataclass(frozen=True)
class SyncReport:
    stored: int
    failed: list[str]


async def sync_minutes(
    session: AsyncSession,
    provider: ForexProvider,
    instruments: Sequence[str],
    now: datetime,
    max_span: timedelta = timedelta(hours=24),
) -> SyncReport:
    end = now.replace(second=0, microsecond=0)
    stored = 0
    failed: list[str] = []
    for code in instruments:
        newest = await newest_candle(session, provider.name, code, Timeframe.M1)
        start = max(newest + MINUTE if newest else end - max_span, end - max_span)
        if start >= end:
            continue
        try:
            candles = await provider.candles(code, Timeframe.M1, start, end, PriceBasis.MID)
        except ProviderError:
            failed.append(code)
            continue
        stored += await store_candles(session, candles, now)
    return SyncReport(stored, failed)
