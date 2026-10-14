"""Loads candles for analysis (P13-T03): stored candles of the requested timeframe when the
provider published them, otherwise the stored one-minute candles aggregated on the session
calendar. Only closed periods are analysed; periods with missing minutes are kept and flagged."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidValueError
from app.modules.forex.candles.aggregate import aggregate
from app.modules.forex.candles.sessions import bucket_start
from app.modules.forex.marketdata.repository import stored_candles
from app.modules.forex.marketdata.types import Candle, DataType, PriceBasis, Timeframe


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    missing: int  # one-minute candles missing from this bar (0 for provider candles)
    source: str  # "provider" or "aggregated"


@dataclass(frozen=True)
class Loaded:
    bars: list[Bar]
    data_types: list[str]
    truncated: bool
    forming_excluded: int


async def load(
    session: AsyncSession,
    provider: str,
    instrument: str,
    timeframe: Timeframe,
    basis: PriceBasis,
    start: datetime,
    end: datetime,
    now: datetime,
    max_bars: int,
    source_cap: int,
) -> Loaded:
    native = await stored_candles(
        session, provider, instrument, timeframe, basis, start, end, max_bars + 1
    )
    if native or timeframe is Timeframe.M1:
        types = sorted({r.data_type for r in native})
        bars = [
            Bar(r.ts, r.open, r.high, r.low, r.close, r.volume, 0, "provider")
            for r in native[:max_bars]
        ]
        return Loaded(bars, types, len(native) > max_bars, 0)
    first = bucket_start(start, timeframe)
    rows = await stored_candles(
        session, provider, instrument, Timeframe.M1, basis, first, end, source_cap + 1
    )
    if len(rows) > source_cap:
        raise InvalidValueError(
            "too many one-minute candles in the range for this timeframe: ask for a shorter range"
        )
    minutes = [
        Candle(
            r.provider,
            r.instrument,
            Timeframe.M1,
            PriceBasis(r.price_basis),
            r.ts,
            r.open,
            r.high,
            r.low,
            r.close,
            r.volume,
            True,
            DataType(r.data_type),
        )
        for r in rows
    ]
    result = aggregate(minutes, timeframe, now)
    closed = [c for c in result.candles if not c.forming and start <= c.ts < end]
    forming = sum(1 for c in result.candles if c.forming and start <= c.ts < end)
    bars = [
        Bar(c.ts, c.open, c.high, c.low, c.close, c.volume, c.missing, "aggregated")
        for c in closed[:max_bars]
    ]
    types = sorted({m.data_type.value for m in minutes})
    return Loaded(bars, types, len(closed) > max_bars, forming)
