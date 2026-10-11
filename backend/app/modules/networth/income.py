"""Income figures (P06-T05): totals by period, by asset and by type, trailing twelve months and
yields. Pure and deterministic (Decimal only, no I/O). Methods: docs/design/income.md."""

from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from app.modules.transactions.income_events_service import Payment

ZERO = Decimal(0)
PRECISION = 50
MONTHS = 12


@dataclass(frozen=True)
class Totals:
    """Amounts in the portfolio currency, each payment at its own posting rate."""

    gross: Decimal = ZERO
    fees: Decimal = ZERO
    taxes: Decimal = ZERO  # withholding and other taxes on the income
    payments: int = 0

    @property
    def net(self) -> Decimal:
        return self.gross - self.fees - self.taxes


@dataclass(frozen=True)
class Period:
    period: str  # YYYY-MM or YYYY
    totals: Totals


def totals(payments: Iterable[Payment]) -> Totals:
    gross = fees = taxes = ZERO
    count = 0
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for p in payments:
            gross += p.gross * p.fx_rate
            fees += p.fees * p.fx_rate
            taxes += p.taxes * p.fx_rate
            count += 1
    return Totals(gross, fees, taxes, count)


def year_before(day: date) -> date:
    """The same day one year earlier (28 February for 29 February)."""
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def trailing(payments: Iterable[Payment], today: date) -> list[Payment]:
    """Payments in the trailing twelve months: after the same day a year earlier, up to and
    including today."""
    start = year_before(today)
    return [p for p in payments if start < p.paid_on <= today]


def by_month(payments: Iterable[Payment], today: date, months: int = MONTHS) -> list[Period]:
    """The `months` calendar months ending with today's month, oldest first, including months
    without income."""
    keys = []
    year, month = today.year, today.month
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    groups = group(payments, lambda p: f"{p.paid_on.year:04d}-{p.paid_on.month:02d}")
    return [Period(k, totals(groups.get(k, []))) for k in reversed(keys)]


def by_year(payments: Iterable[Payment]) -> list[Period]:
    """Every calendar year with income, oldest first."""
    groups = group(payments, lambda p: f"{p.paid_on.year:04d}")
    return [Period(k, totals(groups[k])) for k in sorted(groups)]


def monthly(yearly: Decimal) -> Decimal:
    """A twelfth of a yearly amount (an average month)."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return yearly / MONTHS


def income_yield(gross: Decimal, base: Decimal | None) -> Decimal | None:
    """Income relative to a value or a cost (a fraction); None when the base is not positive."""
    if base is None or base <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return gross / base


def group[K: Hashable](
    payments: Iterable[Payment], key: Callable[[Payment], K]
) -> dict[K, list[Payment]]:
    """Payments by key, in their original order."""
    groups: dict[K, list[Payment]] = {}
    for p in payments:
        groups.setdefault(key(p), []).append(p)
    return groups
