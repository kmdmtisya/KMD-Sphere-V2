"""Net worth history for the signed-in user (P14-T11). Rules: app/modules/networth/history.py."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidValueError
from app.core.money import Money, minor_units, round_half_up
from app.modules.market_data.fx import end_of_day
from app.modules.market_data.service import FxService
from app.modules.networth import history as calc
from app.modules.networth.repository import LiabilityRepository
from app.modules.networth.schemas import NetWorthHistoryOut, NetWorthPoint
from app.modules.portfolio import history
from app.modules.portfolio.history import SeriesFrequency
from app.modules.portfolio.risk_service import PortfolioRisk, RateBook, RiskService
from app.modules.portfolio.service import PortfolioService
from app.modules.portfolio.summary_service import SummaryService

NOTICE = (
    "Rebuilt from your ledger, valuations and the exchange rates of each date. A liability counts "
    "from the date its balance was recorded: before that its balance is not known, so those dates "
    "leave it out and are marked incomplete. Past values are estimates, not a record of what any "
    "account statement showed."
)


class NetWorthHistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._risk = RiskService(session)
        self._summaries = SummaryService(session)
        self._portfolios = PortfolioService(session)
        self._liabilities = LiabilityRepository(session)
        self._fx = FxService(session)

    async def user(
        self,
        user_id: uuid.UUID,
        currency: str | None,
        frequency: SeriesFrequency,
        start: date | None,
        end: date | None,
        now: datetime,
    ) -> NetWorthHistoryOut:
        """Raises InvalidValueError for a range after today or with too many points."""
        reporting = await self._summaries.reporting_currency(user_id, currency)
        today = now.astimezone(UTC).date()
        end = end or today
        if end > today:
            raise InvalidValueError("end must not be after today")
        rows = await self._liabilities.list_for(user_id)
        debts = [calc.DebtBalance(r.currency, r.balance, r.balance_as_of) for r in rows]
        portfolios = await self._portfolios.list(user_id, False)

        results = [
            await self._risk.portfolio(user_id, p.id, frequency, start, end, now)
            for p in portfolios
        ]
        if start is None and results:
            # Each portfolio starts at its own first entry; put them on one common start.
            earliest = min(r.start for r in results)
            results = [
                r
                if r.start == earliest
                else await self._risk.portfolio(user_id, p.id, frequency, earliest, end, now)
                for p, r in zip(portfolios, results, strict=True)
            ]
        first = min([r.start for r in results] + [d.balance_as_of for d in debts], default=None)
        first = start or first
        days = _days(results, first, end, frequency)

        currencies = {p.base_currency for p in portfolios} | {d.currency for d in debts}
        stored = (
            await self._fx.history(currencies, reporting, end_of_day(days[0]), end_of_day(days[-1]))
            if days
            else []
        )
        series = [
            calc.PortfolioSeries(p.base_currency, {pt.on: pt for pt in r.points})
            for p, r in zip(portfolios, results, strict=True)
        ]
        combined = calc.combine(days, reporting, series, debts, RateBook(reporting, stored, now))
        places = minor_units(reporting)

        def money(amount: Decimal) -> Money:
            return Money(amount=round_half_up(amount, places), currency=reporting)

        points = [
            NetWorthPoint(
                on=c.on,
                assets=money(c.assets),
                liabilities=money(c.liabilities),
                net_worth=money(c.net_worth),
                complete=c.complete,
            )
            for c in combined
        ]
        incomplete = sum(1 for p in points if not p.complete)
        return NetWorthHistoryOut(
            currency=reporting,
            frequency=frequency,
            start=days[0] if days else first or end,
            end=end,
            points=points,
            portfolio_count=len(portfolios),
            liability_count=len(debts),
            incomplete_points=incomplete,
            complete=incomplete == 0,
            notice=NOTICE,
            as_of=now,
        )


def _days(
    results: list[PortfolioRisk], first: date | None, end: date, frequency: SeriesFrequency
) -> list[date]:
    if results:
        return [p.on for p in results[0].points]
    if first is None:
        return []
    try:
        return history.dates(first, end, frequency)
    except ValueError as e:
        raise InvalidValueError(str(e)) from e
