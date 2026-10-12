"""/api/v1/dashboard (P06-T09): the Home screen's figures in one call (net worth, passive income
and goals), composed from the modules' services and cached per user (app/core/cache.py)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED
from app.core.cache import ResponseCache
from app.core.money import CURRENCY_PATTERN, Money, minor_units, round_half_up
from app.db.session import get_session
from app.modules.fx.reporting import ReportingDep
from app.modules.fx.schemas import ReportingOut
from app.modules.goals.service import GoalService
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.networth.income_service import IncomeService
from app.modules.networth.service import NetWorthService

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class NetWorthCard(BaseModel):
    assets: Money
    liabilities: Money
    net_worth: Money


class IncomeCard(BaseModel):
    monthly: Money
    yearly: Money


class GoalsCard(BaseModel):
    on_track: int
    total: int


class DashboardOut(BaseModel):
    currency: str
    net_worth: NetWorthCard
    income: IncomeCard
    goals: GoalsCard = Field(description="Goal statuses are estimates under stated assumptions")
    complete: bool = Field(
        description="False when assets are unpriced or amounts in a currency could not be converted"
    )
    as_of: datetime
    reporting: ReportingOut | None = Field(
        default=None, description="The rate snapshot every figure was converted with (P11-T06)"
    )


@router.get("", response_model=DashboardOut, responses=UNAUTHORIZED)
async def dashboard(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    reporting: ReportingDep,
    currency: Annotated[
        str | None,
        Query(
            pattern=CURRENCY_PATTERN,
            description="Defaults to the user's reporting-currency setting",
        ),
    ] = None,
) -> DashboardOut:
    """Net worth, passive income and goals on track for the signed-in user."""

    async def compute() -> DashboardOut:
        now = datetime.now(UTC)
        nw = await NetWorthService(session).user(user.id, currency, now)
        income = await IncomeService(session).user(user.id, nw.currency, now.date())
        goals = await GoalService(session).summary(user.id, now)
        places = minor_units(nw.currency)

        def money(amount: Decimal) -> Money:
            return Money(amount=round_half_up(amount, places), currency=nw.currency)

        return DashboardOut(
            currency=nw.currency,
            net_worth=NetWorthCard(
                assets=nw.assets, liabilities=nw.liabilities, net_worth=nw.net_worth
            ),
            income=IncomeCard(monthly=money(income.monthly_average), yearly=money(income.yearly)),
            goals=GoalsCard(on_track=goals.on_track, total=goals.total),
            complete=nw.freshness.complete and not income.unconverted,
            as_of=now,
            reporting=reporting.out(nw.currency),
        )

    cache: ResponseCache = request.app.state.response_cache
    return await cache.cached(user.id, "dashboard", {"currency": currency}, DashboardOut, compute)
