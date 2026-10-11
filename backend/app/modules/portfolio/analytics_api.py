"""Portfolio analytics (P06-T09): performance, allocation and risk of one of the user's
portfolios, cached per user (app/core/cache.py) and recomputed after any of their writes."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.cache import ResponseCache
from app.core.money import Money, minor_units, round_half_up
from app.db.session import get_session
from app.modules.analytics.allocation import Allocation, Dimension
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.portfolio.allocation_service import AllocationService
from app.modules.portfolio.analytics_schemas import (
    PAST_NOTICE,
    AllocationOut,
    ConcentrationOut,
    DimensionOut,
    DrawdownOut,
    MoneyWeightedOut,
    PerformanceOut,
    RiskOut,
    SeriesPointOut,
    SliceOut,
    percent,
)
from app.modules.portfolio.history import SeriesFrequency
from app.modules.portfolio.performance_service import PerformanceService
from app.modules.portfolio.risk_service import RiskService

router = APIRouter(prefix="/api/v1/portfolios", tags=["analytics"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RESPONSES = {**UNAUTHORIZED, **not_found("portfolio")}


def _cache(request: Request) -> ResponseCache:
    cache: ResponseCache = request.app.state.response_cache
    return cache


def _money(currency: str) -> Callable[[Decimal], Money]:
    """Amounts in `currency`, rounded half-up to its minor units."""
    places = minor_units(currency)
    return lambda amount: Money(amount=round_half_up(amount, places), currency=currency)


@router.get("/{portfolio_id}/performance", response_model=PerformanceOut, responses=RESPONSES)
async def portfolio_performance(
    portfolio_id: uuid.UUID, request: Request, user: CurrentUserDep, session: SessionDep
) -> PerformanceOut:
    """Profit, simple return and money-weighted return (XIRR) from the ledger and the latest
    valuations (docs/design/performance.md)."""

    async def compute() -> PerformanceOut:
        p = await PerformanceService(session).portfolio(user.id, portfolio_id)
        money = _money(p.currency)
        mw = p.money_weighted
        return PerformanceOut(
            portfolio_id=portfolio_id,
            currency=p.currency,
            as_of=p.as_of,
            total_value=money(p.total_value),
            contributions=money(p.contributions),
            withdrawals=money(p.withdrawals),
            net_invested=money(p.net_invested),
            profit_loss=money(p.total_gain),
            return_percent=percent(p.simple_return),
            money_weighted=MoneyWeightedOut(
                status=mw.status.value, annual_return_percent=percent(mw.rate), unique=mw.unique
            ),
            realized_pl=money(p.realized_pl),
            unrealized_pl=money(p.unrealized_pl),
            income=money(p.income),
            expenses=money(p.expenses),
            complete=p.complete,
            first_flow=p.first_flow,
            assumed_deposits=money(p.assumed_deposits),
            assumed_deposit_count=p.assumed_count,
            notice=PAST_NOTICE,
        )

    return await _cache(request).cached(
        user.id, "performance", {"portfolio": portfolio_id}, PerformanceOut, compute
    )


@router.get("/{portfolio_id}/allocation", response_model=AllocationOut, responses=RESPONSES)
async def portfolio_allocation(
    portfolio_id: uuid.UUID, request: Request, user: CurrentUserDep, session: SessionDep
) -> AllocationOut:
    """Allocation by asset class, currency, country and sector, and concentration
    (docs/design/allocation.md)."""

    async def compute() -> AllocationOut:
        a = await AllocationService(session).portfolio(user.id, portfolio_id)
        money = _money(a.currency)

        def dimension(d: Allocation) -> DimensionOut:
            return DimensionOut(
                slices=[
                    SliceOut(
                        key=s.key,
                        value=money(s.value),
                        weight_percent=s.weight_percent,
                        parts=s.parts,
                    )
                    for s in d.slices
                ],
                hhi=None if d.hhi is None else round_half_up(d.hhi, 4),
            )

        c = a.concentration
        return AllocationOut(
            portfolio_id=portfolio_id,
            currency=a.currency,
            total=money(a.total),
            asset_class=dimension(a.by[Dimension.ASSET_CLASS]),
            currency_exposure=dimension(a.by[Dimension.CURRENCY]),
            country=dimension(a.by[Dimension.COUNTRY]),
            sector=dimension(a.by[Dimension.SECTOR]),
            concentration=ConcentrationOut(
                positions=c.positions,
                hhi=None if c.hhi is None else round_half_up(c.hhi, 4),
                effective_positions=None
                if c.effective_positions is None
                else round_half_up(c.effective_positions, 2),
                top_1_percent=percent(c.top[1]),
                top_3_percent=percent(c.top[3]),
                top_5_percent=percent(c.top[5]),
                largest=c.largest,
            ),
            complete=a.complete,
            unpriced_assets=len(a.unpriced_assets),
        )

    return await _cache(request).cached(
        user.id, "allocation", {"portfolio": portfolio_id}, AllocationOut, compute
    )


@router.get(
    "/{portfolio_id}/risk",
    response_model=RiskOut,
    responses={**RESPONSES, **invalid("range (after today, or too many points)")},
)
async def portfolio_risk(
    portfolio_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    frequency: Annotated[SeriesFrequency, Query(description="Spacing of the value series")] = (
        SeriesFrequency.MONTHLY
    ),
    start: Annotated[
        date | None, Query(description="Default: the first entry or valuation")
    ] = None,
    end: Annotated[date | None, Query(description="Default: today")] = None,
) -> RiskOut:
    """The value series, volatility, maximum drawdown and time-weighted return, or an explicit
    status when the data cannot support them (docs/design/risk.md)."""

    async def compute() -> RiskOut:
        now = datetime.now(UTC)
        r = await RiskService(session).portfolio(user.id, portfolio_id, frequency, start, end, now)
        money = _money(r.currency)
        k, dd, tw = r.risk, r.risk.max_drawdown, r.risk.time_weighted
        return RiskOut(
            portfolio_id=portfolio_id,
            currency=r.currency,
            frequency=r.frequency.value,
            start=r.start,
            end=r.end,
            status=k.status.value,
            points=[
                SeriesPointOut(on=p.on, value=money(p.value), complete=p.complete) for p in r.points
            ],
            returns=len(k.returns),
            volatility_percent=percent(k.volatility),
            period_volatility_percent=percent(k.period_volatility),
            max_drawdown=None
            if dd is None
            else DrawdownOut(
                depth_percent=round_half_up(dd.depth * 100, 2),
                peak=dd.peak,
                trough=dd.trough,
                recovered=dd.recovered,
            ),
            time_weighted_return_percent=None if tw is None else percent(tw.cumulative),
            time_weighted_annualized_percent=None if tw is None else percent(tw.annualized),
            incomplete_points=k.incomplete_points,
            assumed_deposit_count=r.assumed_count,
            as_of=now,
            notice=PAST_NOTICE,
        )

    params = {"portfolio": portfolio_id, "frequency": frequency, "start": start, "end": end}
    return await _cache(request).cached(user.id, "risk", params, RiskOut, compute)
