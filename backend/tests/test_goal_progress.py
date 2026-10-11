"""Goal progress (P06-T06): hand-computed cases and properties. Methods: docs/design/goals.md."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.forecasting.engine import Frequency
from app.modules.goals.progress import (
    Assumptions,
    GoalInput,
    add_months,
    months_between,
    progress,
)

D = Decimal
TODAY = date(2026, 10, 11)
FLAT = Assumptions(contribution=D(500), returns={"base": D(0)})
GOAL = GoalInput(D(12000), "USD", date(2027, 10, 11), False, FLAT)


@pytest.mark.parametrize(
    ("start", "end", "months"),
    [
        (date(2026, 10, 11), date(2027, 10, 11), 12),
        (date(2026, 10, 11), date(2027, 10, 10), 11),
        (date(2026, 1, 31), date(2026, 2, 28), 0),
        (date(2026, 1, 31), date(2026, 3, 1), 1),
        (date(2026, 10, 11), date(2026, 10, 30), 0),
        (date(2026, 10, 11), date(2026, 9, 11), -1),
        (date(2026, 10, 11), date(2026, 9, 12), 0),
        (date(2026, 10, 11), date(2025, 10, 1), -12),
    ],
)
def test_months_between(start: date, end: date, months: int) -> None:
    assert months_between(start, end) == months


def test_add_months_keeps_the_day_or_the_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 10, 11), 15) == date(2028, 1, 11)
    assert add_months(date(2026, 10, 11), 0) == date(2026, 10, 11)


def test_on_track() -> None:
    p = progress(GOAL, D(6000), TODAY)
    # 6000 + 12 x 500 = 12000 on the date.
    assert (p.status, p.reached, p.overdue) == ("on_track", False, False)
    assert (p.progress_percent, p.current_value, p.gap) == (D("50.00"), D("6000.00"), D("6000.00"))
    assert p.months_left == 12
    assert [(s.kind, s.nominal, s.reaches_target) for s in p.scenarios] == [
        ("base", D("12000.00"), True)
    ]
    assert p.required_contribution == D("500.00")
    assert p.estimated_completion == date(2027, 10, 11)


def test_behind() -> None:
    goal = replace(GOAL, assumptions=replace(FLAT, contribution=D(400)))
    p = progress(goal, D(6000), TODAY)
    assert p.status == "behind"
    assert p.scenarios[0].nominal == D("10800.00")
    assert p.required_contribution == D("500.00")
    assert p.estimated_completion == date(2028, 1, 11)  # 15 months: 6000 + 15 x 400


def test_reached() -> None:
    p = progress(GOAL, D(13000), TODAY)
    assert (p.status, p.reached, p.progress_percent, p.gap) == ("on_track", True, D("100.00"), D(0))
    assert p.required_contribution is None
    assert p.estimated_completion == TODAY


def test_overdue() -> None:
    goal = replace(GOAL, target_date=date(2026, 8, 1))
    p = progress(goal, D(6000), TODAY)
    assert (p.status, p.overdue, p.months_left) == ("behind", True, -2)
    assert p.scenarios[0].nominal == D("6000.00")  # no time left to grow
    assert p.required_contribution is None
    assert p.estimated_completion == date(2027, 10, 11)  # still reachable with 500 a month


def test_reached_after_the_date_is_not_overdue() -> None:
    p = progress(replace(GOAL, target_date=date(2026, 8, 1)), D(12000), TODAY)
    assert (p.status, p.reached, p.overdue) == ("on_track", True, False)


def test_under_a_month_left() -> None:
    p = progress(replace(GOAL, target_date=date(2026, 10, 30)), D(6000), TODAY)
    assert (p.months_left, p.status, p.required_contribution) == (0, "behind", None)


def test_a_target_in_todays_money_is_measured_in_real_terms() -> None:
    # 12000 nominal after a year at 20% inflation is worth 10000 today.
    inflating = replace(FLAT, inflation_percent=D(20))
    real = replace(GOAL, target=D(10000), target_in_todays_money=True, assumptions=inflating)
    p = progress(real, D(6000), TODAY)
    assert p.scenarios[0].nominal == D("12000.00") and p.scenarios[0].real == D("10000.00")
    assert p.status == "on_track" and p.scenarios[0].reaches_target
    # Needed: 12000 nominal on the date, so (12000 - 6000) / 12 a month (not 10000's 333.33).
    assert progress(replace(real, assumptions=replace(inflating, contribution=D(0))), D(6000),
                    TODAY).required_contribution == D("500.00")  # fmt: skip
    nominal = replace(real, target_in_todays_money=False, target=D(10001))
    assert progress(nominal, D(6000), TODAY).status == "on_track"  # 12000 >= 10001
    stricter = replace(real, target=D("10000.01"))
    assert progress(stricter, D(6000), TODAY).status == "behind"


def test_scenarios_and_their_order() -> None:
    a = Assumptions(D(0), {"conservative": D(-10), "base": D(0), "growth": D(12)},
                    compounding_frequency=Frequency.YEARLY)  # fmt: skip
    p = progress(replace(GOAL, target=D(6600), assumptions=a), D(6000), TODAY)
    assert [(s.kind, s.nominal, s.reaches_target) for s in p.scenarios] == [
        ("conservative", D("5400.00"), False),
        ("base", D("6000.00"), False),
        ("growth", D("6720.00"), True),
    ]
    assert p.status == "behind"  # measured against base only


def test_a_negative_value_counts_as_nothing() -> None:
    p = progress(GOAL, D(-500), TODAY)
    assert (p.progress_percent, p.current_value, p.gap) == (D("0.00"), D("-500.00"), D("12500.00"))
    assert p.scenarios[0].nominal == D("6000.00")  # 0 + 12 x 500
    assert p.required_contribution == D("1000.00")


def test_no_contribution_date_before_the_target() -> None:
    yearly = replace(FLAT, contribution_frequency=Frequency.YEARLY, contribution=D(6000))
    p = progress(replace(GOAL, target_date=date(2027, 3, 11), assumptions=yearly), D(6000), TODAY)
    assert p.months_left == 5 and p.required_contribution is None
    assert p.estimated_completion == date(2027, 10, 11)


def test_never_reached() -> None:
    p = progress(replace(GOAL, assumptions=replace(FLAT, contribution=D(0))), D(6000), TODAY)
    assert p.status == "behind" and p.estimated_completion is None


def test_currency_minor_units() -> None:
    goal = GoalInput(D(1000000), "JPY", date(2027, 10, 11), False,
                     Assumptions(D(10000), {"base": D("3.33")}))  # fmt: skip
    p = progress(goal, D("123456.7"), TODAY)
    assert p.current_value == D(123457) and p.required_contribution is not None
    assert p.required_contribution == p.required_contribution.to_integral_value()


@settings(max_examples=80, deadline=None)
@given(
    st.decimals(min_value=1, max_value=1_000_000, places=2),
    st.decimals(min_value=0, max_value=1_000_000, places=2),
    st.decimals(min_value=0, max_value=10_000, places=2),
    st.decimals(min_value=-20, max_value=50, places=2),
    st.integers(1, 360),
)
def test_status_and_required_contribution_agree(
    target: Decimal, current: Decimal, contribution: Decimal, rate: Decimal, months: int
) -> None:
    goal = GoalInput(target, "USD", add_months(TODAY, months), False,
                     Assumptions(contribution, {"base": rate}))  # fmt: skip
    p = progress(goal, current, TODAY)
    if p.reached:
        assert p.status == "on_track" and p.required_contribution is None
        return
    base = p.scenarios[0]
    # Measured on the unrounded projection (a rounded 1.00 can still be short of 1.00).
    assert (p.status == "on_track") == base.reaches_target
    assert p.required_contribution is not None
    # Paying the required amount (rounded up) reaches the target.
    paying = progress(replace(goal, assumptions=replace(goal.assumptions,
                                                        contribution=p.required_contribution)),
                      current, TODAY)  # fmt: skip
    # Rounded up, it is never short: only the projection's own rounding (half a cent) remains.
    assert paying.scenarios[0].nominal >= target - D("0.005")
    assert D(0) <= p.progress_percent <= 100
