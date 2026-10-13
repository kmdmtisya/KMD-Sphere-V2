"""The forex market-data API (P13-T02): instruments, the quote board and stored candles.

Sign-in is required; the data is reference data, the same for every user. The module is behind
the `forex_enabled` flag (DEC-23): when it is off every route answers 404 to a signed-in user
(authentication is checked first, so the protection is the same either way)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.authz import ResourceNotFoundError
from app.core.errors import InvalidValueError
from app.db.session import get_session
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.marketdata.factory import quality_policy
from app.modules.forex.marketdata.repository import stored_candles
from app.modules.forex.marketdata.schemas import (
    CandleOut,
    CandlesOut,
    InstrumentOut,
    InstrumentsOut,
    QuotesOut,
)
from app.modules.forex.marketdata.service import feed_status_of, quote_board
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN, PriceBasis, Timeframe
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.identity.service import CurrentUser

router = APIRouter(prefix="/api/v1/forex", tags=["forex"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
MAX_RANGE = timedelta(days=366)


async def require_forex(request: Request, user: CurrentUserDep) -> CurrentUser:
    if not request.app.state.settings.forex_enabled:
        raise ResourceNotFoundError("forex")
    return user


ForexUser = Annotated[CurrentUser, Depends(require_forex)]


@router.get(
    "/instruments",
    response_model=InstrumentsOut,
    summary="The active currency pairs and how each is quoted",
    description="Reference data from the instrument registry: pip location, display precision, "
    "liquidity tier and the default price type a licensed provider would give. The universe is "
    "configuration; inactive pairs are left out.",
    responses={**UNAUTHORIZED, **not_found("forex module (switched off)")},
)
async def instruments(_: ForexUser, session: SessionDep) -> InstrumentsOut:
    rows = await active_instruments(session)
    return InstrumentsOut(
        items=[
            InstrumentOut(
                code=r.code,
                base=r.base,
                quote=r.quote,
                pip_location=r.pip_location,
                display_precision=r.display_precision,
                liquidity_tier=r.liquidity_tier,
                default_data_type=r.default_data_type,
                spec_version=r.spec_version,
            )
            for r in rows
        ]
    )


@router.get(
    "/quotes",
    response_model=QuotesOut,
    summary="The latest quote of each pair, with its type, true age and the feed's status",
    description="A pair without a usable quote is `unavailable` and carries no price. A quote "
    "older than the staleness threshold is `stale`, with its true age. Nothing is interpolated.",
    responses={**UNAUTHORIZED, **invalid("instrument"), **not_found("forex module")},
)
async def quotes(
    request: Request,
    _: ForexUser,
    session: SessionDep,
    instrument: Annotated[
        list[Annotated[str, Query(pattern=INSTRUMENT_PATTERN)]] | None,
        Query(max_length=50, description="Pairs to show; all active pairs when omitted"),
    ] = None,
) -> QuotesOut:
    settings = request.app.state.settings
    active = [r.code for r in await active_instruments(session)]
    wanted = list(dict.fromkeys(instrument)) if instrument else active
    if set(wanted) - set(active):
        raise InvalidValueError("unknown or inactive instrument")
    now = datetime.now(UTC)
    hub = request.app.state.forex_hub
    items = await quote_board(
        session,
        settings.forex_provider,
        wanted,
        now,
        quality_policy(settings),
        timedelta(days=settings.forex_quote_lookback_days),
        hub,
    )
    return QuotesOut(
        as_of=now,
        provider=settings.forex_provider,
        feed_status=feed_status_of(hub, settings.forex_provider).value,
        items=items,
    )


@router.get(
    "/candles",
    response_model=CandlesOut,
    summary="Stored candles of a pair, oldest first",
    description="Complete candles in [start, end), at most `forex_candles_max` of them "
    "(`truncated` says when more exist). A period without a candle is absent, never filled in; "
    "a forming candle is not stored. Times are UTC and must carry a time zone.",
    responses={
        **UNAUTHORIZED,
        **invalid("range"),
        **not_found("instrument, or the forex module is switched off"),
    },
)
async def candles(
    request: Request,
    _: ForexUser,
    session: SessionDep,
    instrument: Annotated[str, Query(pattern=INSTRUMENT_PATTERN)],
    start: datetime,
    end: datetime,
    timeframe: Literal["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W", "1M"] = "1m",
    price_basis: Literal["mid", "bid", "ask"] = "mid",
) -> CandlesOut:
    settings = request.app.state.settings
    if start.tzinfo is None or end.tzinfo is None:
        raise InvalidValueError("start and end must carry a time zone")
    if not start < end or end - start > MAX_RANGE:
        raise InvalidValueError("start must be before end, at most 366 days apart")
    if instrument not in {r.code for r in await active_instruments(session)}:
        raise ResourceNotFoundError("forex instrument")
    limit = settings.forex_candles_max
    rows = await stored_candles(
        session,
        settings.forex_provider,
        instrument,
        Timeframe(timeframe),
        PriceBasis(price_basis),
        start,
        end,
        limit + 1,
    )
    return CandlesOut(
        instrument=instrument,
        timeframe=timeframe,
        price_basis=price_basis,
        provider=settings.forex_provider,
        start=start,
        end=end,
        items=[
            CandleOut(
                ts=r.ts,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                data_type=r.data_type,
            )
            for r in rows[:limit]
        ],
        truncated=len(rows) > limit,
    )
