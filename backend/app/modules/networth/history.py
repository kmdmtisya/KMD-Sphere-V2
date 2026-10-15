"""Net worth over time (P14-T11): the historical value of each portfolio plus the liabilities known
on each date, in one currency. Pure and deterministic (Decimal only, no I/O). Methods:
docs/design/net-worth.md, section "History".

Rules:
- Assets on a date are the sum of each active portfolio's value on that date (rebuilt from the
  ledger, valuations and historical FX by the risk series), converted at the rate valid that day.
- A liability counts from the date its balance was recorded (`balance_as_of`). Balances are
  user-entered and their earlier history is not kept, so before that date the amount owed is
  unknown: the liability is left out and the date is marked incomplete rather than guessed.
- A date is also incomplete when a portfolio's own value is incomplete, or an amount has no
  exchange rate for the day."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from app.modules.portfolio.history import Point

ZERO = Decimal(0)
ONE = Decimal(1)
PRECISION = 50

RateAt = Callable[[str, date], Decimal | None]  # currency, day -> rate into the reporting currency


@dataclass(frozen=True)
class DebtBalance:
    currency: str
    balance: Decimal
    balance_as_of: date


@dataclass(frozen=True)
class PortfolioSeries:
    currency: str  # the portfolio's base currency (its points are in this currency)
    points: Mapping[date, Point]


@dataclass(frozen=True)
class HistoryPoint:
    on: date
    assets: Decimal
    liabilities: Decimal
    complete: bool

    @property
    def net_worth(self) -> Decimal:
        return self.assets - self.liabilities


def combine(
    days: Sequence[date],
    reporting: str,
    series: Sequence[PortfolioSeries],
    debts: Sequence[DebtBalance],
    rate: RateAt,
) -> list[HistoryPoint]:
    def into_reporting(currency: str, day: date) -> Decimal | None:
        return ONE if currency == reporting else rate(currency, day)

    out: list[HistoryPoint] = []
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for day in days:
            assets = liabilities = ZERO
            complete = True
            for s in series:
                point = s.points.get(day)
                if point is None:
                    complete = False
                    continue
                complete = complete and point.complete
                if point.value == ZERO:
                    continue
                factor = into_reporting(s.currency, day)
                if factor is None:
                    complete = False
                    continue
                assets += point.value * factor
            for d in debts:
                if d.balance_as_of > day:
                    complete = False  # the balance on this date is not known
                    continue
                factor = into_reporting(d.currency, day)
                if factor is None:
                    complete = False
                    continue
                liabilities += d.balance * factor
            out.append(HistoryPoint(day, assets, liabilities, complete))
    return out
