"""An independent oracle for the P06-T10 financial review.

Every function here is written from the specification (the ADRs and docs/financial-methods.md),
not from the application code, and uses exact rational arithmetic (`fractions.Fraction`) instead
of the application's 50-digit Decimal. Where a quantity is irrational (fractional powers, XIRR,
square roots), a different algorithm at higher precision is used and the comparison allows for
it. tests/test_cross_check.py compares the application with this module.
"""

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, Overflow, localcontext
from fractions import Fraction
from itertools import pairwise

F = Fraction
ZERO = Fraction(0)


def frac(value: Decimal | int | str | Fraction) -> Fraction:
    return Fraction(str(value)) if not isinstance(value, Fraction) else value


def half_up(x: Fraction, places: int) -> Fraction:
    """Round half away from zero to `places` decimals (ADR-0006), exactly."""
    scale = 10**places
    magnitude = math.floor(abs(x) * scale + F(1, 2))
    return F(magnitude if x >= 0 else -magnitude, scale)


def to_decimal(x: Fraction, places: int) -> Decimal:
    rounded = half_up(x, places)
    with localcontext() as ctx:
        ctx.prec = 80
        return (Decimal(rounded.numerator) / Decimal(rounded.denominator)).quantize(
            Decimal(1).scaleb(-places)
        )


# ----------------------------------------------------------------------- ledger and holdings


@dataclass(frozen=True)
class Tx:
    id: str
    kind: str
    on: date
    order: int  # creation order within the ledger
    asset: str | None
    quantity: Fraction
    gross: Fraction
    fees: Fraction
    taxes: Fraction
    fx: Fraction
    currency: str = "USD"
    reverses: str | None = None


@dataclass
class Pos:
    quantity: Fraction = field(default_factory=Fraction)
    cost: Fraction = field(default_factory=Fraction)
    realized: Fraction = field(default_factory=Fraction)
    income: Fraction = field(default_factory=Fraction)
    expenses: Fraction = field(default_factory=Fraction)


INCOME_WITH_ASSET = {"DIVIDEND", "COUPON", "RENT", "DISTRIBUTION", "INTEREST"}


def effective(ledger: Iterable[Tx]) -> list[Tx]:
    """Leave out every reversed entry and its reversal; order by date, creation, id."""
    ledger = list(ledger)
    gone = {t.reverses for t in ledger if t.reverses}
    kept = [t for t in ledger if not t.reverses and t.id not in gone]
    return sorted(kept, key=lambda t: (t.on, t.order, t.id))


def holdings(ledger: Iterable[Tx]) -> dict[str, Pos]:
    """ADR-0012 weighted average cost in the portfolio currency."""
    out: dict[str, Pos] = defaultdict(Pos)
    for t in effective(ledger):
        if t.asset is None:
            continue
        p = out[t.asset]
        if t.kind in ("BUY", "TRANSFER_IN"):
            p.quantity += t.quantity
            p.cost += (t.gross + t.fees + t.taxes) * t.fx
        elif t.kind in ("SELL", "TRANSFER_OUT"):
            removed = p.cost * t.quantity / p.quantity
            if t.kind == "SELL":
                p.realized += (t.gross - t.fees - t.taxes) * t.fx - removed
            p.cost -= removed
            p.quantity -= t.quantity
        elif t.kind in INCOME_WITH_ASSET:
            p.income += t.gross * t.fx
            p.expenses += (t.fees + t.taxes) * t.fx
        elif t.kind in ("FEE", "TAX"):
            p.expenses += (t.gross + t.fees + t.taxes) * t.fx
    return dict(out)


def cash(ledger: Iterable[Tx]) -> dict[str, Fraction]:
    """Cash per currency (docs/design/portfolio-summary.md, section 3)."""
    out: dict[str, Fraction] = defaultdict(Fraction)
    for t in effective(ledger):
        g, fe, ta = t.gross, t.fees, t.taxes
        effect = {
            "DEPOSIT": g - fe - ta,
            "WITHDRAWAL": -(g + fe + ta),
            "BUY": -(g + fe + ta),
            "SELL": g - fe - ta,
            "FEE": -(g + fe + ta),
            "TAX": -(g + fe + ta),
            "TRANSFER_IN": -(fe + ta),
            "TRANSFER_OUT": -(fe + ta),
            "VALUATION_ADJUSTMENT": F(0),
        }.get(t.kind, g - fe - ta)  # income types
        out[t.currency] += effect
    return dict(out)


def external_flows(ledger: Iterable[Tx]) -> list[tuple[date, Fraction]]:
    flows = []
    for t in effective(ledger):
        if t.kind in ("DEPOSIT", "TRANSFER_IN"):
            flows.append((t.on, t.gross * t.fx))
        elif t.kind in ("WITHDRAWAL", "TRANSFER_OUT"):
            flows.append((t.on, -t.gross * t.fx))
    return [(d, a) for d, a in flows if a != 0]


# -------------------------------------------------------------------------------- allocation


def largest_remainder(parts: Sequence[Fraction], places: int = 2) -> list[Fraction] | None:
    total = sum(parts, F(0))
    if not parts or total <= 0 or any(p < 0 for p in parts):
        return None
    unit = F(1, 10**places)
    exact = [p * 100 / total for p in parts]
    floored = [math.floor(e / unit) * unit for e in exact]
    missing = round((100 - sum(floored, F(0))) / unit)
    order = sorted(range(len(parts)), key=lambda i: (-(exact[i] - floored[i]), i))
    for i in order[:missing]:
        floored[i] += unit
    return floored


def herfindahl(values: Sequence[Fraction]) -> Fraction:
    total = sum(values, F(0))
    return sum(((v / total) ** 2 for v in values), F(0))


# ------------------------------------------------------------------- forecasts and goals


def monthly_forecast(
    initial: Fraction,
    contribution: Fraction,
    rate: Fraction,
    fee: Fraction,
    months: int,
    *,
    every: int = 1,
    growth: Fraction = ZERO,
) -> tuple[Fraction, Fraction]:
    """Monthly compounding at (rate - fee) / 12 a month, contributions at the end of every
    `every` months, growing yearly by `growth` (percentages). Returns (value, paid in)."""
    q = 1 + (rate - fee) / 100 / 12
    balance = paid = initial
    for month in range(1, months + 1):
        payment = contribution * (1 + growth / 100) ** ((month - 1) // 12)
        balance *= q
        if month % every == 0:
            balance += payment
            paid += payment
    return balance, paid


def required_monthly(
    initial: Fraction, target: Fraction, rate: Fraction, fee: Fraction, months: int
) -> Fraction:
    """Level monthly contribution reaching `target`, from the annuity closed form."""
    q = 1 + (rate - fee) / 100 / 12
    grown = initial * q**months
    if grown >= target:
        return F(0)
    if q == 1:
        return (target - grown) / months
    return (target - grown) / ((q**months - 1) / (q - 1))


# -------------------------------------------------------------------------------- returns


def simple_return(gain: Fraction, contributions: Fraction) -> Fraction | None:
    return None if contributions <= 0 else gain / contributions


def twr(points: Sequence[tuple[Fraction, Fraction]]) -> Fraction:
    """Points are (value at the end of the period's start day, flow during the period)."""
    growth = F(1)
    for (value, flow), (next_value, _) in pairwise(points):
        base = value + flow
        if base == 0 and next_value == 0:
            continue
        growth *= next_value / base
    return growth - 1


def sample_variance(returns: Sequence[Fraction]) -> Fraction:
    n = len(returns)
    mean = sum(returns, F(0)) / n
    return sum(((r - mean) ** 2 for r in returns), F(0)) / (n - 1)


def xirr_newton(flows: Sequence[tuple[date, Decimal]], guess: str = "0.1") -> Decimal | None:
    """Newton-Raphson at 80 digits (the application uses a grid and bisection at 34)."""
    with localcontext() as ctx:
        ctx.prec = 80
        first = min(d for d, _ in flows)
        terms = [(Decimal((d - first).days) / 365, a) for d, a in flows]
        rate = Decimal(guess)
        try:
            return _newton(terms, rate)
        except (Overflow, InvalidOperation, ZeroDivisionError):
            return None  # Newton diverged from this guess; the caller skips the case


def _newton(terms: list[tuple[Decimal, Decimal]], rate: Decimal) -> Decimal | None:
    with localcontext() as ctx:
        ctx.prec = 80
        for _ in range(200):
            base = 1 + rate
            npv = sum((a / base**t for t, a in terms), Decimal(0))
            slope = sum((-t * a / base ** (t + 1) for t, a in terms), Decimal(0))
            if slope == 0:
                return None
            step = npv / slope
            rate -= step
            if rate <= -1:
                return None
            if abs(step) < Decimal("1e-40"):
                return rate
    return None
