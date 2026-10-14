"""Timeframe aggregation (P13-T03.3, design section 4.5): complete one-minute candles into any
higher timeframe, 5m to 1M, on the session calendar.

Nothing is invented:
- A period is built only from one-minute candles that exist. Minutes with no candle (a feed gap, a
  provider outage) stay missing: the result says how many were present (`source_count`) and how
  many a full period holds (`expected_count`), and is marked `partial` when some are missing.
- Periods with no candle at all are absent: a weekend, or an outage that covered the period.
- Candles stamped inside the closed weekend are not used; they are counted in `ignored_closed`.
- A period still open at `as_of` is returned with `forming=True` and must not be treated as final.
- Open is the first present candle's open, close the last present candle's close, high and low
  the extremes, volume the sum (or None if any contributing candle has none)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.modules.forex.candles.sessions import bucket_end, bucket_start, expected_candles, is_open
from app.modules.forex.marketdata.types import Candle, Timeframe
from app.modules.market_data.providers.errors import ProviderDataError


@dataclass(frozen=True)
class AggregatedCandle:
    ts: datetime  # period start (UTC)
    end: datetime  # period end (UTC, exclusive)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    source_count: int
    expected_count: int
    forming: bool

    @property
    def missing(self) -> int:
        return self.expected_count - self.source_count

    @property
    def partial(self) -> bool:
        return self.source_count < self.expected_count


@dataclass(frozen=True)
class Aggregation:
    candles: list[AggregatedCandle]
    ignored_closed: int  # candles stamped while the market is closed, not used


def aggregate(source: Sequence[Candle], target: Timeframe, as_of: datetime) -> Aggregation:
    """Aggregate complete one-minute candles of one pair, provider and price basis into `target`.
    Raises `ProviderDataError` for mixed pairs, a non-minute timeframe, or duplicate minutes."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must carry a time zone")
    if target is Timeframe.M1:
        raise ValueError("the source is already one-minute candles")
    keys = {(c.provider, c.instrument, c.price_basis, c.data_type) for c in source}
    if len(keys) > 1:
        raise ProviderDataError("candles of different pairs, providers, bases or data types")
    buckets: dict[datetime, list[Candle]] = {}
    seen: set[datetime] = set()
    ignored = 0
    for c in sorted(source, key=lambda x: x.ts):
        if c.timeframe is not Timeframe.M1 or c.ts.second or c.ts.microsecond:
            raise ProviderDataError("aggregation needs candles on whole minutes")
        if c.ts in seen:
            raise ProviderDataError("duplicate candle for one minute")
        seen.add(c.ts)
        if not c.complete:
            continue  # a forming minute is not final
        if not is_open(c.ts):
            ignored += 1
            continue
        buckets.setdefault(bucket_start(c.ts, target), []).append(c)
    out = []
    for start in sorted(buckets):
        members = buckets[start]
        end = bucket_end(start, target)
        volumes = [m.volume for m in members]
        out.append(
            AggregatedCandle(
                ts=start,
                end=end,
                open=members[0].open,
                high=max(m.high for m in members),
                low=min(m.low for m in members),
                close=members[-1].close,
                volume=None
                if any(v is None for v in volumes)
                else sum(v for v in volumes if v is not None),
                source_count=len(members),
                expected_count=expected_candles(start, target),
                forming=end > as_of,
            )
        )
    return Aggregation(out, ignored)
