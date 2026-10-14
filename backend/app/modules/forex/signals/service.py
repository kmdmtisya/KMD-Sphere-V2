"""Gathers what the ranking needs for each active pair (P13-T06): closed bars of the timeframe,
the latest fresh quote (spread), economic-event windows and the matching forecast."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.forex.analysis.service import load
from app.modules.forex.backtest.store import latest_by_rule
from app.modules.forex.calendar.models import ForexEconomicEvent
from app.modules.forex.calendar.risk import pair_currencies, windows
from app.modules.forex.forecast.store import ForexForecast, latest_version
from app.modules.forex.instruments.models import ForexInstrument
from app.modules.forex.marketdata.repository import latest_quotes
from app.modules.forex.marketdata.types import PriceBasis, Timeframe
from app.modules.forex.signals import setups as su
from app.modules.forex.signals.ranking import (
    Candidate,
    ForecastInput,
    PairInput,
    StrategyHistory,
    candidates,
)

STEP = {
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
}
# The forecast horizon that matches each signal timeframe.
HORIZON = {
    Timeframe.M5: "15m",
    Timeframe.M15: "1h",
    Timeframe.H1: "4h",
    Timeframe.H4: "24h",
    Timeframe.D1: "1w",
}
BARS = 200


async def _forecast(session: AsyncSession, instrument: str, horizon: str) -> ForecastInput | None:
    version = await latest_version(session, instrument, horizon)
    if version is None or version.status != "active":
        return None
    row = await session.scalar(
        select(ForexForecast)
        .where(ForexForecast.model_version_id == version.id)
        .order_by(ForexForecast.generated_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    return ForecastInput(
        horizon,
        row.prob_up,
        version.calibration_status == "calibrated",
        version.version,
        version.model_name,
    )


async def pair_candidates(
    session: AsyncSession,
    settings: Settings,
    spec: ForexInstrument,
    timeframe: Timeframe,
    now: datetime,
) -> list[Candidate]:
    step = STEP[timeframe]
    # Weekends hold no bars: look back far enough for BARS trading periods.
    loaded = await load(
        session,
        settings.forex_provider,
        spec.code,
        timeframe,
        PriceBasis.MID,
        now - step * BARS * 2,
        now,
        now,
        1_000_000,
        settings.forex_analysis_source_cap,
    )
    bars = loaded.bars[-BARS:]
    if len(bars) < su.MIN_BARS:
        return []
    quotes = await latest_quotes(
        session,
        settings.forex_provider,
        [spec.code],
        now - timedelta(days=settings.forex_quote_lookback_days),
    )
    q = quotes.get(spec.code)
    events = (
        await session.execute(
            select(ForexEconomicEvent).where(
                ForexEconomicEvent.scheduled_at >= now - timedelta(hours=2),
                ForexEconomicEvent.scheduled_at <= now + step + timedelta(hours=1),
            )
        )
    ).scalars()
    found = [w for w in windows(events) if pair_currencies(spec.code) & set(w.currencies)]
    return candidates(
        PairInput(
            instrument=spec.code,
            pip_location=spec.pip_location,
            display_precision=spec.display_precision,
            liquidity_tier=spec.liquidity_tier,
            bars=su.Bars(
                [b.ts for b in bars],
                [b.open for b in bars],
                [b.high for b in bars],
                [b.low for b in bars],
                [b.close for b in bars],
            ),
            bar_step=step,
            data_types=loaded.data_types,
            spread=(q.ask - q.bid) if q is not None and q.ask >= q.bid else None,
            quote_age=(now - q.ts_provider) if q is not None else None,
            windows=found,
            forecast=await _forecast(session, spec.code, HORIZON[timeframe]),
            now=now,
            history={
                rule: StrategyHistory(r.oos_trades, r.oos_profit_factor, tuple(r.data_types))
                for rule, r in (await latest_by_rule(session, spec.code, timeframe.value)).items()
            },
        ),
        settings.forex_signal_weights,
    )
