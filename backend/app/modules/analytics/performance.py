"""Performance maths (P06-T03): external flows, simple return, CAGR, XIRR and time-weighted
return. Pure and deterministic (Decimal only, no I/O). Methods: docs/design/performance.md."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum
from itertools import pairwise

from app.modules.transactions.holdings import Entry, effective

ZERO = Decimal(0)
ONE = Decimal(1)
DAYS_PER_YEAR = Decimal(365)
PRECISION = 50
ROOT_PRECISION = 34  # XIRR and annualising powers
XIRR_TOLERANCE = Decimal("1e-12")
XIRR_MAX_STEPS = 200
XIRR_GUESS = Decimal("0.1")
# Rates at which the net present value is evaluated to find a sign change (fractions a year).
XIRR_GRID = tuple(
    Decimal(r)
    for r in (
        "-0.9999", "-0.99", "-0.9", "-0.75", "-0.5", "-0.25", "-0.1", "0", "0.1", "0.25", "0.5",
        "1", "2", "5", "10", "100", "1000", "10000",
    )
)  # fmt: skip

_INFLOWS = {"DEPOSIT", "TRANSFER_IN"}
_OUTFLOWS = {"WITHDRAWAL", "TRANSFER_OUT"}


@dataclass(frozen=True)
class Flow:
    """An amount on a date. For external flows: positive into the portfolio, negative out."""

    on: date
    amount: Decimal


@dataclass(frozen=True)
class FlowTotals:
    contributions: Decimal  # deposits and transfers in
    withdrawals: Decimal  # withdrawals and transfers out (a positive amount)

    @property
    def net_invested(self) -> Decimal:
        return self.contributions - self.withdrawals


def external_flows(entries: Iterable[Entry]) -> list[Flow]:
    """The investor's flows into (+) and out of (-) the portfolio, in its base currency at each
    posting's rate, in date order. Reversed entries and their reversals are left out."""
    flows = []
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for e in effective(entries):
            if e.transaction_type in _INFLOWS:
                flows.append(Flow(e.trade_date, e.gross_amount * e.fx))
            elif e.transaction_type in _OUTFLOWS:
                flows.append(Flow(e.trade_date, -(e.gross_amount * e.fx)))
    return [f for f in flows if f.amount != 0]


def totals(flows: Iterable[Flow]) -> FlowTotals:
    flows = list(flows)
    return FlowTotals(
        contributions=sum((f.amount for f in flows if f.amount > 0), ZERO),
        withdrawals=-sum((f.amount for f in flows if f.amount < 0), ZERO),
    )


def simple_return(gain: Decimal, contributions: Decimal) -> Decimal | None:
    """Gain relative to everything put in; None when nothing was put in."""
    if contributions <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return gain / contributions


def cagr(start_value: Decimal, end_value: Decimal, start: date, end: date) -> Decimal | None:
    """Compound annual growth between two values with no flows in between. None unless
    start_value > 0, end_value >= 0 and the period is at least 365 days."""
    days = (end - start).days
    if start_value <= 0 or end_value < 0 or days < DAYS_PER_YEAR:
        return None
    return _annualise(end_value / start_value, days)


# ----------------------------------------------------------------------------------------- XIRR


class XirrStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_FLOWS = "insufficient_flows"
    NO_SIGN_CHANGE = "no_sign_change"
    NO_RATE_IN_RANGE = "no_rate_in_range"


@dataclass(frozen=True)
class XirrResult:
    status: XirrStatus
    rate: Decimal | None = None  # annual, as a fraction (0.08 is 8%)
    unique: bool = False  # the flows change sign once, so no other rate solves them
    steps: int = 0


def xirr(flows: Iterable[Flow]) -> XirrResult:
    """The annual rate at which the flows' net present value is zero (actual/365)."""
    by_day: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for f in flows:
        by_day[f.on] += f.amount
    dated = sorted((d, a) for d, a in by_day.items() if a != 0)
    if len(dated) < 2:
        return XirrResult(XirrStatus.INSUFFICIENT_FLOWS)
    signs = [a > 0 for _, a in dated]
    if all(signs) or not any(signs):
        return XirrResult(XirrStatus.NO_SIGN_CHANGE)
    unique = sum(1 for x, y in pairwise(signs) if x != y) == 1

    with localcontext() as ctx:
        ctx.prec = ROOT_PRECISION
        first = dated[0][0]
        terms = [(Decimal((d - first).days) / DAYS_PER_YEAR, a) for d, a in dated]

        def npv(rate: Decimal) -> Decimal:
            log = (ONE + rate).ln()
            return sum((a * (-t * log).exp() for t, a in terms), ZERO)

        values = [npv(r) for r in XIRR_GRID]
        exact = [r for r, v in zip(XIRR_GRID, values, strict=True) if v == 0]
        if exact:
            best = min(exact, key=lambda r: abs(r - XIRR_GUESS))
            return XirrResult(XirrStatus.OK, best, unique)
        brackets = [
            (XIRR_GRID[i], XIRR_GRID[i + 1], values[i])
            for i in range(len(XIRR_GRID) - 1)
            if (values[i] > 0) != (values[i + 1] > 0)
        ]
        if not brackets:
            return XirrResult(XirrStatus.NO_RATE_IN_RANGE, unique=unique)
        lo, hi, at_lo = min(brackets, key=lambda b: _distance(XIRR_GUESS, b[0], b[1]))
        steps = 0
        while hi - lo > XIRR_TOLERANCE and steps < XIRR_MAX_STEPS:
            mid = (lo + hi) / 2
            at_mid = npv(mid)
            if (at_mid > 0) == (at_lo > 0):
                lo, at_lo = mid, at_mid
            else:
                hi = mid
            steps += 1
        return XirrResult(XirrStatus.OK, (lo + hi) / 2, unique, steps)


def _distance(x: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return ZERO if lo <= x <= hi else min(abs(x - lo), abs(x - hi))


# ------------------------------------------------------------------------------------------ TWR


class TwrStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"
    UNDEFINED_PERIOD = "undefined_period"


@dataclass(frozen=True)
class ValuePoint:
    """The value just before any external flow on `on`, and that day's external flow."""

    on: date
    value: Decimal
    flow: Decimal = ZERO


@dataclass(frozen=True)
class TwrResult:
    status: TwrStatus
    cumulative: Decimal | None = None
    annualized: Decimal | None = None  # only for periods of at least 365 days
    days: int = 0


def twr(points: Iterable[ValuePoint]) -> TwrResult:
    """Time-weighted return: the product of the sub-period returns between external flows."""
    points = list(points)
    if any(b.on <= a.on for a, b in pairwise(points)):
        raise ValueError("points must be in strictly increasing date order")
    if len(points) < 2:
        return TwrResult(TwrStatus.INSUFFICIENT_DATA)
    days = (points[-1].on - points[0].on).days
    with localcontext() as ctx:
        ctx.prec = PRECISION
        growth = ONE
        for start, end in pairwise(points):
            base = start.value + start.flow
            if end.value < 0 or start.value < 0:
                return TwrResult(TwrStatus.UNDEFINED_PERIOD, days=days)
            if base == 0 and end.value == 0:
                continue  # an empty portfolio earns nothing
            if base <= 0:
                return TwrResult(TwrStatus.UNDEFINED_PERIOD, days=days)
            growth *= end.value / base
        cumulative = growth - ONE
    annualized = _annualise(growth, days) if days >= DAYS_PER_YEAR and growth > 0 else None
    return TwrResult(TwrStatus.OK, cumulative, annualized, days)


def _annualise(growth: Decimal, days: int) -> Decimal:
    """growth^(365 / days) - 1, for growth >= 0 (ln(0) is -Infinity, so 0 gives -100%)."""
    with localcontext() as ctx:
        ctx.prec = ROOT_PRECISION
        return (growth.ln() * DAYS_PER_YEAR / days).exp() - ONE
