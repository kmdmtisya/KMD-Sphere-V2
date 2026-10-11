"""Risk metrics (P06-T08): period returns, volatility, maximum drawdown and the time-weighted
return of a value series. Pure and deterministic (Decimal only). Methods: docs/design/risk.md."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum
from itertools import pairwise

from app.modules.analytics.performance import TwrResult, ValuePoint, twr

ZERO = Decimal(0)
ONE = Decimal(1)
PRECISION = 34
MIN_RETURNS = 12  # fewer period returns are not enough to measure risk (P06-T10 review)


class RiskStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"  # fewer than MIN_RETURNS period returns
    INCOMPLETE_DATA = "incomplete_data"  # a point could not be fully valued
    UNDEFINED_PERIOD = "undefined_period"  # a period starts at zero or below but ends with value


@dataclass(frozen=True)
class Observation:
    on: date
    value: Decimal  # end of day
    flow_next: Decimal  # external flows during the next period (+ in, - out)
    complete: bool = True


@dataclass(frozen=True)
class Drawdown:
    depth: Decimal  # fall from the peak, a fraction <= 0 (-0.25 is a 25% fall)
    peak: date
    trough: date
    recovered: date | None  # when the index regained the peak; None if it has not


@dataclass(frozen=True)
class Risk:
    status: RiskStatus
    points: int
    returns: tuple[Decimal, ...] = ()
    period_volatility: Decimal | None = None  # sample standard deviation of period returns
    volatility: Decimal | None = None  # annualised: period volatility x sqrt(periods a year)
    max_drawdown: Drawdown | None = None
    time_weighted: TwrResult | None = None
    incomplete_points: int = 0


def measure(series: Sequence[Observation], periods_per_year: int) -> Risk:
    points = len(series)
    incomplete = sum(1 for o in series if not o.complete)
    if incomplete:
        return Risk(RiskStatus.INCOMPLETE_DATA, points, incomplete_points=incomplete)
    returns = period_returns(series)
    if returns is None:
        return Risk(RiskStatus.UNDEFINED_PERIOD, points)
    if len(returns) < MIN_RETURNS:
        return Risk(RiskStatus.INSUFFICIENT_DATA, points, tuple(r for _, r in returns))
    period, annual = volatility([r for _, r in returns], periods_per_year)
    return Risk(
        RiskStatus.OK,
        points,
        tuple(r for _, r in returns),
        period,
        annual,
        max_drawdown(index(series[0].on, returns)),
        twr(ValuePoint(o.on, o.value, o.flow_next) for o in series),
    )


def period_returns(series: Sequence[Observation]) -> list[tuple[date, Decimal]] | None:
    """r = V_next / (V + F) - 1 for each period, with the period's external flows F counted at
    its start. A period that starts and ends empty has no return (skipped); one that starts at
    zero or below but ends with a value is undefined (None for the whole series)."""
    out = []
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for start, end in pairwise(series):
            base = start.value + start.flow_next
            if base == 0 and end.value == 0:
                continue
            if base <= 0 or end.value < 0:
                return None
            out.append((end.on, end.value / base - ONE))
    return out


def volatility(returns: Sequence[Decimal], periods_per_year: int) -> tuple[Decimal, Decimal]:
    """Sample standard deviation (n - 1) of the returns, and the same annualised."""
    n = len(returns)
    if n < 2:
        raise ValueError("volatility needs at least two returns")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        mean = sum(returns, ZERO) / n
        variance = sum(((r - mean) ** 2 for r in returns), ZERO) / (n - 1)
        period = variance.sqrt()
        return period, period * Decimal(periods_per_year).sqrt()


def index(start: date, returns: Sequence[tuple[date, Decimal]]) -> list[tuple[date, Decimal]]:
    """The growth of 1 invested at `start`, linking the period returns (flows removed)."""
    out = [(start, ONE)]
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for on, r in returns:
            out.append((on, out[-1][1] * (ONE + r)))
    return out


def max_drawdown(levels: Sequence[tuple[date, Decimal]]) -> Drawdown:
    """The largest fall from a running peak, with its peak, trough and recovery dates. The
    earliest of equal falls is reported; a series that never falls has depth 0."""
    peak_on, peak = levels[0]
    worst = Drawdown(ZERO, peak_on, peak_on, peak_on)
    current_peak_on = peak_on
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for on, level in levels:
            if level > peak:
                peak, current_peak_on = level, on
                continue
            fall = level / peak - ONE
            if fall < worst.depth:
                worst = Drawdown(fall, current_peak_on, on, None)
        if worst.depth < 0:
            target = next(lv for d, lv in levels if d == worst.peak)
            recovered = next((d for d, lv in levels if d > worst.trough and lv >= target), None)
            worst = Drawdown(worst.depth, worst.peak, worst.trough, recovered)
    return worst
