"""Month-based horizons of the forecast engine (P06-T06, for goals that end on a date)."""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest
from hypothesis import given, settings

from app.core.money import round_half_up
from app.modules.forecasting.engine import (
    ForecastInput,
    Frequency,
    InvalidForecast,
    months_to_reach,
    project,
    required_contribution,
    required_contribution_by,
    value_after,
)
from tests.forecasting.test_engine import inputs

D = Decimal
FLAT = ForecastInput("USD", D(0), D(100), D(0), 1)


def test_whole_years_agree_with_the_yearly_projection() -> None:
    inp = ForecastInput("USD", D(10000), D(500), D(8), 20, D(3), D("2.5"), D("0.5"))
    nominal, real = value_after(inp, 240)
    p = project(inp)
    assert round_half_up(nominal, 2) == p.final_nominal
    assert round_half_up(real, 2) == p.final_real


def test_part_years() -> None:
    assert value_after(FLAT, 0) == (D(0), D(0))
    assert value_after(FLAT, 7)[0] == D(700)
    # 1% a month on 1000 for 18 months; quarterly contributions of 300 at months 3..18.
    inp = ForecastInput(
        "USD", D(1000), D(300), D(12), 1, contribution_frequency=Frequency.QUARTERLY
    )
    with localcontext() as ctx:
        ctx.prec = 50
        expected = D(1000) * D("1.01") ** 18 + sum(
            D(300) * D("1.01") ** (18 - k) for k in (3, 6, 9, 12, 15, 18)
        )
    assert abs(value_after(inp, 18)[0] - expected) < D("1e-40")


def test_escalation_steps_at_each_full_year() -> None:
    inp = replace(FLAT, contribution_growth_percent=D(10))
    assert value_after(inp, 12)[0] == D(1200)
    assert value_after(inp, 13)[0] == D(1310)  # month 13 pays 110
    assert value_after(inp, 25)[0] == D("2641.0")  # 1200 + 1320 + 121


def test_real_values_deflate_by_part_years() -> None:
    inp = ForecastInput("USD", D(1000), D(0), D(0), 1, inflation_percent=D(21))
    _, real = value_after(inp, 6)
    assert abs(real - D(1000) / D("1.1")) < D("1e-25")  # 1.21^(1/2) = 1.1
    _, real = value_after(inp, 18)
    assert abs(real - D(1000) / (D("1.21") * D("1.1"))) < D("1e-25")


def test_months_to_reach() -> None:
    assert months_to_reach(FLAT, D(1000)) == 10
    assert months_to_reach(FLAT, D(1000.01)) == 11
    assert months_to_reach(FLAT, D(0)) == 0
    assert months_to_reach(replace(FLAT, contribution=D(0)), D(1)) is None
    assert months_to_reach(FLAT, D(1000), limit=9) is None
    inflating = replace(FLAT, inflation_percent=D(5))
    assert (
        months_to_reach(inflating, D(1000), real=True) == 11
    )  # 1000 nominal is less in real terms


def test_no_contribution_falls_before_the_date() -> None:
    yearly = replace(FLAT, contribution_frequency=Frequency.YEARLY)
    assert required_contribution_by(yearly, D(1000), 11) is None
    assert required_contribution_by(yearly, D(1000), 12) == D(1000)


def test_required_contribution_by_a_date() -> None:
    assert required_contribution_by(FLAT, D(1000), 10) == D(100)
    assert required_contribution_by(FLAT, D(0), 10) == 0
    assert required_contribution_by(replace(FLAT, initial=D(5000)), D(1000), 3) == 0
    inp = ForecastInput("USD", D(10000), D(0), D("7.5"), 20, D(2), D("2.5"))
    assert (
        required_contribution_by(inp, D(1000000), 240)
        == required_contribution(inp, D(1000000)).exact
    )
    assert (
        required_contribution_by(inp, D(500000), 240, real=True)
        == required_contribution(inp, D(500000), real=True).exact
    )


@pytest.mark.parametrize("months", [-1, 1201])
def test_horizon_limits(months: int) -> None:
    with pytest.raises(InvalidForecast):
        value_after(FLAT, months)
    with pytest.raises(InvalidForecast):
        required_contribution_by(FLAT, D(1), months)


def test_invalid_inputs_are_refused_even_without_steps() -> None:
    bad = replace(FLAT, initial=D(-1))
    with pytest.raises(InvalidForecast):
        value_after(bad, 0)
    with pytest.raises(InvalidForecast):
        months_to_reach(bad, D(-5))
    with pytest.raises(InvalidForecast):
        required_contribution_by(FLAT, D(-1), 12)
    with pytest.raises(InvalidForecast):
        required_contribution_by(FLAT, D(1), 0)


@settings(max_examples=60, deadline=None)
@given(inputs())
def test_months_to_reach_is_the_first_month_at_the_target(inp: ForecastInput) -> None:
    target = inp.initial + D(1000)
    month = months_to_reach(inp, target, limit=360)
    if month is None:
        assert value_after(inp, 360)[0] < target
        return
    assert value_after(inp, month)[0] >= target
    assert month == 0 or value_after(inp, month - 1)[0] < target


@settings(max_examples=60, deadline=None)
@given(inputs())
def test_the_required_amount_reaches_the_target_by_the_date(inp: ForecastInput) -> None:
    months = inp.years * 12 - 5 if inp.years > 1 else 7
    target = inp.initial * 2 + D(5000)
    exact = required_contribution_by(inp, target, months)
    if exact is None:  # no contribution date before the horizon
        assert months < 12 // inp.contribution_frequency.per_year
        return
    nominal, _ = value_after(replace(inp, contribution=exact), months)
    if exact == 0:  # the initial amount alone gets there
        assert nominal >= target
    else:
        assert abs(nominal - target) <= target * D("1e-30") + D("1e-30")
