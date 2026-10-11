"""One portfolio's value history and risk metrics (P06-T08). Methods: docs/design/risk.md.
Published by the analytics API (P06-T09)."""

import bisect
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import require_found
from app.core.errors import InvalidValueError
from app.modules.analytics.risk import Observation, Risk, measure
from app.modules.market_data.fx import (
    HISTORICAL_MAX_AGE,
    FxRateUnavailable,
    StoredRate,
    end_of_day,
    select,
)
from app.modules.market_data.service import FxService
from app.modules.portfolio import history
from app.modules.portfolio.history import Point, SeriesFrequency, Valued
from app.modules.portfolio.repository import PortfolioRepository
from app.modules.transactions.holdings_service import HoldingsService
from app.modules.transactions.valuations_service import ValuationService


@dataclass(frozen=True)
class PortfolioRisk:
    currency: str
    frequency: SeriesFrequency
    start: date
    end: date
    points: list[Point]
    risk: Risk


class RiskService:
    def __init__(self, session: AsyncSession) -> None:
        self._portfolios = PortfolioRepository(session)
        self._holdings = HoldingsService(session)
        self._valuations = ValuationService(session)
        self._fx = FxService(session)

    async def portfolio(
        self,
        user_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        frequency: SeriesFrequency = SeriesFrequency.MONTHLY,
        start: date | None = None,
        end: date | None = None,
        now: datetime | None = None,
    ) -> PortfolioRisk:
        """Raises ResourceNotFoundError (404) unless the portfolio is the user's, and
        InvalidValueError for a range outside the data or too many points."""
        portfolio = require_found(await self._portfolios.get(user_id, portfolio_id), "portfolio")
        moment = now or datetime.now(UTC)
        today = moment.date()
        entries = await self._holdings.entries(portfolio_id)
        valued = [
            Valued(v.asset_id, v.value, v.currency, v.as_of)
            for v in await self._valuations.all_rows(portfolio_id)
        ]
        first = min(
            [e.trade_date for e in entries] + [v.as_of.date() for v in valued], default=today
        )
        start = start or first
        end = end or today
        if end > today:
            raise InvalidValueError("end must not be after today")
        try:
            days = history.dates(start, end, frequency)
        except ValueError as e:
            raise InvalidValueError(str(e)) from e
        base = portfolio.base_currency
        currencies = {e.currency for e in entries} | {v.currency for v in valued}
        stored = await self._fx.history(currencies, base, end_of_day(start), end_of_day(end))
        rate = _RateBook(base, stored, moment)
        points = history.build(entries, valued, rate, days)
        risk = measure(
            [Observation(p.on, p.value, p.flow_next, p.complete) for p in points],
            frequency.per_year,
        )
        return PortfolioRisk(base, frequency, start, end, points, risk)


class _RateBook:
    """Historical rates into the base currency by the P05-T06 rule (the newest rate at or
    before the end of the day, at most 7 days old, the opposite pair inverted only when there
    is no direct rate), looked up over a bounded window of stored rates."""

    def __init__(self, base: str, stored: list[StoredRate], now: datetime) -> None:
        self._base = base
        self._now = now
        self._by_currency: dict[str, list[StoredRate]] = defaultdict(list)
        for r in stored:
            other = r.base_currency if r.quote_currency == base else r.quote_currency
            self._by_currency[other].append(r)
        for rows in self._by_currency.values():
            rows.sort(key=lambda r: r.rate_timestamp)
        self._times = {c: [r.rate_timestamp for r in rows] for c, rows in self._by_currency.items()}
        self._cache: dict[tuple[str, date], Decimal | None] = {}

    def __call__(self, currency: str, day: date) -> Decimal | None:
        key = (currency, day)
        if key not in self._cache:
            at = end_of_day(day)
            rows, times = self._by_currency.get(currency, []), self._times.get(currency, [])
            # Only bounds the search; `select` applies the age and as-of rules itself.
            window = rows[
                bisect.bisect_left(times, at - HISTORICAL_MAX_AGE) : bisect.bisect_right(times, at)
            ]
            try:
                self._cache[key] = select(currency, self._base, window, at, now=self._now).rate
            except FxRateUnavailable:
                self._cache[key] = None
        return self._cache[key]
