"""Quantitative features of a universe instrument (P12-T03.1). Pure and Decimal-only.

Price features come from stored daily closes over the trailing year, sampled to the last close of
each week, and reuse the risk maths of the analytics module (docs/design/risk.md): annualised
volatility of weekly returns, the largest fall from a running peak, and the trailing return. They
describe the past; none is a forecast. A feature that cannot be measured is reported as missing
with the reason, never filled in."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from app.modules.analytics.risk import max_drawdown, volatility
from app.modules.assets.liquidity import Liquidity

ONE = Decimal(1)
WINDOW_DAYS = 365
# The trailing return needs a first close at least this many days before the last one.
MIN_RETURN_SPAN_DAYS = 300
# Volatility and drawdown need at least this many weekly returns (half a year).
MIN_WEEKLY_RETURNS = 26
WEEKS_A_YEAR = 52


class Feature(StrEnum):
    TRAILING_RETURN = "trailing_return"
    VOLATILITY = "volatility"
    MAX_DRAWDOWN = "max_drawdown"
    EXPENSE_RATIO = "expense_ratio"
    LIQUIDITY = "liquidity"
    RISK_LEVEL = "risk_level"


@dataclass(frozen=True)
class Close:
    on: date
    price: Decimal


@dataclass(frozen=True)
class Missing:
    feature: Feature
    reason: str


@dataclass(frozen=True)
class Features:
    risk_level: int
    liquidity: Liquidity
    priced: bool  # the class is valued from market prices
    trailing_return: Decimal | None = None
    volatility: Decimal | None = None  # annualised
    max_drawdown: Decimal | None = None  # a fall as a positive fraction
    expense_ratio: Decimal | None = None  # a fraction a year (0.002 is 0.2%)
    fund: bool = False  # the class has an expense ratio (ETFs, mutual funds)
    last_close: date | None = None
    weeks: int = 0
    stale_prices: bool = False
    missing: tuple[Missing, ...] = ()


def weekly(closes: Sequence[Close]) -> list[Close]:
    """The last close of each ISO week, in date order."""
    by_week: dict[tuple[int, int], Close] = {}
    for c in sorted(closes, key=lambda c: c.on):
        year, week, _ = c.on.isocalendar()
        by_week[(year, week)] = c
    return sorted(by_week.values(), key=lambda c: c.on)


def compute(
    closes: Sequence[Close],
    *,
    risk_level: int,
    liquidity: Liquidity,
    priced: bool,
    fund: bool,
    expense_ratio: Decimal | None,
    today: date,
    stale_after: timedelta,
) -> Features:
    """Every feature, or a reason it is missing. `closes` may hold any history: only the trailing
    year up to `today` is used."""
    missing: list[Missing] = []
    window = [c for c in closes if today - timedelta(days=WINDOW_DAYS) <= c.on <= today]
    trailing = vol = fall = None
    weeks: list[Close] = []
    last = max((c.on for c in window), default=None)
    stale = False
    if not priced:
        for f in (Feature.TRAILING_RETURN, Feature.VOLATILITY, Feature.MAX_DRAWDOWN):
            missing.append(Missing(f, "Valued manually: there are no market prices."))
    elif not window:
        for f in (Feature.TRAILING_RETURN, Feature.VOLATILITY, Feature.MAX_DRAWDOWN):
            missing.append(Missing(f, "No market prices in the last year."))
    else:
        first = min(window, key=lambda c: c.on)
        latest = max(window, key=lambda c: c.on)
        stale = today - latest.on > stale_after
        if (latest.on - first.on).days >= MIN_RETURN_SPAN_DAYS:
            trailing = latest.price / first.price - ONE
        else:
            missing.append(
                Missing(Feature.TRAILING_RETURN, "Less than 10 months of prices in the last year.")
            )
        weeks = weekly(window)
        returns = [b.price / a.price - ONE for a, b in pairwise(weeks)]
        if len(returns) >= MIN_WEEKLY_RETURNS:
            _, vol = volatility(returns, WEEKS_A_YEAR)
            fall = -max_drawdown([(c.on, c.price) for c in weeks]).depth
        else:
            reason = f"Fewer than {MIN_WEEKLY_RETURNS} weeks of prices in the last year."
            missing.append(Missing(Feature.VOLATILITY, reason))
            missing.append(Missing(Feature.MAX_DRAWDOWN, reason))
    if fund and expense_ratio is None:
        missing.append(Missing(Feature.EXPENSE_RATIO, "The fund's expense ratio is not recorded."))
    if liquidity is Liquidity.UNKNOWN:
        missing.append(Missing(Feature.LIQUIDITY, "Liquidity is unknown for this asset class."))
    return Features(
        risk_level=risk_level,
        liquidity=liquidity,
        priced=priced,
        trailing_return=trailing,
        volatility=vol,
        max_drawdown=fall,
        expense_ratio=expense_ratio if fund else None,
        fund=fund,
        last_close=last,
        weeks=len(weeks),
        stale_prices=stale,
        missing=tuple(missing),
    )
