"""Training from stored data (P13-T05): loads the pair's closed bars for the horizon's timeframe
(provider candles, or aggregated one-minute candles), marks bars inside economic-event risk
windows, runs the pipeline and records the result. Insufficient history publishes nothing."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.modules.forex.analysis.service import Loaded, load
from app.modules.forex.calendar.models import ForexEconomicEvent
from app.modules.forex.calendar.risk import pair_currencies, windows
from app.modules.forex.candles.sessions import bucket_end
from app.modules.forex.forecast import pipeline
from app.modules.forex.forecast.store import blocked, record
from app.modules.forex.instruments.models import ForexInstrument
from app.modules.forex.marketdata.types import PriceBasis

# How far back to look for the bars of each horizon's timeframe.
ALL_BARS = 1_000_000
LOOKBACK = {
    "15m": timedelta(days=14),
    "1h": timedelta(days=45),
    "4h": timedelta(days=200),
    "24h": timedelta(days=900),
    "1w": timedelta(days=3650),
}


@dataclass(frozen=True)
class Outcome:
    instrument: str
    horizon: str
    result: str  # published, disabled (drift), skipped (blocked), insufficient_history
    detail: str = ""


async def _event_flags(session: AsyncSession, instrument: str, ends: list[datetime]) -> list[bool]:
    if not ends:
        return []
    rows = (
        await session.execute(
            select(ForexEconomicEvent).where(
                ForexEconomicEvent.scheduled_at >= ends[0] - timedelta(hours=2),
                ForexEconomicEvent.scheduled_at <= ends[-1] + timedelta(hours=2),
            )
        )
    ).scalars()
    found = [w for w in windows(rows) if pair_currencies(instrument) & set(w.currencies)]
    # The bar's close is at its end; a window covering that moment marks the bar.
    return [any(w.contains(t) for w in found) for t in ends]


async def train(
    session: AsyncSession, settings: Settings, instrument: str, horizon: str, now: datetime
) -> Outcome:
    if await blocked(session, instrument, horizon):
        return Outcome(
            instrument, horizon, "skipped", "drift breached; retraining not yet approved"
        )
    spec = await session.get(ForexInstrument, instrument)
    if spec is None:
        raise ValueError("unknown instrument")
    timeframe, _ = pipeline.HORIZONS[horizon]

    async def fetch(start: datetime) -> Loaded:
        # No bar cap here: the loader keeps the oldest bars when it caps, and training needs the
        # most recent ones, so the newest `forex_forecast_max_bars` are taken below.
        return await load(
            session,
            settings.forex_provider,
            instrument,
            timeframe,
            PriceBasis.MID,
            start,
            now,
            now,
            ALL_BARS,
            settings.forex_analysis_source_cap,
        )

    try:
        loaded = await fetch(now - LOOKBACK[horizon])
    except InvalidValueError:
        # Too many one-minute candles to aggregate: use the most recent window that fits the cap.
        loaded = await fetch(now - timedelta(minutes=int(settings.forex_analysis_source_cap * 0.9)))
    bars = loaded.bars[-settings.forex_forecast_max_bars :]
    ends = [bucket_end(b.ts, timeframe) for b in bars]
    series = pipeline.Series(
        [b.ts for b in bars],
        [b.close for b in bars],
        [b.high for b in bars],
        [b.low for b in bars],
        await _event_flags(session, instrument, ends),
    )
    try:
        run = pipeline.run(series, horizon, spec.display_precision, settings.forex_forecast_seed)
    except pipeline.InsufficientHistory as error:
        return Outcome(instrument, horizon, "insufficient_history", str(error))
    version, forecast = await record(session, instrument, run, loaded.data_types, now)
    return Outcome(
        instrument, horizon, "published" if forecast is not None else "disabled", version.version
    )
