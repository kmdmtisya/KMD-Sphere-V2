"""Backtests from stored bars (P13-T08): the bars, the contract specification and the reports of
one pair, stored once per hash."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.modules.forex.analysis.service import Loaded, load
from app.modules.forex.backtest import runner
from app.modules.forex.backtest.store import save
from app.modules.forex.backtest.strategy import WINDOW
from app.modules.forex.instruments.models import ForexInstrument
from app.modules.forex.marketdata.types import PriceBasis, Timeframe
from app.modules.forex.risk.specs import active_spec, values_of
from app.modules.forex.signals import setups as su
from app.modules.forex.signals.service import STEP

ALL_BARS = 1_000_000


@dataclass(frozen=True)
class Outcome:
    instrument: str
    status: str  # "stored", "unchanged" or "skipped"
    detail: str
    reports: int = 0


async def pair_data(
    session: AsyncSession,
    settings: Settings,
    pair: ForexInstrument,
    timeframe: Timeframe,
    now: datetime,
) -> runner.PairData | None:
    spec = await active_spec(session, pair.code)
    if spec is None:
        return None

    async def fetch(start: datetime) -> Loaded:
        # No bar cap here: the loader keeps the oldest bars when it caps, and a backtest needs
        # the most recent ones, so the newest are taken below.
        return await load(
            session,
            settings.forex_provider,
            pair.code,
            timeframe,
            PriceBasis.MID,
            start,
            now,
            now,
            ALL_BARS,
            settings.forex_analysis_source_cap,
        )

    lookback = STEP[timeframe] * settings.forex_backtest_max_bars * 3 // 2  # weekends hold no bars
    try:
        loaded = await fetch(now - lookback)
    except InvalidValueError:
        # Too many one-minute candles to aggregate: the most recent window that fits the cap.
        loaded = await fetch(now - timedelta(minutes=int(settings.forex_analysis_source_cap * 0.9)))
    bars = loaded.bars[-settings.forex_backtest_max_bars :]
    return runner.PairData(
        instrument=pair.code,
        timeframe=timeframe.value,
        bars=su.Bars(
            [b.ts for b in bars],
            [b.open for b in bars],
            [b.high for b in bars],
            [b.low for b in bars],
            [b.close for b in bars],
        ),
        data_types=loaded.data_types,
        pip_location=pair.pip_location,
        display_precision=pair.display_precision,
        liquidity_tier=pair.liquidity_tier,
        spec=values_of(spec),
        spec_version=spec.version,
        spec_reviewed=spec.review_status == "reviewed",
    )


async def run_and_store(
    session: AsyncSession, settings: Settings, pair: ForexInstrument, now: datetime
) -> Outcome:
    timeframe = Timeframe(settings.forex_backtest_timeframe)
    data = await pair_data(session, settings, pair, timeframe, now)
    if data is None:
        return Outcome(pair.code, "skipped", "no contract specification")
    needed = WINDOW - 1 + runner.MIN_TRADABLE_BARS
    if len(data.bars) < needed:
        return Outcome(pair.code, "skipped", f"{len(data.bars)} bars stored, {needed} needed")
    reports = runner.run_pair(
        data,
        runner.Settings(seed=settings.forex_backtest_seed, folds=settings.forex_backtest_folds),
        now,
    )
    added = 0
    for report in reports:
        added += await save(session, report)
    return Outcome(
        pair.code, "stored" if added else "unchanged", f"{added} new of {len(reports)}", added
    )
