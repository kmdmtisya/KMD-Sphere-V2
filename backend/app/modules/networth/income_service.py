"""One portfolio's income and passive income (P06-T05). Methods: docs/design/income.md.
Published by the analytics API (P06-T09)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.networth.income import (
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


class IncomeService:
    def __init__(self, session: AsyncSession) -> None:
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
