"""Historical portfolio value (P06-T08): the value at the end of each date of a series, rebuilt
from the ledger, the valuations and the historical FX rates. Pure (no I/O). Methods:
docs/design/risk.md. The same rules as the summary (docs/design/portfolio-summary.md) applied as
of each date."""

import calendar
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from enum import StrEnum

from app.modules.analytics.performance import external_flows
from app.modules.market_data.fx import end_of_day
from app.modules.portfolio.summary import cash_effect
from app.modules.transactions.holdings import Entry, effective
from app.modules.transactions.rules import POSITION_SIGN

ZERO = Decimal(0)
PRECISION = 50
MAX_POINTS = 1000

RateAt = Callable[[str, date], Decimal | None]  # currency, day -> rate into the base currency


class SeriesFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    @property
    def per_year(self) -> int:
        return {"daily": 365, "weekly": 52, "monthly": 12}[self.value]


@dataclass(frozen=True)
class Valued:
    """A valuation: the whole position's value as of a moment."""

    asset_id: uuid.UUID
    value: Decimal
    currency: str
    as_of: datetime


@dataclass(frozen=True)
class Point:
    on: date
    value: Decimal  # end of day, base currency; parts that could not be valued are left out
    flow_next: Decimal  # external flows after this date up to the next point (+ in, - out)
    complete: bool
    unpriced: int  # open positions without a valuation as of the date
    unconverted: frozenset[str]  # currencies without a historical rate on the date
    flows: tuple[tuple[date, Decimal], ...] = ()  # the dated flows that make up `flow_next`


def dates(start: date, end: date, frequency: SeriesFrequency) -> list[date]:
    """`start`, then the end of each period up to `end`, and `end` itself. Monthly periods end
    on the last day of each month; weekly ones every 7 days."""
    if end < start:
        raise ValueError("end must not be before start")
    out = [start]
    if frequency == SeriesFrequency.DAILY:
        out += [start + timedelta(days=i) for i in range(1, (end - start).days + 1)]
    elif frequency == SeriesFrequency.WEEKLY:
        day = start + timedelta(days=7)
        while day < end:
            out.append(day)
            day += timedelta(days=7)
    else:
        year, month = start.year, start.month
        while True:
            last = date(year, month, calendar.monthrange(year, month)[1])
            if last >= end:
                break
            if last > start:
                out.append(last)
            year, month = (year, month + 1) if month < 12 else (year + 1, 1)
    if out[-1] != end:
        out.append(end)
    if len(out) > MAX_POINTS:
        raise ValueError(f"at most {MAX_POINTS} points; choose a longer frequency")
    return out


def build(
    entries: Iterable[Entry],
    valuations: Iterable[Valued],
    rate: RateAt,
    days: list[date],
) -> list[Point]:
    """The portfolio's value at the end of each of `days` (ascending)."""
    ledger = effective(entries)
    flows = external_flows(ledger)
    by_asset: dict[uuid.UUID, list[Valued]] = defaultdict(list)
    for row in sorted(valuations, key=lambda v: v.as_of):
        by_asset[row.asset_id].append(row)
    traded = {e.asset_id for e in ledger if e.transaction_type in POSITION_SIGN}

    points = []
    quantity: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    cash: dict[str, Decimal] = defaultdict(lambda: ZERO)
    i = 0
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for n, day in enumerate(days):
            while i < len(ledger) and ledger[i].trade_date <= day:
                e = ledger[i]
                if (
                    e.asset_id is not None
                    and e.quantity is not None
                    and e.transaction_type in POSITION_SIGN
                ):
                    quantity[e.asset_id] += POSITION_SIGN[e.transaction_type] * e.quantity
                cash[e.currency] += cash_effect(e)
                i += 1
            value, unpriced, unconverted = ZERO, 0, set()
            for asset_id in sorted(set(by_asset) | {a for a in traded if a is not None}):
                if asset_id in traded and quantity[asset_id] <= 0:
                    continue  # not held on this date
                latest = _latest(by_asset.get(asset_id, []), day)
                if latest is None:
                    # Held but not valued yet; an asset known only from valuations (never
                    # traded) is simply not in the portfolio before its first valuation.
                    unpriced += asset_id in traded
                    continue
                converted = _convert(latest.value, latest.currency, day, rate)
                if converted is None:
                    unconverted.add(latest.currency)
                else:
                    value += converted
            for currency, balance in cash.items():
                if balance == 0:
                    continue
                converted = _convert(balance, currency, day, rate)
                if converted is None:
                    unconverted.add(currency)
                else:
                    value += converted
            following = days[n + 1] if n + 1 < len(days) else day
            between = tuple((f.on, f.amount) for f in flows if day < f.on <= following)
            flow_next = sum((a for _, a in between), ZERO)
            points.append(
                Point(
                    day,
                    value,
                    flow_next,
                    not unpriced and not unconverted,
                    unpriced,
                    frozenset(unconverted),
                    between,
                )
            )
    return points


def _latest(rows: list[Valued], day: date) -> Valued | None:
    """The newest valuation as of the end of `day` (UTC); `rows` are sorted by time."""
    end = end_of_day(day)
    found = None
    for v in rows:
        if v.as_of > end:
            break
        found = v
    return found


def _convert(amount: Decimal, currency: str, day: date, rate: RateAt) -> Decimal | None:
    r = rate(currency, day)
    return None if r is None else amount * r
