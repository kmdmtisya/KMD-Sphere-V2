"""One portfolio's income and passive income (P06-T05). Methods: docs/design/income.md.
Published by the analytics API (P06-T09)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.networth.income import (
    ZERO,
    Period,
    Totals,
    by_month,
    by_year,
    group,
    income_yield,
    monthly,
    totals,
    trailing,
)
from app.modules.portfolio.service import PortfolioService
from app.modules.portfolio.summary import Summary
from app.modules.portfolio.summary_service import SummaryService
from app.modules.transactions.holdings_service import HoldingsService
from app.modules.transactions.income_events_service import IncomeEventService, Payment


@dataclass(frozen=True)
class AssetIncome:
    asset_id: uuid.UUID | None  # None: income without an asset (cash interest)
    trailing_12m: Totals
    all_time: Totals
    value: Decimal | None  # current value of the position (None: not valued or closed)
    cost_basis: Decimal | None
    current_yield: Decimal | None  # trailing gross / value
    yield_on_cost: Decimal | None  # trailing gross / cost basis


@dataclass(frozen=True)
class TypeIncome:
    income_type: str
    trailing_12m: Totals
    all_time: Totals


@dataclass(frozen=True)
class PortfolioIncome:
    """Unrounded figures in the portfolio's base currency."""

    currency: str
    as_of: date
    trailing_12m: Totals
    monthly_average: Decimal  # trailing net / 12: passive income a month
    yearly: Decimal  # trailing net: passive income a year
    portfolio_yield: Decimal | None  # trailing gross / total value
    months: list[Period]  # the 12 calendar months ending with this month
    years: list[Period]
    by_asset: list[AssetIncome]
    by_type: list[TypeIncome]
    complete: bool  # the value the yield is measured against is complete


@dataclass(frozen=True)
class PortfolioLine:
    portfolio_id: uuid.UUID
    currency: str
    trailing_12m: Totals  # in the portfolio's currency
    converted_net: Decimal | None  # trailing net in the reporting currency; None without a rate


@dataclass(frozen=True)
class UserIncome:
    currency: str
    as_of: date
    yearly_gross: Decimal
    yearly: Decimal  # trailing net of all active portfolios, converted
    monthly_average: Decimal
    portfolios: list[PortfolioLine]
    unconverted: frozenset[str]  # portfolio currencies without a rate (left out)


class IncomeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._summaries = SummaryService(session)
        self._events = IncomeEventService(session)
        self._holdings = HoldingsService(session)

    async def portfolio(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, today: date | None = None
    ) -> PortfolioIncome:
        """Raises ResourceNotFoundError (404) unless the portfolio is the user's."""
        summary = await self._summaries.figures(user_id, portfolio_id)
        payments = await self._events.payments(portfolio_id)
        # A closed position has a cost basis of exactly 0 (ADR-0012), so no yield on cost.
        costs = {h.asset_id: h.cost_basis for h in await self._holdings.positions(portfolio_id)}
        return measure(summary, payments, costs, today or datetime.now(UTC).date())

    async def user(
        self, user_id: uuid.UUID, currency: str | None, today: date | None = None
    ) -> UserIncome:
        """Trailing income of all the user's active portfolios, each converted from its base
        currency at the latest rate (docs/design/income.md, section 7)."""
        day = today or datetime.now(UTC).date()
        reporting = await self._summaries.reporting_currency(user_id, currency)
        portfolios = await PortfolioService(self._session).list(user_id, False)
        rates = await self._summaries.rates({p.base_currency for p in portfolios}, reporting)
        lines = []
        gross = net = ZERO
        with localcontext() as ctx:
            ctx.prec = 50
            for p in portfolios:
                t = (await self.portfolio(user_id, p.id, day)).trailing_12m
                if p.base_currency == reporting:
                    factor: Decimal | None = Decimal(1)
                else:
                    rate = rates.get(p.base_currency)
                    factor = None if rate is None else rate.rate
                if factor is not None:
                    gross += t.gross * factor
                    net += t.net * factor
                lines.append(
                    PortfolioLine(
                        p.id, p.base_currency, t, None if factor is None else t.net * factor
                    )
                )
        return UserIncome(
            currency=reporting,
            as_of=day,
            yearly_gross=gross,
            yearly=net,
            monthly_average=monthly(net),
            portfolios=lines,
            unconverted=frozenset(
                p.base_currency
                for p in portfolios
                if p.base_currency != reporting and p.base_currency not in rates
            ),
        )


def measure(
    summary: Summary,
    payments: list[Payment],
    costs: dict[uuid.UUID, Decimal],
    today: date,
) -> PortfolioIncome:
    """Pure: the income figures of `payments` against a summary's values."""
    recent = trailing(payments, today)
    last = totals(recent)
    recent_by_asset = group(recent, lambda p: p.asset_id)
    assets = []
    for asset_id, items in sorted(
        group(payments, lambda p: p.asset_id).items(), key=lambda kv: str(kv[0])
    ):
        t = totals(recent_by_asset.get(asset_id, []))
        value = summary.positions.get(asset_id) if asset_id else None
        cost = costs.get(asset_id) if asset_id else None
        assets.append(
            AssetIncome(
                asset_id=asset_id,
                trailing_12m=t,
                all_time=totals(items),
                value=value,
                cost_basis=cost,
                current_yield=income_yield(t.gross, value),
                yield_on_cost=income_yield(t.gross, cost),
            )
        )
    recent_by_type = group(recent, lambda p: p.income_type)
    return PortfolioIncome(
        currency=summary.currency,
        as_of=today,
        trailing_12m=last,
        monthly_average=monthly(last.net),
        yearly=last.net,
        portfolio_yield=income_yield(last.gross, summary.total_value),
        months=by_month(payments, today),
        years=by_year(payments),
        by_asset=sorted(assets, key=lambda a: (-a.trailing_12m.gross, -a.all_time.gross)),
        by_type=[
            TypeIncome(kind, totals(recent_by_type.get(kind, [])), totals(items))
            for kind, items in sorted(group(payments, lambda p: p.income_type).items())
        ],
        complete=summary.complete,
    )
