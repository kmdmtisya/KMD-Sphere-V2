"""Economic calendar API (P13-T04.4): events, event-risk windows and policy-rate differentials.

Reference data, the same for every signed-in user, behind the forex flag. Release times are stored
in UTC and returned both in UTC and in the user's time zone (the profile's, unless `tz` names
another). Each event keeps confirmed values, the consensus expectation and commentary apart."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, available_timezones

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.authz import ResourceNotFoundError
from app.core.errors import InvalidValueError
from app.core.money import DecimalString
from app.modules.forex.api import ForexUser, SessionDep
from app.modules.forex.calendar.models import ForexEconomicEvent, ForexPolicyRate
from app.modules.forex.calendar.risk import active, pair_currencies, window_for, windows
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN
from app.modules.identity.models import UserProfile

router = APIRouter(prefix="/api/v1/forex", tags=["forex"])
MAX_RANGE = timedelta(days=92)
ORDER = {"low": 0, "medium": 1, "high": 2}
RESPONSES = {
    **UNAUTHORIZED,
    **invalid("request"),
    **not_found("instrument, or the forex module is switched off"),
}
NOTICE = (
    "Scheduled releases with their source and time. Confirmed values (actual, previous) are "
    "facts as published; the consensus forecast is an expectation; commentary is not data. A "
    "risk window marks when prices often move around a release; it is not a prediction. DEMO "
    "items are fictional."
)
COMMENTARY_LABEL = "Commentary from the source: not confirmed data"
Importance = Literal["low", "medium", "high"]


class Confirmed(BaseModel):
    released: bool = Field(description="True once the actual value is published")
    actual: DecimalString | None
    previous: DecimalString | None
    unit: str | None


class Expectation(BaseModel):
    forecast: DecimalString | None = Field(
        description="Consensus forecast: an expectation, not a fact"
    )


class Commentary(BaseModel):
    label: str = COMMENTARY_LABEL
    text: str


class WindowOut(BaseModel):
    name: str
    currencies: list[str]
    importance: Importance
    scheduled_at: datetime
    starts: datetime
    ends: datetime


class EventOut(BaseModel):
    id: str
    name: str
    kind: Literal["indicator", "central_bank_decision", "speech", "other"]
    currencies: list[str]
    importance: Importance
    scheduled_at: datetime = Field(description="UTC")
    scheduled_local: datetime = Field(description="The same instant in the requested time zone")
    confirmed: Confirmed
    expectation: Expectation
    commentary: Commentary | None
    risk_window: WindowOut | None
    source: str
    source_url: str | None
    licence_status: Literal["demo", "public_domain", "unconfirmed", "licensed"]
    is_demo: bool
    retrieved_at: datetime
    actual_seen_at: datetime | None


class CalendarOut(BaseModel):
    timezone: str
    start: datetime
    end: datetime
    items: list[EventOut]
    notice: str = NOTICE


class ForexEventRiskOut(BaseModel):
    instrument: str
    at: datetime
    in_window: bool
    windows: list[WindowOut]
    notice: str = NOTICE


class RateOut(BaseModel):
    currency: str
    bank: str
    rate: DecimalString = Field(description="Percent a year")
    effective_date: date
    decided_at: datetime
    source: str
    source_url: str | None
    is_demo: bool


class DifferentialOut(BaseModel):
    instrument: str
    base: RateOut | None
    quote: RateOut | None
    differential: DecimalString | None = Field(
        description="Base rate minus quote rate, in percentage points; null when either is unknown"
    )
    notice: str = (
        "Policy rates as published by each central bank, with their dates. The differential is "
        "base minus quote. DEMO rates are fictional."
    )


async def _zone(session: AsyncSession, user_id: object, tz: str | None) -> str:
    if tz is not None:
        if tz not in available_timezones():
            raise InvalidValueError("unknown time zone")
        return tz
    found = await session.scalar(select(UserProfile.timezone).where(UserProfile.user_id == user_id))
    return found or "UTC"


def _window_out(w: object) -> WindowOut:
    return WindowOut.model_validate(w, from_attributes=True)


def _event_out(r: ForexEconomicEvent, zone: ZoneInfo) -> EventOut:
    w = window_for(r)
    return EventOut(
        id=str(r.id),
        name=r.name,
        kind=r.kind,
        currencies=list(r.currencies),
        importance=r.importance,
        scheduled_at=r.scheduled_at,
        scheduled_local=r.scheduled_at.astimezone(zone),
        confirmed=Confirmed(
            released=r.actual is not None, actual=r.actual, previous=r.previous, unit=r.unit
        ),
        expectation=Expectation(forecast=r.forecast),
        commentary=Commentary(text=r.commentary) if r.commentary else None,
        risk_window=_window_out(w) if w else None,
        source=r.source,
        source_url=r.source_url,
        licence_status=r.licence_status,
        is_demo=r.is_demo,
        retrieved_at=r.retrieved_at,
        actual_seen_at=r.actual_seen_at,
    )


async def _events(
    session: AsyncSession, start: datetime, end: datetime
) -> list[ForexEconomicEvent]:
    return list(
        (
            await session.execute(
                select(ForexEconomicEvent)
                .where(
                    ForexEconomicEvent.scheduled_at >= start, ForexEconomicEvent.scheduled_at < end
                )
                .order_by(ForexEconomicEvent.scheduled_at, ForexEconomicEvent.name)
            )
        ).scalars()
    )


@router.get(
    "/calendar",
    response_model=CalendarOut,
    summary="Scheduled economic events with their published values",
    description="Events scheduled in [start, end) (at most 92 days), optionally for some "
    "currencies and from a minimum importance. Each event separates confirmed values, the "
    "consensus expectation and commentary, and carries its source and retrieval time.",
    responses=RESPONSES,
)
async def calendar(
    user: ForexUser,
    session: SessionDep,
    start: datetime,
    end: datetime,
    currency: Annotated[
        list[Annotated[str, Query(pattern=r"^[A-Z]{3}$")]] | None, Query(max_length=20)
    ] = None,
    min_importance: Importance = "low",
    tz: Annotated[str | None, Query(max_length=64)] = None,
) -> CalendarOut:
    if start.tzinfo is None or end.tzinfo is None:
        raise InvalidValueError("start and end must carry a time zone")
    if not start < end or end - start > MAX_RANGE:
        raise InvalidValueError("start must be before end, at most 92 days apart")
    zone_name = await _zone(session, user.id, tz)
    zone = ZoneInfo(zone_name)
    wanted = set(currency or [])
    rows = [
        r
        for r in await _events(session, start, end)
        if ORDER[r.importance] >= ORDER[min_importance]
        and (not wanted or wanted & set(r.currencies))
    ]
    return CalendarOut(
        timezone=zone_name,
        start=start,
        end=end,
        items=[_event_out(r, zone) for r in rows],
    )


@router.get(
    "/calendar/risk",
    response_model=ForexEventRiskOut,
    summary="Event-risk windows open for a pair at a time",
    description="Windows of medium and high importance releases for either currency of the pair "
    "that are open at `at` (now when omitted). A window is a schedule fact, not a forecast.",
    responses=RESPONSES,
)
async def risk(
    _: ForexUser,
    session: SessionDep,
    instrument: Annotated[str, Query(pattern=INSTRUMENT_PATTERN)],
    at: datetime | None = None,
) -> ForexEventRiskOut:
    when = at or datetime.now(UTC)
    if when.tzinfo is None:
        raise InvalidValueError("at must carry a time zone")
    if instrument not in {r.code for r in await active_instruments(session)}:
        raise ResourceNotFoundError("forex instrument")
    nearby = await _events(session, when - timedelta(hours=2), when + timedelta(hours=2))
    found = active(windows(nearby), instrument, when)
    return ForexEventRiskOut(
        instrument=instrument,
        at=when,
        in_window=bool(found),
        windows=[_window_out(w) for w in found],
    )


async def _latest_rate(session: AsyncSession, currency: str) -> ForexPolicyRate | None:
    return await session.scalar(
        select(ForexPolicyRate)
        .where(
            ForexPolicyRate.currency == currency,
            ForexPolicyRate.effective_date <= datetime.now(UTC).date(),
        )
        .order_by(ForexPolicyRate.effective_date.desc(), ForexPolicyRate.decided_at.desc())
        .limit(1)
    )


def _rate_out(r: ForexPolicyRate | None) -> RateOut | None:
    if r is None:
        return None
    return RateOut(
        currency=r.currency,
        bank=r.bank,
        rate=r.rate,
        effective_date=r.effective_date,
        decided_at=r.decided_at,
        source=r.source,
        source_url=r.source_url,
        is_demo=r.is_demo,
    )


@router.get(
    "/policy-rates/differential",
    response_model=DifferentialOut,
    summary="Central-bank policy rates of a pair and their differential",
    description="The latest effective policy rate of each currency of the pair, with its bank, "
    "dates and source, and base minus quote in percentage points.",
    responses=RESPONSES,
)
async def differential(
    _: ForexUser,
    session: SessionDep,
    instrument: Annotated[str, Query(pattern=INSTRUMENT_PATTERN)],
) -> DifferentialOut:
    if instrument not in {r.code for r in await active_instruments(session)}:
        raise ResourceNotFoundError("forex instrument")
    pair_currencies(instrument)
    base, quote = instrument[:3], instrument[4:]
    b, q = await _latest_rate(session, base), await _latest_rate(session, quote)
    diff: Decimal | None = b.rate - q.rate if b is not None and q is not None else None
    return DifferentialOut(
        instrument=instrument, base=_rate_out(b), quote=_rate_out(q), differential=diff
    )
