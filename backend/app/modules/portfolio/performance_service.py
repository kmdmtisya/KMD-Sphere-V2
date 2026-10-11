"""One portfolio's performance (P06-T03): the analytics maths applied to its ledger and summary.
Methods: docs/design/performance.md. Published by the analytics API (P06-T09)."""

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.performance import (
    Flow,
    XirrResult,
    external_flows,
    simple_return,
    totals,
    xirr,
)
from app.modules.portfolio.assumed import with_assumed_deposits
from app.modules.portfolio.summary_service import SummaryService
from app.modules.transactions.holdings_service import HoldingsService


@dataclass(frozen=True)
class PortfolioPerformance:
    """Unrounded figures in the portfolio's base currency."""

    currency: str
    as_of: date
    total_value: Decimal
    contributions: Decimal
    withdrawals: Decimal
    net_invested: Decimal
    total_gain: Decimal  # total_value - net_invested
    simple_return: Decimal | None  # total_gain / contributions
    money_weighted: XirrResult
    realized_pl: Decimal
    unrealized_pl: Decimal
    income: Decimal
    expenses: Decimal
    complete: bool  # false when assets are unpriced or currencies unconverted
    first_flow: date | None
    assumed_deposits: Decimal = Decimal(0)  # counted as contributions, in the base currency
    assumed_count: int = 0


class PerformanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._summaries = SummaryService(session)
        self._holdings = HoldingsService(session)

    async def portfolio(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, today: date | None = None
    ) -> PortfolioPerformance:
        """Raises ResourceNotFoundError (404) unless the portfolio is the user's."""
        summary = await self._summaries.figures(user_id, portfolio_id, assume_deposits=True)
        entries, assumed = with_assumed_deposits(await self._holdings.entries(portfolio_id))
        flows = external_flows(entries)
        result = measure(
            summary.currency,
            today or datetime.now(UTC).date(),
            summary.total_value,
            flows,
            realized_pl=summary.realized_pl,
            unrealized_pl=summary.unrealized_pl,
            income=summary.income,
            expenses=summary.expenses,
            complete=summary.complete,
        )
        return replace(
            result,
            assumed_deposits=sum((a.base_amount for a in assumed), Decimal(0)),
            assumed_count=len(assumed),
        )


def measure(
    currency: str,
    as_of: date,
    total_value: Decimal,
    flows: list[Flow],
    *,
    realized_pl: Decimal,
    unrealized_pl: Decimal,
    income: Decimal,
    expenses: Decimal,
    complete: bool,
) -> PortfolioPerformance:
    """Pure: the performance of a value reached through `flows` (external flows, + in)."""
    t = totals(flows)
    gain = total_value - t.net_invested
    # The investor's view: money in is negative, money out and today's value are positive.
    investor = [Flow(f.on, -f.amount) for f in flows] + [Flow(as_of, total_value)]
    return PortfolioPerformance(
        currency=currency,
        as_of=as_of,
        total_value=total_value,
        contributions=t.contributions,
        withdrawals=t.withdrawals,
        net_invested=t.net_invested,
        total_gain=gain,
        simple_return=simple_return(gain, t.contributions),
        money_weighted=xirr(investor),
        realized_pl=realized_pl,
        unrealized_pl=unrealized_pl,
        income=income,
        expenses=expenses,
        complete=complete,
        first_flow=min((f.on for f in flows), default=None),
    )
