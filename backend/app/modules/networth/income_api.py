"""Income endpoints (P06-T09): one portfolio's income and the user's passive income across their
portfolios, cached per user (app/core/cache.py). Methods: docs/design/income.md."""

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, not_found
from app.core.cache import ResponseCache
from app.core.money import CURRENCY_PATTERN, DecimalString, Money, minor_units, round_half_up
from app.db.session import get_session
from app.modules.fx.reporting import ReportingDep
from app.modules.fx.schemas import ReportingOut
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.networth.income import Period, Totals
from app.modules.networth.income_service import IncomeService

router = APIRouter(tags=["income"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class TotalsOut(BaseModel):
    gross: Money
    fees: Money
    taxes: Money = Field(description="Withholding and other taxes on the income")
    net: Money
    payments: int


class PeriodOut(BaseModel):
    period: str = Field(description="YYYY-MM or YYYY")
    totals: TotalsOut


class AssetIncomeOut(BaseModel):
    asset_id: uuid.UUID | None = Field(description="Null: income without an asset (cash interest)")
    trailing_12m: TotalsOut
    all_time: TotalsOut
    current_yield_percent: DecimalString | None
    yield_on_cost_percent: DecimalString | None


class TypeIncomeOut(BaseModel):
    income_type: str
    trailing_12m: TotalsOut
    all_time: TotalsOut


class PortfolioIncomeOut(BaseModel):
    portfolio_id: uuid.UUID
    currency: str
    as_of: date
    trailing_12m: TotalsOut
    monthly: Money = Field(description="Trailing 12 months net / 12")
    yearly: Money = Field(description="Trailing 12 months net")
    portfolio_yield_percent: DecimalString | None = Field(
        description="Trailing gross / total value; null when the value is not positive"
    )
    months: list[PeriodOut]
    years: list[PeriodOut]
    by_asset: list[AssetIncomeOut]
    by_type: list[TypeIncomeOut]
    complete: bool


class PortfolioIncomeLine(BaseModel):
    portfolio_id: uuid.UUID
    yearly: Money = Field(description="Trailing net in the portfolio's currency")
    value: Money | None = Field(description="The same in the summary currency; null without a rate")


class IncomeSummaryOut(BaseModel):
    currency: str
    monthly: Money = Field(description="Passive income a month: trailing 12 months net / 12")
    yearly: Money = Field(description="Passive income a year: trailing 12 months net")
    yearly_gross: Money
    portfolios: list[PortfolioIncomeLine]
    unconverted_currencies: list[str]
    complete: bool
    as_of: date
    reporting: ReportingOut | None = Field(
        default=None, description="The rate snapshot the conversions used (P11-T06)"
    )


def _money(currency: str) -> Callable[[Decimal], Money]:
    places = minor_units(currency)
    return lambda amount: Money(amount=round_half_up(amount, places), currency=currency)


def _totals(t: Totals, money: Callable[[Decimal], Money]) -> TotalsOut:
    return TotalsOut(
        gross=money(t.gross), fees=money(t.fees), taxes=money(t.taxes), net=money(t.net),
        payments=t.payments,
    )  # fmt: skip


def _percent(fraction: Decimal | None) -> Decimal | None:
    return None if fraction is None else round_half_up(fraction * 100, 2)


async def portfolio_income_out(
    session: AsyncSession, user_id: uuid.UUID, portfolio_id: uuid.UUID
) -> PortfolioIncomeOut:
    """One portfolio's income as the endpoint returns it (also used by the reports)."""
    i = await IncomeService(session).portfolio(user_id, portfolio_id)
    money = _money(i.currency)

    def periods(items: list[Period]) -> list[PeriodOut]:
        return [PeriodOut(period=p.period, totals=_totals(p.totals, money)) for p in items]

    return PortfolioIncomeOut(
        portfolio_id=portfolio_id,
        currency=i.currency,
        as_of=i.as_of,
        trailing_12m=_totals(i.trailing_12m, money),
        monthly=money(i.monthly_average),
        yearly=money(i.yearly),
        portfolio_yield_percent=_percent(i.portfolio_yield),
        months=periods(i.months),
        years=periods(i.years),
        by_asset=[
            AssetIncomeOut(
                asset_id=a.asset_id,
                trailing_12m=_totals(a.trailing_12m, money),
                all_time=_totals(a.all_time, money),
                current_yield_percent=_percent(a.current_yield),
                yield_on_cost_percent=_percent(a.yield_on_cost),
            )
            for a in i.by_asset
        ],
        by_type=[
            TypeIncomeOut(
                income_type=t.income_type,
                trailing_12m=_totals(t.trailing_12m, money),
                all_time=_totals(t.all_time, money),
            )
            for t in i.by_type
        ],
        complete=i.complete,
    )


async def income_summary_out(
    session: AsyncSession, user_id: uuid.UUID, currency: str | None
) -> IncomeSummaryOut:
    """Passive income across the user's portfolios as the endpoint returns it (also used by the
    reports); the endpoint adds the rate snapshot."""
    u = await IncomeService(session).user(user_id, currency)
    money = _money(u.currency)
    return IncomeSummaryOut(
        currency=u.currency,
        monthly=money(u.monthly_average),
        yearly=money(u.yearly),
        yearly_gross=money(u.yearly_gross),
        portfolios=[
            PortfolioIncomeLine(
                portfolio_id=line.portfolio_id,
                yearly=_money(line.currency)(line.trailing_12m.net),
                value=None if line.converted_net is None else money(line.converted_net),
            )
            for line in u.portfolios
        ],
        unconverted_currencies=sorted(u.unconverted),
        complete=not u.unconverted,
        as_of=u.as_of,
    )


def _cache(request: Request) -> ResponseCache:
    cache: ResponseCache = request.app.state.response_cache
    return cache


@router.get(
    "/api/v1/portfolios/{portfolio_id}/income",
    response_model=PortfolioIncomeOut,
    responses={**UNAUTHORIZED, **not_found("portfolio")},
)
async def portfolio_income(
    portfolio_id: uuid.UUID, request: Request, user: CurrentUserDep, session: SessionDep
) -> PortfolioIncomeOut:
    """Dividends, interest, coupons, rent and distributions: trailing 12 months, by month, year,
    asset and type, and yields."""

    async def compute() -> PortfolioIncomeOut:
        return await portfolio_income_out(session, user.id, portfolio_id)

    return await _cache(request).cached(
        user.id, "income", {"portfolio": portfolio_id}, PortfolioIncomeOut, compute
    )


@router.get("/api/v1/income/summary", response_model=IncomeSummaryOut, responses=UNAUTHORIZED)
async def income_summary(
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
) -> IncomeSummaryOut:
    """Passive income across all active portfolios, each converted at the latest rate."""

    async def compute() -> IncomeSummaryOut:
        out = await income_summary_out(session, user.id, currency)
        out.reporting = reporting.out(out.currency)
        return out

    return await _cache(request).cached(
        user.id, "income-summary", {"currency": currency}, IncomeSummaryOut, compute
    )
