"""Historical rates (P11-T05): three rate concepts kept apart, and a daily rate history that says
where a rate is missing instead of filling it in.

- `transaction`: the rate recorded on a ledger posting, chosen once at posting (trade date, the
  pair's own rate) and never recomputed.
- `historical_valuation`: a past valuation, a past income payment or a value series: the rate
  valid at the end of that day (historical rule, at most 7 days old), possibly through the pivot.
- `current_reporting`: today's figures in the reporting currency, from the latest snapshot
  (P11-T04).

A past figure is never converted with today's rate. A day without a usable rate is flagged
`rate_missing`, never substituted; a rate from an earlier day inside the 7-day window (a weekend,
a holiday) is used under the historical rule and flagged `from_earlier_day`."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidValueError
from app.modules.market_data.fx import (
    HISTORICAL_MAX_AGE,
    FxRateUnavailable,
    StoredRate,
    end_of_day,
    select_via,
)
from app.modules.market_data.models import FxRate

MAX_HISTORY_DAYS = 366


class RateConcept(StrEnum):
    TRANSACTION = "transaction"
    HISTORICAL_VALUATION = "historical_valuation"
    CURRENT_REPORTING = "current_reporting"


@dataclass(frozen=True)
class HistoryPoint:
    day: date
    rate: Decimal | None
    rate_timestamp: datetime | None
    provider: str | None
    path: tuple[str, ...] | None
    rate_missing: bool
    from_earlier_day: bool


async def _candidates(
    session: AsyncSession, currencies: set[str], start: datetime, end: datetime
) -> list[StoredRate]:
    rows = await session.execute(
        select(FxRate).where(
            FxRate.base_currency.in_(currencies),
            FxRate.quote_currency.in_(currencies),
            FxRate.rate_timestamp <= end,
            FxRate.rate_timestamp >= start - HISTORICAL_MAX_AGE,
        )
    )
    return [
        StoredRate(
            r.base_currency,
            r.quote_currency,
            r.rate,
            r.provider,
            r.rate_timestamp,
            r.retrieved_at,
            tuple(r.rate_path) if r.rate_path else None,
        )
        for r in rows.scalars()
    ]


async def rate_history(
    session: AsyncSession, base: str, quote: str, start: date, end: date, pivot: str
) -> list[HistoryPoint]:
    """One point per calendar day from `start` to `end`: the historical rate at that day's end."""
    if end < start:
        raise InvalidValueError("The end date is before the start date.")
    if (end - start).days + 1 > MAX_HISTORY_DAYS:
        raise InvalidValueError(f"A rate history covers at most {MAX_HISTORY_DAYS} days.")
    candidates = await _candidates(
        session, {base, quote, pivot}, end_of_day(start), end_of_day(end)
    )
    points: list[HistoryPoint] = []
    day = start
    while day <= end:
        at = end_of_day(day)
        try:
            q = select_via(base, quote, candidates, at, now=at, pivot=pivot)
        except FxRateUnavailable:
            points.append(HistoryPoint(day, None, None, None, None, True, False))
        else:
            points.append(
                HistoryPoint(
                    day,
                    q.rate,
                    q.as_of,
                    q.provider,
                    q.path,
                    False,
                    base != quote and q.as_of.date() < day,
                )
            )
        day += timedelta(days=1)
    return points
