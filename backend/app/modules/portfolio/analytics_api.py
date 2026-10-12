"""Portfolio analytics (P06-T09): performance, allocation and risk of one of the user's
portfolios, cached per user (app/core/cache.py) and recomputed after any of their writes."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.cache import ResponseCache
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.portfolio.analytics_schemas import AllocationOut, PerformanceOut, RiskOut
from app.modules.portfolio.analytics_views import allocation_out, performance_out, risk_out
from app.modules.portfolio.history import SeriesFrequency

router = APIRouter(prefix="/api/v1/portfolios", tags=["analytics"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RESPONSES = {**UNAUTHORIZED, **not_found("portfolio")}


def _cache(request: Request) -> ResponseCache:
    cache: ResponseCache = request.app.state.response_cache
    return cache


@router.get("/{portfolio_id}/performance", response_model=PerformanceOut, responses=RESPONSES)
async def portfolio_performance(
    portfolio_id: uuid.UUID, request: Request, user: CurrentUserDep, session: SessionDep
) -> PerformanceOut:
    """Profit, simple return and money-weighted return (XIRR) from the ledger and the latest
    valuations (docs/design/performance.md)."""

    async def compute() -> PerformanceOut:
        return await performance_out(session, user.id, portfolio_id)

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
        return await allocation_out(session, user.id, portfolio_id)

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
        return await risk_out(session, user.id, portfolio_id, frequency, start, end)

    params = {"portfolio": portfolio_id, "frequency": frequency, "start": start, "end": end}
    return await _cache(request).cached(user.id, "risk", params, RiskOut, compute)
