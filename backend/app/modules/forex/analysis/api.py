"""Forex technical analysis API (P13-T03): indicators, market structure and candlestick patterns
over stored candles. Reference data, the same for every signed-in user; behind the forex flag
(404 when off, after authentication). Every figure is computed here, in Decimal."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.authz import ResourceNotFoundError
from app.core.errors import InvalidValueError
from app.modules.forex.analysis import patterns as pat
from app.modules.forex.analysis import structure as st
from app.modules.forex.analysis.indicators import atr
from app.modules.forex.analysis.registry import Bars, compute, parse_all
from app.modules.forex.analysis.schemas import (
    BreakoutOut,
    Coverage,
    IndicatorSeries,
    IndicatorsOut,
    LevelOut,
    PatternOut,
    PatternsOut,
    StructureOut,
    SwingOut,
    TrendlineOut,
)
from app.modules.forex.analysis.service import Bar, Loaded, load
from app.modules.forex.api import ForexUser, SessionDep
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN, PriceBasis, Timeframe

router = APIRouter(prefix="/api/v1/forex", tags=["forex"])
Q8 = Decimal("0.00000001")
RESPONSES = {
    **UNAUTHORIZED,
    **invalid("request"),
    **not_found("instrument, or the forex module is switched off"),
}
InstrumentQ = Annotated[str, Query(pattern=INSTRUMENT_PATTERN)]
FrameQ = Annotated[str, Query(pattern=r"^(1m|5m|15m|30m|1H|4H|1D|1W|1M)$")]
BasisQ = Annotated[str, Query(pattern=r"^(mid|bid|ask)$")]


def q8(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(Q8, rounding=ROUND_HALF_UP)


def _need(value: Decimal | None) -> Decimal:
    if value is None:  # pragma: no cover - callers check before
        raise ValueError("value")
    return value


async def _loaded(
    request: Request,
    session: AsyncSession,
    instrument: str,
    timeframe: str,
    basis: str,
    start: datetime,
    end: datetime,
) -> tuple[Loaded, Coverage]:
    settings = request.app.state.settings
    if start.tzinfo is None or end.tzinfo is None:
        raise InvalidValueError("start and end must carry a time zone")
    if not start < end or end - start > timedelta(days=366):
        raise InvalidValueError("start must be before end, at most 366 days apart")
    if instrument not in {r.code for r in await active_instruments(session)}:
        raise ResourceNotFoundError("forex instrument")
    now = datetime.now(UTC)
    loaded = await load(
        session,
        settings.forex_provider,
        instrument,
        Timeframe(timeframe),
        PriceBasis(basis),
        start,
        end,
        now,
        settings.forex_analysis_max_bars,
        settings.forex_analysis_source_cap,
    )
    cover = Coverage(
        instrument=instrument,
        timeframe=timeframe,
        price_basis=basis,
        provider=settings.forex_provider,
        as_of=now,
        data_types=loaded.data_types,
        bars=len(loaded.bars),
        partial_bars=sum(1 for b in loaded.bars if b.missing),
        forming_excluded=loaded.forming_excluded,
        truncated=loaded.truncated,
    )
    return loaded, cover


def _series(bars: Sequence[Bar]) -> Bars:
    return Bars([b.high for b in bars], [b.low for b in bars], [b.close for b in bars])


@router.get(
    "/indicators",
    response_model=IndicatorsOut,
    summary="Technical indicators over stored candles",
    description="`indicator` is repeated, each as `name` or `name:p1,p2` from sma, ema, macd, "
    "rsi, stochastic, roc, atr, adx and bollinger (for example `rsi:14`, `macd:12,26,9`). Values "
    "are null until the warm-up is satisfied or where a ratio is undefined; ask for a wider range "
    "to see earlier values. Formulas: docs/financial-methods.md section 19.",
    responses=RESPONSES,
)
async def indicators(
    request: Request,
    _: ForexUser,
    session: SessionDep,
    instrument: InstrumentQ,
    start: datetime,
    end: datetime,
    indicator: Annotated[list[str], Query(max_length=12)],
    timeframe: FrameQ = "1m",
    price_basis: BasisQ = "mid",
) -> IndicatorsOut:
    asked = parse_all(indicator)
    loaded, cover = await _loaded(request, session, instrument, timeframe, price_basis, start, end)
    bars = _series(loaded.bars)
    out = []
    for req in asked:
        values = compute(req, bars)
        out.append(
            IndicatorSeries(
                name=req.label,
                outputs={k: [q8(v) for v in series] for k, series in values.items()},
                first_defined_index=req.warmup(),
            )
        )
    return IndicatorsOut(**cover.model_dump(), timestamps=[b.ts for b in loaded.bars], series=out)


def _structure(
    loaded: Loaded,
) -> tuple[Decimal, list[st.SwingPoint], list[st.Level], list[st.Breakout], list[st.Trendline]]:
    bars = loaded.bars
    high, low, close = [b.high for b in bars], [b.low for b in bars], [b.close for b in bars]
    averages = atr(high, low, close, 14)
    last = next((v for v in reversed(averages) if v is not None), None)
    tolerance = (last / 2) if last else (max(close) - min(close)) / 100 or Decimal("0.0001")
    points = st.swing_points(high, low)
    found = st.levels(points, tolerance)
    return (
        tolerance,
        points,
        found,
        st.breakouts(close, found),
        st.trendlines(points, close, tolerance),
    )


@router.get(
    "/structure",
    response_model=StructureOut,
    summary="Market structure: swings, support and resistance, breakouts, trendlines and channels",
    description="Swing points are reported once confirmed by two further bars. Levels group swings "
    "within half the ATR(14); a level below the last close is support, otherwise resistance. "
    "Descriptive only, not a forecast.",
    responses=RESPONSES,
)
async def structure(
    request: Request,
    _: ForexUser,
    session: SessionDep,
    instrument: InstrumentQ,
    start: datetime,
    end: datetime,
    timeframe: FrameQ = "1H",
    price_basis: BasisQ = "mid",
) -> StructureOut:
    loaded, cover = await _loaded(request, session, instrument, timeframe, price_basis, start, end)
    if len(loaded.bars) < 5:
        return StructureOut(
            **cover.model_dump(),
            tolerance=Decimal(0),
            swings=[],
            levels=[],
            breakouts=[],
            trendlines=[],
        )
    tolerance, points, found, breaks, lines = _structure(loaded)
    ts = [b.ts for b in loaded.bars]
    last_close = loaded.bars[-1].close
    high, low = [b.high for b in loaded.bars], [b.low for b in loaded.bars]
    trend = []
    for line in lines:
        ch = st.channel(line, high, low)
        trend.append(
            TrendlineOut(
                kind=line.kind,
                first_ts=ts[line.first.index],
                second_ts=ts[line.second.index],
                slope_per_bar=_need(q8(line.slope)),
                value_at_last=_need(q8(line.value_at_last)),
                intact=line.intact,
                channel_upper_at_last=_need(q8(ch.upper_at_last)),
                channel_lower_at_last=_need(q8(ch.lower_at_last)),
            )
        )
    return StructureOut(
        **cover.model_dump(),
        tolerance=_need(q8(tolerance)),
        swings=[
            SwingOut(
                ts=ts[p.index], kind=p.kind, price=_need(q8(p.price)), confirmed_ts=ts[p.confirmed]
            )
            for p in points
        ],
        levels=[
            LevelOut(
                price=_need(q8(lv.price)),
                role=st.role(lv, last_close),
                touches=lv.touches,
                first_ts=ts[lv.first_index],
                last_ts=ts[lv.last_index],
                established_ts=ts[lv.established],
            )
            for lv in found
        ],
        breakouts=[
            BreakoutOut(ts=ts[b.index], level_price=_need(q8(b.level_price)), direction=b.direction)
            for b in breaks
        ],
        trendlines=trend,
    )


@router.get(
    "/patterns",
    response_model=PatternsOut,
    summary="Candlestick and price-action patterns",
    description="Rule-based detections, each naming its rule and the candles used. A pattern's "
    "bias describes its shape and is not a forecast or a probability.",
    responses=RESPONSES,
)
async def patterns(
    request: Request,
    _: ForexUser,
    session: SessionDep,
    instrument: InstrumentQ,
    start: datetime,
    end: datetime,
    timeframe: FrameQ = "1H",
    price_basis: BasisQ = "mid",
) -> PatternsOut:
    loaded, cover = await _loaded(request, session, instrument, timeframe, price_basis, start, end)
    bars = loaded.bars
    if len(bars) < 3:
        return PatternsOut(**cover.model_dump(), patterns=[])
    ohlc = pat.Ohlc(
        [b.open for b in bars],
        [b.high for b in bars],
        [b.low for b in bars],
        [b.close for b in bars],
    )
    tolerance, _points, _found, breaks, _lines = _structure(loaded)
    averages = atr(ohlc.high, ohlc.low, ohlc.close, 14)
    hits = [
        *pat.detect(ohlc),
        *pat.range_consolidation(ohlc, averages),
        *pat.breakout_retest(ohlc, breaks, tolerance),
    ]
    hits.sort(key=lambda h: (h.end, h.rule))
    return PatternsOut(
        **cover.model_dump(),
        patterns=[
            PatternOut(
                rule=h.rule,
                category=h.category,
                bias=h.bias,
                timestamps=[bars[i].ts for i in h.indices],
            )
            for h in hits
        ],
    )
