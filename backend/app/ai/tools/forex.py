"""The Forex Copilot's tools (P13-T10.1, design section 12). Read-only and allow-listed.

Each tool reads through the same code paths as the forex API and returns structured data with
its time (`as_of`), its source and data types, and, for a forecast, the model version and
calibration status. A stale or missing price is reported, never replaced: `complete` is false,
so the server qualifies the answer (QG-18.5).

Rules (docs/ai-governance.md section 1):
- registered only when forex is switched on (DEC-23); with it off the model has no forex tool;
- no tool changes anything. The Copilot cannot place or manage a trade, real or paper: it can
  only read the caller's paper results and point to the paper account;
- the only user data is the caller's own paper performance, scoped to `ToolContext.user_id`: an
  account id the model supplies is a request, and another user's answers "not found";
- research candidates are not recommendations, forecasts are not promises, and every simulated
  figure says so."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import any_, select

from app.ai.tools.base import Tool, ToolArguments, ToolContext, ToolData
from app.ai.tools.registry import ToolRegistry
from app.core.authz import ResourceNotFoundError
from app.core.config import Settings
from app.modules.forex.analysis.service import load
from app.modules.forex.backtest.store import ForexBacktestReport, latest_by_rule
from app.modules.forex.calendar.models import ForexEconomicEvent
from app.modules.forex.calendar.risk import windows
from app.modules.forex.forecast.pipeline import HORIZONS
from app.modules.forex.forecast.store import ForexForecast, ForexModelVersion, latest_version
from app.modules.forex.instruments.models import ForexInstrument
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.marketdata.factory import quality_policy
from app.modules.forex.marketdata.service import quote_board
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN, PriceBasis, Timeframe
from app.modules.forex.paper import analytics as paper_analytics
from app.modules.forex.paper.service import PaperService
from app.modules.forex.risk.schemas import ForexRiskRequest
from app.modules.forex.risk.service import calculate_trade
from app.modules.forex.signals import setups as su
from app.modules.forex.signals.ranking import rank
from app.modules.forex.signals.service import STEP, pair_candidates

D = Decimal
Instrument = Field(pattern=INSTRUMENT_PATTERN, description="A currency pair such as EUR_USD")
Frame = Literal["5m", "15m", "1H", "4H", "1D"]
Horizon = Literal["15m", "1h", "4h", "24h", "1w"]
SOURCE = "WealthSphere forex data (provider: {provider})"
RESEARCH = (
    "Research candidates ranked by a published formula: not recommendations to buy or sell and "
    "not probabilities of profit."
)
BARS = 200


def _q(value: Decimal | None, places: int = 8) -> str | None:
    if value is None:
        return None
    return format(value.quantize(D(1).scaleb(-places)).normalize(), "f")


async def _pair(ctx: ToolContext, code: str) -> ForexInstrument:
    pair = next((p for p in await active_instruments(ctx.session) if p.code == code), None)
    if pair is None:
        raise ResourceNotFoundError("forex instrument")
    return pair


async def _bars(
    ctx: ToolContext, settings: Settings, code: str, frame: Timeframe
) -> tuple[su.Bars, list[str]]:
    now = ctx.now()
    step = STEP[frame]
    loaded = await load(
        ctx.session,
        settings.forex_provider,
        code,
        frame,
        PriceBasis.MID,
        now - step * BARS * 2,
        now,
        now,
        1_000_000,
        settings.forex_analysis_source_cap,
    )
    bars = loaded.bars[-BARS:]
    return (
        su.Bars(
            [b.ts for b in bars],
            [b.open for b in bars],
            [b.high for b in bars],
            [b.low for b in bars],
            [b.close for b in bars],
        ),
        loaded.data_types,
    )


def _fresh_bars(bars: su.Bars, frame: Timeframe, now: datetime) -> bool:
    return bool(bars.ts) and now - (bars.ts[-1] + STEP[frame]) <= 2 * STEP[frame]


# ---------------------------------------------------------------------------------- quotes
class QuoteArguments(ToolArguments):
    instrument: str = Instrument


class QuoteResult(ToolData):
    instrument: str
    status: Literal["fresh", "stale", "unavailable"]
    bid: str | None
    ask: str | None
    mid: str | None
    spread_pips: str | None
    quote_time: datetime | None
    age_seconds: int | None
    data_type: str | None
    source: str


def quote_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: QuoteArguments) -> QuoteResult:
        pair = await _pair(ctx, args.instrument)
        now = ctx.now()
        (q,) = await quote_board(
            ctx.session,
            settings.forex_provider,
            [pair.code],
            now,
            quality_policy(settings),
            timedelta(days=settings.forex_quote_lookback_days),
            None,
        )
        spread = None
        if q.bid is not None and q.ask is not None:
            spread = (q.ask - q.bid) / D(1).scaleb(pair.pip_location)
        return QuoteResult(
            as_of=q.ts_provider or now,
            complete=q.freshness == "fresh",
            instrument=pair.code,
            status=q.freshness,
            bid=_q(q.bid),
            ask=_q(q.ask),
            mid=_q(q.mid),
            spread_pips=_q(spread, 1),
            quote_time=q.ts_provider,
            age_seconds=q.age_seconds,
            data_type=q.data_type,
            source=SOURCE.format(provider=settings.forex_provider),
        )

    return Tool(
        "get_forex_quote",
        "The latest stored bid, ask and mid of a currency pair with its time, age, freshness and "
        "data type (simulated, indicative or tradable). A stale or missing price is reported, "
        "never filled in.",
        QuoteArguments,
        QuoteResult,
        run,
    )


# --------------------------------------------------------------------------------- candles
class CandlesArguments(ToolArguments):
    instrument: str = Instrument
    timeframe: Frame = "1H"
    count: int = Field(default=50, ge=1, le=100, description="Most recent closed bars")


class CandleRow(BaseModel):
    start: datetime
    open_price: str
    high: str
    low: str
    close: str


class CandlesResult(ToolData):
    instrument: str
    timeframe: str
    bars: list[CandleRow]
    data_types: list[str]
    source: str


def candles_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: CandlesArguments) -> CandlesResult:
        pair = await _pair(ctx, args.instrument)
        frame = Timeframe(args.timeframe)
        bars, types = await _bars(ctx, settings, pair.code, frame)
        n = len(bars.ts)
        rows = [
            CandleRow(
                start=bars.ts[i],
                open_price=_q(bars.open[i]) or "",
                high=_q(bars.high[i]) or "",
                low=_q(bars.low[i]) or "",
                close=_q(bars.close[i]) or "",
            )
            for i in range(max(0, n - args.count), n)
        ]
        return CandlesResult(
            as_of=(bars.ts[-1] + STEP[frame]) if n else ctx.now(),
            complete=_fresh_bars(bars, frame, ctx.now()),
            instrument=pair.code,
            timeframe=frame.value,
            bars=rows,
            data_types=types,
            source=SOURCE.format(provider=settings.forex_provider),
        )

    return Tool(
        "get_candles",
        "The most recent closed price bars (open, high, low, close; mid prices) of a pair, up to "
        "100, with their data types. Times are the bar starts (UTC).",
        CandlesArguments,
        CandlesResult,
        run,
    )


# ------------------------------------------------------------------- indicators and structure
class AnalysisArguments(ToolArguments):
    instrument: str = Instrument
    timeframe: Frame = "1H"


class IndicatorsResult(ToolData):
    instrument: str
    timeframe: str
    bar_close_time: datetime | None
    values: dict[str, str | None]
    data_types: list[str]
    source: str
    method: str = (
        "Computed by WealthSphere's deterministic indicator library (financial-methods section 19)."
    )


def _last(series: Sequence[Decimal | None]) -> Decimal | None:
    return next((v for v in reversed(series) if v is not None), None)


def indicators_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: AnalysisArguments) -> IndicatorsResult:
        pair = await _pair(ctx, args.instrument)
        frame = Timeframe(args.timeframe)
        bars, types = await _bars(ctx, settings, pair.code, frame)
        if len(bars) < su.MIN_BARS:
            return IndicatorsResult(
                as_of=ctx.now(),
                complete=False,
                instrument=pair.code,
                timeframe=frame.value,
                bar_close_time=None,
                values={},
                data_types=types,
                source=SOURCE.format(provider=settings.forex_provider),
            )
        c = su.context(bars)
        values = {
            "close": c.bars.close[-1],
            "ema_20": _last(c.ema20),
            "ema_50": _last(c.ema50),
            "rsi_14": _last(c.rsi),
            "atr_14": _last(c.atr),
            "adx_14": _last(c.adx.adx),
            "plus_di_14": _last(c.adx.plus_di),
            "minus_di_14": _last(c.adx.minus_di),
            "macd": _last(c.macd.macd),
            "macd_signal": _last(c.macd.signal),
            "macd_histogram": _last(c.macd.histogram),
            "bollinger_upper": _last(c.bollinger.upper),
            "bollinger_middle": _last(c.bollinger.middle),
            "bollinger_lower": _last(c.bollinger.lower),
        }
        close_time = bars.ts[-1] + STEP[frame]
        return IndicatorsResult(
            as_of=close_time,
            complete=_fresh_bars(bars, frame, ctx.now()),
            instrument=pair.code,
            timeframe=frame.value,
            bar_close_time=close_time,
            values={k: _q(v, 6) for k, v in values.items()},
            data_types=types,
            source=SOURCE.format(provider=settings.forex_provider),
        )

    return Tool(
        "get_indicators",
        "The latest values of the standard indicators on a pair's closed bars: EMA 20 and 50, RSI "
        "14, ATR 14, ADX with +DI and -DI, MACD 12/26/9 and Bollinger 20/2, with the bar's close "
        "time. Read-only; computed by WealthSphere.",
        AnalysisArguments,
        IndicatorsResult,
        run,
    )


class Level(BaseModel):
    price: str
    touches: int
    last_touched: datetime


class StructureResult(ToolData):
    instrument: str
    timeframe: str
    bar_close_time: datetime | None
    levels: list[Level]
    recent_breakouts: list[dict[str, Any]]
    recent_patterns: list[dict[str, Any]]
    data_types: list[str]
    source: str


def structure_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: AnalysisArguments) -> StructureResult:
        pair = await _pair(ctx, args.instrument)
        frame = Timeframe(args.timeframe)
        bars, types = await _bars(ctx, settings, pair.code, frame)
        base = {
            "instrument": pair.code,
            "timeframe": frame.value,
            "data_types": types,
            "source": SOURCE.format(provider=settings.forex_provider),
        }
        if len(bars) < su.MIN_BARS:
            return StructureResult(
                as_of=ctx.now(),
                complete=False,
                bar_close_time=None,
                levels=[],
                recent_breakouts=[],
                recent_patterns=[],
                **base,
            )
        c = su.context(bars)
        n = len(bars)
        levels = [
            Level(
                price=_q(lv.price, 6) or "", touches=lv.touches, last_touched=bars.ts[lv.last_index]
            )
            for lv in sorted(c.levels, key=lambda lv: -lv.last_index)[:8]
        ]
        breakouts = [
            {
                "time": bars.ts[b.index].isoformat(),
                "direction": b.direction,
                "level": _q(b.level_price, 6),
            }
            for b in c.breakouts
            if b.index >= n - 20
        ][-5:]
        patterns = [
            {"time": bars.ts[p.end].isoformat(), "pattern": p.rule, "bias": p.bias}
            for p in c.patterns
            if p.end >= n - 10
        ][-5:]
        close_time = bars.ts[-1] + STEP[frame]
        return StructureResult(
            as_of=close_time,
            complete=_fresh_bars(bars, frame, ctx.now()),
            bar_close_time=close_time,
            levels=levels,
            recent_breakouts=breakouts,
            recent_patterns=patterns,
            **base,
        )

    return Tool(
        "get_market_structure",
        "Support and resistance levels, recent breakouts and recent candlestick patterns found "
        "by WealthSphere's published rules on a pair's closed bars.",
        AnalysisArguments,
        StructureResult,
        run,
    )


# -------------------------------------------------------------------------------- forecasts
class ForecastArguments(ToolArguments):
    instrument: str = Instrument
    horizon: Horizon = "1h"


class ForecastModel(BaseModel):
    name: str
    version: str
    trained_at: datetime
    calibration_status: str
    drift_status: str
    edge: bool
    data_types: list[str]


class ForecastResult(ToolData):
    instrument: str
    horizon: str
    status: Literal["available", "unavailable"]
    reason: str | None
    model: ForecastModel | None
    generated_at: datetime | None
    prob_up: str | None
    probability_label: str | None
    price_median: str | None
    price_interval_80: list[str] | None
    expected_volatility: str | None
    notice: str = (
        "A model forecast with its uncertainty, not a prediction of what will happen and not "
        "advice. Probabilities labelled 'Requires calibration' are not reliable."
    )


def _model(v: ForexModelVersion) -> ForecastModel:
    return ForecastModel(
        name=v.model_name,
        version=v.version,
        trained_at=v.trained_at,
        calibration_status=v.calibration_status,
        drift_status=v.drift_status,
        edge=v.edge,
        data_types=list(v.data_types),
    )


async def _latest_forecasts(
    ctx: ToolContext, version: ForexModelVersion, n: int
) -> list[ForexForecast]:
    rows = await ctx.session.execute(
        select(ForexForecast)
        .where(ForexForecast.model_version_id == version.id)
        .order_by(ForexForecast.generated_at.desc())
        .limit(n)
    )
    return list(rows.scalars())


def forecast_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: ForecastArguments) -> ForecastResult:
        pair = await _pair(ctx, args.instrument)
        version = await latest_version(ctx.session, pair.code, args.horizon)
        empty = {
            "generated_at": None,
            "prob_up": None,
            "probability_label": None,
            "price_median": None,
            "price_interval_80": None,
            "expected_volatility": None,
        }
        if version is None or version.status == "disabled":
            reason = (
                "no forecast yet"
                if version is None
                else "disabled: drift detected, retraining not approved"
            )
            return ForecastResult(
                as_of=ctx.now(),
                complete=False,
                instrument=pair.code,
                horizon=args.horizon,
                status="unavailable",
                reason=reason,
                model=_model(version) if version else None,
                **empty,
            )
        rows = await _latest_forecasts(ctx, version, 1)
        if not rows:
            return ForecastResult(
                as_of=ctx.now(),
                complete=False,
                instrument=pair.code,
                horizon=args.horizon,
                status="unavailable",
                reason="no forecast stored",
                model=_model(version),
                **empty,
            )
        row = rows[0]
        timeframe, _ = HORIZONS[args.horizon]
        fresh = ctx.now() - row.as_of <= STEP[timeframe] * 3 + timedelta(hours=1)
        p = [D(v) for v in row.price_quantiles]
        return ForecastResult(
            as_of=row.as_of,
            complete=fresh,
            instrument=pair.code,
            horizon=args.horizon,
            status="available",
            reason=None,
            model=_model(version),
            generated_at=row.generated_at,
            prob_up=_q(row.prob_up, 4),
            probability_label="Calibrated"
            if version.calibration_status == "calibrated"
            else "Requires calibration",
            price_median=_q(p[2], 6),
            price_interval_80=[_q(p[0], 6) or "", _q(p[4], 6) or ""],
            expected_volatility=_q(row.expected_volatility, 8),
        )

    return Tool(
        "get_forecast",
        "The latest published model forecast of a pair for a horizon: probability of a rise with "
        "its calibration label, the median and 80% price interval, expected volatility, the model "
        "name and version, when it was generated and whether it has a demonstrated edge.",
        ForecastArguments,
        ForecastResult,
        run,
    )


class ForecastChangeResult(ToolData):
    instrument: str
    horizon: str
    status: Literal["compared", "unavailable"]
    previous_generated_at: datetime | None
    latest_generated_at: datetime | None
    prob_up_previous: str | None
    prob_up_latest: str | None
    prob_up_change: str | None
    price_median_previous: str | None
    price_median_latest: str | None
    volatility_previous: str | None
    volatility_latest: str | None
    model_version: str | None
    model_changed: bool
    drift_status: str | None
    calibration_status: str | None


def forecast_change_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: ForecastArguments) -> ForecastChangeResult:
        pair = await _pair(ctx, args.instrument)
        rows = await ctx.session.execute(
            select(ForexForecast, ForexModelVersion)
            .join(ForexModelVersion, ForexModelVersion.id == ForexForecast.model_version_id)
            .where(ForexForecast.instrument == pair.code, ForexForecast.horizon == args.horizon)
            .order_by(ForexForecast.generated_at.desc())
            .limit(2)
        )
        found = list(rows.all())
        if len(found) < 2:
            return ForecastChangeResult(
                as_of=ctx.now(),
                complete=False,
                instrument=pair.code,
                horizon=args.horizon,
                status="unavailable",
                previous_generated_at=None,
                latest_generated_at=None,
                prob_up_previous=None,
                prob_up_latest=None,
                prob_up_change=None,
                price_median_previous=None,
                price_median_latest=None,
                volatility_previous=None,
                volatility_latest=None,
                model_version=None,
                model_changed=False,
                drift_status=None,
                calibration_status=None,
            )
        (new, new_v), (old, old_v) = found
        return ForecastChangeResult(
            as_of=new.as_of,
            instrument=pair.code,
            horizon=args.horizon,
            status="compared",
            previous_generated_at=old.generated_at,
            latest_generated_at=new.generated_at,
            prob_up_previous=_q(old.prob_up, 4),
            prob_up_latest=_q(new.prob_up, 4),
            prob_up_change=_q(new.prob_up - old.prob_up, 4),
            price_median_previous=_q(D(old.price_quantiles[2]), 6),
            price_median_latest=_q(D(new.price_quantiles[2]), 6),
            volatility_previous=_q(old.expected_volatility, 8),
            volatility_latest=_q(new.expected_volatility, 8),
            model_version=new_v.version,
            model_changed=new_v.id != old_v.id,
            drift_status=new_v.drift_status,
            calibration_status=new_v.calibration_status,
        )

    return Tool(
        "explain_forecast_change",
        "The two most recent forecasts of a pair for a horizon side by side: the probability of a "
        "rise, the median price and the volatility before and after, whether the model version "
        "changed, and its drift and calibration status. Facts to explain a change, nothing more.",
        ForecastArguments,
        ForecastChangeResult,
        run,
    )


# ---------------------------------------------------------------------------- opportunities
class OpportunitiesArguments(ToolArguments):
    timeframe: Frame = "1H"
    count: int = Field(default=5, ge=1, le=10)


class Candidate(BaseModel):
    rank: int
    instrument: str
    setup: str
    scenario: str
    score: str
    risk: str
    market_condition: str
    levels: dict[str, str]
    bar_close_time: datetime
    forecast_label: str | None
    data_types: list[str]


class OpportunitiesResult(ToolData):
    timeframe: str
    items: list[Candidate]
    excluded: int
    label: str = "Research candidate"
    notice: str = RESEARCH


def opportunities_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: OpportunitiesArguments) -> OpportunitiesResult:
        now = ctx.now()
        frame = Timeframe(args.timeframe)
        per_pair = [
            await pair_candidates(ctx.session, settings, p, frame, now)
            for p in await active_instruments(ctx.session)
        ]
        ranked, excluded = rank(per_pair)
        items = []
        for position, c in enumerate(ranked[: args.count], start=1):
            q = D(1).scaleb(-c.precision)
            items.append(
                Candidate(
                    rank=position,
                    instrument=c.instrument,
                    setup=c.setup.rule,
                    scenario="Bullish scenario"
                    if c.setup.direction == "bullish"
                    else "Bearish scenario",
                    score=_q(c.score, 1) or "0",
                    risk=c.risk,
                    market_condition=c.condition,
                    levels={
                        "entry": str(c.setup.entry.quantize(q)),
                        "stop": str(c.setup.stop.quantize(q)),
                        "target": str(c.setup.target.quantize(q)),
                    },
                    bar_close_time=c.setup.as_of + STEP[frame],
                    forecast_label=None
                    if c.forecast is None
                    else ("Calibrated" if c.forecast.calibrated else "Requires calibration"),
                    data_types=c.data_types,
                )
            )
        oldest = min((i.bar_close_time for i in items), default=now)
        return OpportunitiesResult(
            as_of=oldest, timeframe=frame.value, items=items, excluded=len(excluded)
        )

    return Tool(
        "get_opportunities",
        "The Opportunity Ranking: research candidates found by published setup rules, scored by "
        "a published formula, with illustrative levels, risk level and freshness. Not "
        "recommendations and not probabilities of profit.",
        OpportunitiesArguments,
        OpportunitiesResult,
        run,
    )


# ------------------------------------------------------------------------------- calendar
class EventsArguments(ToolArguments):
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    hours_ahead: int = Field(default=48, ge=1, le=168)


class EventRow(BaseModel):
    name: str
    currencies: list[str]
    importance: str
    scheduled_at: datetime
    unit: str | None
    forecast: str | None = Field(description="Consensus expectation, not a fact")
    previous: str | None
    actual: str | None
    source: str
    demo: bool


class EventsResult(ToolData):
    events: list[EventRow]
    risk_windows: list[dict[str, Any]]


def events_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: EventsArguments) -> EventsResult:
        now = ctx.now()
        query = select(ForexEconomicEvent).where(
            ForexEconomicEvent.scheduled_at >= now - timedelta(hours=2),
            ForexEconomicEvent.scheduled_at <= now + timedelta(hours=args.hours_ahead),
        )
        if args.currency is not None:
            query = query.where(any_(ForexEconomicEvent.currencies) == args.currency)
        rows = list(
            (
                await ctx.session.execute(query.order_by(ForexEconomicEvent.scheduled_at).limit(40))
            ).scalars()
        )
        found = windows(rows)
        return EventsResult(
            as_of=now,
            events=[
                EventRow(
                    name=r.name,
                    currencies=list(r.currencies),
                    importance=r.importance,
                    scheduled_at=r.scheduled_at,
                    unit=r.unit,
                    forecast=_q(r.forecast, 4),
                    previous=_q(r.previous, 4),
                    actual=_q(r.actual, 4),
                    source=r.source,
                    demo=r.is_demo,
                )
                for r in rows
            ],
            risk_windows=[
                {
                    "event": w.name,
                    "currencies": sorted(w.currencies),
                    "starts": w.starts.isoformat(),
                    "ends": w.ends.isoformat(),
                    "importance": w.importance,
                }
                for w in found
            ],
        )

    return Tool(
        "get_economic_events",
        "Scheduled economic events (from two hours ago up to a week ahead), optionally for one "
        "currency, with importance, forecast, previous and actual values, their source, and the "
        "event-risk windows around them.",
        EventsArguments,
        EventsResult,
        run,
    )


# ---------------------------------------------------------------------------- risk calculator
class RiskArguments(ToolArguments):
    instrument: str = Instrument
    direction: Literal["long", "short"]
    entry: Decimal
    stop: Decimal
    target: Decimal | None = None
    balance: Decimal = Field(gt=0, description="The user's stated account balance")
    account_currency: str = Field(pattern=r"^[A-Z]{3}$")
    risk_percent: Decimal = Field(gt=0, le=100)


class RiskResult(ToolData):
    calculation: dict[str, Any]


def risk_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: RiskArguments) -> RiskResult:
        out = await calculate_trade(
            ctx.session,
            settings,
            ForexRiskRequest(
                instrument=args.instrument,
                direction=args.direction,
                entry=args.entry,
                stop=args.stop,
                target=args.target,
                balance=args.balance,
                account_currency=args.account_currency,
                risk_percent=args.risk_percent,
            ),
            ctx.now(),
        )
        data = out.model_dump(mode="json")
        as_of = out.conversion.as_of or ctx.now()
        return RiskResult(as_of=as_of, complete=not out.conversion.stale, calculation=data)

    return Tool(
        "calculate_trade_risk",
        "The position-size and risk calculator for a hypothetical trade: size, pip value in the "
        "account currency, loss and profit before and after costs, risk/reward, margin, leverage, "
        "exposure, warnings and the disclosures. Nothing is placed or stored. Use the user's own "
        "entry, stop, balance and risk percent.",
        RiskArguments,
        RiskResult,
        run,
    )


# --------------------------------------------------------------------------------- backtests
class BacktestArguments(ToolArguments):
    instrument: str = Instrument
    timeframe: Literal["15m", "1H", "4H", "1D"] = "1H"


class BacktestRow(BaseModel):
    rule: str
    rule_version: int
    period_start: datetime
    period_end: datetime
    out_of_sample_trades: int
    out_of_sample_return: str
    out_of_sample_profit_factor: str | None
    leakage_audit_passed: bool
    report_hash: str
    data_types: list[str]


class BacktestResult(ToolData):
    instrument: str
    timeframe: str
    reports: list[BacktestRow]
    label: str = "backtested"
    notice: str = (
        "Backtested results of published rules on stored bars, net of modelled costs: a study, "
        "not a forecast. Results on simulated data say nothing about real markets."
    )


def backtest_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: BacktestArguments) -> BacktestResult:
        pair = await _pair(ctx, args.instrument)
        found = await latest_by_rule(ctx.session, pair.code, args.timeframe)
        rows: list[ForexBacktestReport] = sorted(found.values(), key=lambda r: r.rule)
        return BacktestResult(
            as_of=max((r.generated_at for r in rows), default=ctx.now()),
            complete=bool(rows),
            instrument=pair.code,
            timeframe=args.timeframe,
            reports=[
                BacktestRow(
                    rule=r.rule,
                    rule_version=r.rule_version,
                    period_start=r.period_start,
                    period_end=r.period_end,
                    out_of_sample_trades=r.oos_trades,
                    out_of_sample_return=_q(r.oos_return, 6) or "0",
                    out_of_sample_profit_factor=_q(r.oos_profit_factor, 2),
                    leakage_audit_passed=bool(r.report["leakage_audit"]["passed"]),
                    report_hash=r.report_hash,
                    data_types=list(r.data_types),
                )
                for r in rows
            ],
        )

    return Tool(
        "get_backtest_summary",
        "The latest stored backtest of each setup rule on a pair: walk-forward out-of-sample "
        "trades, return and profit factor net of costs, the period, and whether the leakage audit "
        "passed. Backtested results only.",
        BacktestArguments,
        BacktestResult,
        run,
    )


# --------------------------------------------------------------------------- paper results
class PaperArguments(ToolArguments):
    account_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F-]{36}$",
        description="One of the user's paper accounts; omitted: a summary of each",
    )


class PaperAccountRow(BaseModel):
    account_id: str
    name: str
    currency: str
    status: str
    starting_balance: str
    closed_trades: int
    net_pnl: str
    win_rate: str | None
    profit_factor: str | None
    max_drawdown: str
    return_on_starting_balance: str
    open_positions: int


class PaperResult(ToolData):
    accounts: list[PaperAccountRow]
    mode: str = "PAPER TRADING"
    notice: str = (
        "Paper results: virtual money and simulated fills, a separate series never combined with "
        "backtested results or any real portfolio. The Copilot cannot place or manage trades; "
        "the user can simulate one in a paper account."
    )


def paper_tool(settings: Settings) -> Tool:
    async def run(ctx: ToolContext, args: PaperArguments) -> PaperResult:
        service = PaperService(ctx.session, settings)
        if args.account_id is not None:
            import uuid as _uuid

            accounts = [await service.account(ctx.user_id, _uuid.UUID(args.account_id))]
        else:
            accounts = await service.accounts(ctx.user_id)
        rows = []
        for a in accounts[:10]:
            _, closed = await service.closed(ctx.user_id, a.id, ctx.now())
            perf = paper_analytics.performance(a.starting_balance, closed)
            rows.append(
                PaperAccountRow(
                    account_id=str(a.id),
                    name=a.name,
                    currency=a.currency,
                    status=a.status,
                    starting_balance=_q(a.starting_balance, 2) or "0",
                    closed_trades=perf.overall.trades,
                    net_pnl=_q(perf.overall.net, 2) or "0",
                    win_rate=_q(perf.overall.win_rate, 4),
                    profit_factor=_q(perf.overall.profit_factor, 2),
                    max_drawdown=_q(perf.max_drawdown, 4) or "0",
                    return_on_starting_balance=_q(perf.return_on_start, 4) or "0",
                    open_positions=len(await service.open_positions(a)),
                )
            )
        return PaperResult(as_of=ctx.now(), accounts=rows)

    return Tool(
        "get_paper_performance",
        "The user's own PAPER TRADING results: per paper account, closed trades, net P/L, win "
        "rate, profit factor, drawdown and open positions. Virtual money only.",
        PaperArguments,
        PaperResult,
        run,
    )


FOREX_TOOLS = (
    "get_forex_quote",
    "get_candles",
    "get_indicators",
    "get_market_structure",
    "get_forecast",
    "get_opportunities",
    "get_economic_events",
    "calculate_trade_risk",
    "get_backtest_summary",
    "get_paper_performance",
    "explain_forecast_change",
)


def register_forex_tools(registry: ToolRegistry, settings: Settings) -> None:
    for build in (
        quote_tool,
        candles_tool,
        indicators_tool,
        structure_tool,
        forecast_tool,
        opportunities_tool,
        events_tool,
        risk_tool,
        backtest_tool,
        paper_tool,
        forecast_change_tool,
    ):
        registry.register(build(settings))
