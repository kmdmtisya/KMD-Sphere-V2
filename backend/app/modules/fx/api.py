"""/api/v1/fx: the reporting-currency rates and their status, and a user-triggered refresh
(P11-T03). Reads never call a provider; a refresh calls one at most once per window, whoever
asks, and each user may ask a few times an hour."""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.core.money import CURRENCY_PATTERN, Money, round_half_up
from app.core.ratelimit import RateLimit, RateLimitedError
from app.db.session import get_session
from app.modules.fx.board import RateBoard, invalidate
from app.modules.fx.history import RateConcept, rate_history
from app.modules.fx.models import Currency, FxConversionAudit
from app.modules.fx.refresh import refresh_once_per_window
from app.modules.fx.reporting import (
    CurrencyPreferenceService,
    CurrencyPreferencesOut,
    CurrencyPreferencesUpdate,
)
from app.modules.fx.schemas import (
    ConvertIn,
    ConvertOut,
    CurrencyOut,
    FxHistoryOut,
    FxHistoryPointOut,
    FxProviderAttemptOut,
    FxRateLineOut,
    FxRatesOut,
    FxRefreshOut,
    FxStatusOut,
    SnapshotRateOut,
)
from app.modules.fx.snapshot import (
    ResolvedRate,
    Snapshot,
    SnapshotService,
    UnsupportedCurrency,
    convert,
)
from app.modules.fx.status import StatusPolicy
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.market_data.fx import FxRateUnavailable, end_of_day
from app.modules.market_data.providers.errors import ProviderUnavailable
from app.modules.market_data.providers.registry import build_providers
from app.modules.market_data.service import FxService

router = APIRouter(prefix="/api/v1/fx", tags=["fx"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _status(request: Request, session: AsyncSession) -> FxStatusOut:
    settings: Settings = request.app.state.settings
    board = RateBoard(
        session,
        StatusPolicy.from_settings(settings),
        getattr(request.app.state, "cache_store", None),
        settings.fx_status_cache_seconds,
    )
    now = datetime.now(UTC)
    lines = await board.lines(settings.fx_pivot_currency, now)
    return FxStatusOut(
        pivot_currency=settings.fx_pivot_currency,
        checked_at=now,
        rates=[
            FxRateLineOut(
                currency=line.currency,
                status=line.status.value,
                rate=line.rate,
                provider=line.provider,
                rate_type=line.rate_type,
                rate_timestamp=line.rate_timestamp,
                retrieved_at=line.retrieved_at,
                path=line.path,
                age_seconds=line.age_seconds,
            )
            for line in lines
        ],
    )


@router.get(
    "/status",
    response_model=FxStatusOut,
    summary="Reporting-currency rates and their freshness",
    responses=UNAUTHORIZED,
)
async def fx_status(request: Request, user: CurrentUserDep, session: SessionDep) -> FxStatusOut:
    """The latest stored rate of every supported currency against the pivot currency, with the
    provider, the kind of rate, when it was published and fetched, and its status. Cached rates
    are never labelled current; a currency without any rate is `unavailable`."""
    return await _status(request, session)


@router.post(
    "/refresh",
    response_model=FxRefreshOut,
    summary="Ask for fresh rates",
    responses=UNAUTHORIZED,
)
async def fx_refresh(request: Request, user: CurrentUserDep, session: SessionDep) -> FxRefreshOut:
    """Fetches new rates unless a refresh already ran in the current window (then the stored
    rates are returned and no provider is called). Each user may ask a few times an hour. When
    every provider fails, the last stored rates are returned with their status and age; no rate
    is ever invented."""
    settings: Settings = request.app.state.settings
    limiter = request.app.state.rate_limiter
    if limiter is not None:
        decision = await limiter.hit(
            RateLimit("fx_refresh", settings.fx_refresh_per_user_per_hour, 3600), str(user.id)
        )
        if not decision.allowed:
            raise RateLimitedError(decision.retry_after)

    # Tests (and later a shared instance) may provide the providers; otherwise from settings.
    providers = getattr(request.app.state, "market_providers", None) or build_providers(settings)
    attempts: list[FxProviderAttemptOut] = []
    missing: list[str] = []
    refreshed = False
    window = ""
    try:
        run = await refresh_once_per_window(
            request.app.state.db.session_factory,
            providers.fx_sources,
            settings.fx_pivot_currency,
            datetime.now(UTC),
            settings.fx_refresh_window_minutes,
        )
        refreshed, window = run.ran, run.window
        if run.outcome is not None:
            attempts = [
                FxProviderAttemptOut(
                    provider=a.provider,
                    supplied=a.supplied,
                    unsupported=a.unsupported,
                    failed=a.error is not None,
                )
                for a in run.outcome.attempts
            ]
            missing = run.outcome.missing
            await invalidate(getattr(request.app.state, "cache_store", None))
    except ProviderUnavailable:
        refreshed = False
        attempts = [
            FxProviderAttemptOut(provider=p.name, supplied=[], unsupported=[], failed=True)
            for p in providers.fx_sources
        ]
    return FxRefreshOut(
        refreshed=refreshed,
        window=window,
        attempts=attempts,
        missing=missing,
        status=await _status(request, session),
    )


# ------------------------------------------------------------------------- P11-T04 conversion
currencies_router = APIRouter(prefix="/api/v1/currencies", tags=["fx"])
CurrencyCode = Annotated[str, Path(pattern=CURRENCY_PATTERN, description="ISO 4217 code")]


def _snapshots(request: Request, session: AsyncSession) -> SnapshotService:
    return SnapshotService(session, request.app.state.settings.fx_pivot_currency)


async def _snapshot(service: SnapshotService, snapshot_id: uuid.UUID | None) -> Snapshot:
    return await (service.get(snapshot_id) if snapshot_id else service.current())


def _rate_out(rate: ResolvedRate, policy: StatusPolicy, now: datetime) -> SnapshotRateOut:
    return SnapshotRateOut(
        base=rate.base,
        quote=rate.quote,
        rate=rate.rate,
        path=list(rate.path) if rate.path else None,
        status=rate.status(policy, now).value,
        rate_timestamp=rate.rate_timestamp,
        providers=rate.providers,
    )


@currencies_router.get(
    "",
    response_model=list[CurrencyOut],
    summary="Supported currencies",
    responses=UNAUTHORIZED,
)
async def list_currencies(user: CurrentUserDep, session: SessionDep) -> list[CurrencyOut]:
    """The currencies amounts can be reported in, with name, symbol and precision."""
    rows = await session.execute(
        select(Currency).where(Currency.is_active.is_(True)).order_by(Currency.code)
    )
    return [
        CurrencyOut(code=c.code, name=c.name, symbol=c.symbol, decimal_places=c.decimal_places)
        for c in rows.scalars()
    ]


@router.get(
    "/rates",
    response_model=FxRatesOut,
    summary="Rates of one currency against others, from one snapshot",
    responses={**UNAUTHORIZED, **invalid("currency"), **not_found("snapshot")},
)
async def fx_rates(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    base: Annotated[
        str | None, Query(pattern=CURRENCY_PATTERN, description="Default: the pivot currency")
    ] = None,
    quotes: Annotated[
        str | None,
        Query(
            pattern=r"^[A-Z]{3}(,[A-Z]{3}){0,49}$",
            description="Comma-separated codes; default: every supported currency",
        ),
    ] = None,
    snapshot_id: Annotated[uuid.UUID | None, Query()] = None,
) -> FxRatesOut:
    """Every rate comes from the same snapshot (its id is returned), so figures converted with
    them agree. Derived rates state their path; each rate's status is the worst of the stored
    rates it used."""
    settings: Settings = request.app.state.settings
    service = _snapshots(request, session)
    active = await service.currencies()
    base_code = base or settings.fx_pivot_currency
    wanted = quotes.split(",") if quotes else sorted(active)
    for code in [base_code, *wanted]:
        if code not in active:
            raise UnsupportedCurrency(f"{code} is not a supported currency")
    snapshot = await _snapshot(service, snapshot_id)
    policy, now = StatusPolicy.from_settings(settings), datetime.now(UTC)
    rates: list[SnapshotRateOut] = []
    unavailable: list[str] = []
    for quote in wanted:
        if quote == base_code:
            continue
        try:
            rates.append(_rate_out(snapshot.rate(base_code, quote), policy, now))
        except FxRateUnavailable:
            unavailable.append(quote)
    return FxRatesOut(snapshot_id=snapshot.id, base=base_code, rates=rates, unavailable=unavailable)


@router.get(
    "/rates/{base}/{quote}",
    response_model=SnapshotRateOut,
    summary="One rate, direct or derived, with its path",
    responses={
        **UNAUTHORIZED,
        **invalid("currency"),
        404: {"description": "No rate for this pair (fx-rate-unavailable) or no such snapshot"},
    },
)
async def fx_rate(
    request: Request,
    base: CurrencyCode,
    quote: CurrencyCode,
    user: CurrentUserDep,
    session: SessionDep,
    snapshot_id: Annotated[uuid.UUID | None, Query()] = None,
) -> SnapshotRateOut:
    """1 `base` = `rate` `quote` from the latest (or the given) snapshot: direct, inverted, or
    derived through the pivot with its path. A pair with no rate is 404, never guessed."""
    settings: Settings = request.app.state.settings
    service = _snapshots(request, session)
    active = await service.currencies()
    for code in (base, quote):
        if code not in active:
            raise UnsupportedCurrency(f"{code} is not a supported currency")
    snapshot = await _snapshot(service, snapshot_id)
    return _rate_out(
        snapshot.rate(base, quote), StatusPolicy.from_settings(settings), datetime.now(UTC)
    )


@router.post(
    "/convert",
    response_model=ConvertOut,
    summary="Convert an amount",
    responses={
        **UNAUTHORIZED,
        **invalid("conversion"),
        404: {"description": "No rate for this pair (fx-rate-unavailable) or no such snapshot"},
    },
)
async def fx_convert(
    body: ConvertIn, request: Request, user: CurrentUserDep, session: SessionDep
) -> ConvertOut:
    """Converts with the snapshot's rate (or, with `on`, the historical rate of that day) and
    rounds once to the target's decimal places. Nothing stored is changed. A past day is never
    converted with today's rate, and a missing historical rate is 404, never substituted.
    Explicit converter use is recorded in the conversion audit (DEC-28)."""
    settings: Settings = request.app.state.settings
    if body.on is not None and body.snapshot_id is not None:
        raise InvalidValueError("Use either a snapshot or a date, not both.")
    service = _snapshots(request, session)
    source_currency = body.amount.currency
    places = await service.decimal_places(body.to)
    await service.decimal_places(source_currency)
    now = datetime.now(UTC)
    snapshot_id: uuid.UUID | None = None
    if body.on is None:
        snapshot = await _snapshot(service, body.snapshot_id)
        resolved = snapshot.rate(source_currency, body.to)
        snapshot_id = snapshot.id
        rate, path, providers = resolved.rate, resolved.path, resolved.providers
        rate_timestamp = resolved.rate_timestamp
        status = resolved.status(StatusPolicy.from_settings(settings), now).value
        concept = RateConcept.CURRENT_REPORTING
        stamp_for_audit = rate_timestamp or snapshot.created_at
    else:
        q = await FxService(session, settings.fx_pivot_currency).quote(
            source_currency, body.to, end_of_day(body.on)
        )
        rate, path = q.rate, q.path
        providers = [] if q.provider == "identity" else q.provider.split("+")
        rate_timestamp = None if q.provider == "identity" else q.as_of
        status = "stale" if q.stale else "current"
        concept = RateConcept.HISTORICAL_VALUATION
        stamp_for_audit = q.as_of
    converted = convert(body.amount.amount, rate, places)
    session.add(
        FxConversionAudit(
            user_id=user.id,
            source_currency=source_currency,
            target_currency=body.to,
            source_amount=body.amount.amount,
            converted_amount=converted,
            rate=round_half_up(rate, 12),
            rate_timestamp=stamp_for_audit,
            provider=("+".join(providers) or "identity")[:32],
            snapshot_id=snapshot_id,
            conversion_type="converter",
        )
    )
    await session.commit()
    return ConvertOut(
        source=body.amount,
        converted=Money(amount=converted, currency=body.to),
        rate=rate,
        path=list(path) if path else None,
        concept=concept.value,
        snapshot_id=snapshot_id,
        on=body.on,
        status=status,
        rate_timestamp=rate_timestamp,
        providers=providers,
    )


@router.get(
    "/history",
    response_model=FxHistoryOut,
    summary="Daily historical rates of a pair",
    responses={**UNAUTHORIZED, **invalid("currency or date range")},
)
async def fx_history(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    base: Annotated[str, Query(pattern=CURRENCY_PATTERN)],
    quote: Annotated[str, Query(pattern=CURRENCY_PATTERN)],
    start: Annotated[date, Query(description="First day")],
    end: Annotated[date, Query(description="Last day (at most 366 days after start)")],
) -> FxHistoryOut:
    """One point per day: the rate valid at the end of that day (UTC) under the historical rule,
    for converting past values. Days without a usable rate are flagged `rate_missing`, never
    filled; a rate carried from an earlier day inside the 7-day window is flagged."""
    settings: Settings = request.app.state.settings
    service = _snapshots(request, session)
    active = await service.currencies()
    for code in (base, quote):
        if code not in active:
            raise UnsupportedCurrency(f"{code} is not a supported currency")
    points = await rate_history(session, base, quote, start, end, settings.fx_pivot_currency)
    return FxHistoryOut(
        base=base,
        quote=quote,
        points=[
            FxHistoryPointOut(
                date=p.day,
                rate=p.rate,
                rate_timestamp=p.rate_timestamp,
                provider=p.provider,
                path=list(p.path) if p.path else None,
                rate_missing=p.rate_missing,
                from_earlier_day=p.from_earlier_day,
            )
            for p in points
        ],
        missing_days=sum(p.rate_missing for p in points),
    )


# --------------------------------------------------------------- P11-T06 reporting preference
me_router = APIRouter(prefix="/api/v1/me", tags=["identity"])


@me_router.get(
    "/currency-preferences",
    response_model=CurrencyPreferencesOut,
    summary="Your reporting currency",
    responses=UNAUTHORIZED,
)
async def get_currency_preferences(
    request: Request, user: CurrentUserDep, session: SessionDep
) -> CurrencyPreferencesOut:
    """The currency every figure is shown in, on every device, and the recently used ones.
    Until you choose, it is your profile's base currency (when supported)."""
    pivot = request.app.state.settings.fx_pivot_currency
    return await CurrencyPreferenceService(session, pivot).get(user.id)


@me_router.patch(
    "/currency-preferences",
    response_model=CurrencyPreferencesOut,
    summary="Change your reporting currency",
    responses={**UNAUTHORIZED, **invalid("currency")},
)
async def set_currency_preferences(
    body: CurrencyPreferencesUpdate, request: Request, user: CurrentUserDep, session: SessionDep
) -> CurrencyPreferencesOut:
    """Changes how figures are shown. Nothing else changes: balances, transactions, portfolio
    base currencies, goal targets and forecast inputs stay as they are."""
    pivot = request.app.state.settings.fx_pivot_currency
    return await CurrencyPreferenceService(session, pivot).set(user.id, body.reporting_currency)
