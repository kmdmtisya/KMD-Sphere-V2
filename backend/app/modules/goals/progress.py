"""Goal progress (P06-T06): pure and deterministic, on the forecast engine. Methods:
docs/design/goals.md. The status is an estimate under the stated assumptions, never a promise."""

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import Literal

from app.core.money import minor_units, round_half_up
from app.modules.forecasting.engine import (
    MAX_YEARS,
    ForecastInput,
    Frequency,
    months_to_reach,
    required_contribution_by,
    value_after,
)

ZERO = Decimal(0)
HUNDRED = Decimal(100)
PRECISION = 50
SEARCH_MONTHS = MAX_YEARS * 12
NOTICE = (
    "Goal status and dates are estimates based on the assumptions shown. They are not guaranteed."
)
Status = Literal["on_track", "behind"]


@dataclass(frozen=True)
class Assumptions:
    contribution: Decimal  # per contribution period, first year
    returns: Mapping[str, Decimal]  # scenario kind -> annual return percent; "base" is required
    contribution_frequency: Frequency = Frequency.MONTHLY
    contribution_growth_percent: Decimal = ZERO
    inflation_percent: Decimal = ZERO
    annual_fee_percent: Decimal = ZERO
    compounding_frequency: Frequency = Frequency.MONTHLY


@dataclass(frozen=True)
class GoalInput:
    target: Decimal
    currency: str
    target_date: date
    target_in_todays_money: bool
    assumptions: Assumptions


@dataclass(frozen=True)
class ScenarioOutcome:
    kind: str
    annual_return_percent: Decimal
    nominal: Decimal  # projected value on the target date
    real: Decimal  # the same in today's money
    reaches_target: bool


@dataclass(frozen=True)
class Progress:
    status: Status
    reached: bool  # the current value already meets the target
    overdue: bool  # the target date has passed without reaching it
    progress_percent: Decimal  # current value / target, 0 to 100, 2 decimals
    current_value: Decimal
    gap: Decimal  # target - current value, at least 0
    months_left: int
    scenarios: tuple[ScenarioOutcome, ...]
    required_contribution: Decimal | None  # per period in the first year, base scenario
    estimated_completion: date | None  # base scenario with the current contribution


def months_between(start: date, end: date) -> int:
    """Whole months from `start` to `end` (negative when `end` is earlier)."""
    months = (end.year - start.year) * 12 + end.month - start.month
    if months > 0 and end.day < start.day:
        months -= 1
    elif months < 0 and end.day > start.day:
        months += 1
    return months


def add_months(day: date, months: int) -> date:
    """`months` later, on the same day of the month or the month's last day."""
    total = day.month - 1 + months
    year, month = day.year + total // 12, total % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def progress(goal: GoalInput, current: Decimal, today: date) -> Progress:
    """Where the goal stands today and where its assumptions lead. `current` is the value of
    the funding portfolios in the goal's currency (a negative value counts as 0)."""
    places = minor_units(goal.currency)
    start = max(current, ZERO)
    months = months_between(today, goal.target_date)
    reached = current >= goal.target
    with localcontext() as ctx:
        ctx.prec = PRECISION
        share = min(start / goal.target * HUNDRED, HUNDRED)

    outcomes = []
    for kind, rate in goal.assumptions.returns.items():
        inp = _input(goal, start, rate)
        nominal, real = value_after(inp, months) if months > 0 else (start, start)
        measured = real if goal.target_in_todays_money else nominal
        outcomes.append(
            ScenarioOutcome(
                kind,
                rate,
                round_half_up(nominal, places),
                round_half_up(real, places),
                measured >= goal.target,
            )
        )
    base = next(o for o in outcomes if o.kind == "base")
    base_input = _input(goal, start, goal.assumptions.returns["base"])

    required = None
    if not reached and months > 0:
        exact = required_contribution_by(
            base_input, goal.target, months, real=goal.target_in_todays_money
        )
        required = None if exact is None else round_half_up(exact, places)
    completion = months_to_reach(
        base_input, goal.target, real=goal.target_in_todays_money, limit=SEARCH_MONTHS
    )
    return Progress(
        # With no month left the projection is the current value, so this is "reached" then.
        status="on_track" if reached or base.reaches_target else "behind",
        reached=reached,
        overdue=months < 0 and not reached,
        progress_percent=round_half_up(share, 2),
        current_value=round_half_up(current, places),
        gap=round_half_up(max(goal.target - current, ZERO), places),
        months_left=months,
        scenarios=tuple(outcomes),
        required_contribution=required,
        estimated_completion=None if completion is None else add_months(today, completion),
    )


def _input(goal: GoalInput, start: Decimal, rate: Decimal) -> ForecastInput:
    a = goal.assumptions
    return ForecastInput(
        currency=goal.currency,
        initial=start,
        contribution=a.contribution,
        annual_return_percent=rate,
        years=1,  # unused: goals use month horizons
        contribution_growth_percent=a.contribution_growth_percent,
        inflation_percent=a.inflation_percent,
        annual_fee_percent=a.annual_fee_percent,
        compounding=a.compounding_frequency,
        contribution_frequency=a.contribution_frequency,
    )
