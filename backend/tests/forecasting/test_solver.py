"""Required-contribution solver (P06-T01.3): closed form, rounding and properties."""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.modules.forecasting.engine import (
    ForecastInput,
    Frequency,
    InvalidForecast,
    project,
    required_contribution,
)
from tests.forecasting.test_engine import inputs

DEFAULTS = ForecastInput(
    "USD", Decimal(10000), Decimal(500), Decimal(8), 20, Decimal(0), Decimal("2.5"),
    Decimal("0.5"),
)  # fmt: skip


def test_matches_the_annuity_closed_form() -> None:
    """Monthly at 8% less a 0.5% fee for 20 years: C = (T - PV (1+i)^N) / (((1+i)^N - 1) / i)."""
    with localcontext() as ctx:
        ctx.prec = 60
        i = Decimal("7.5") / 100 / 12
        growth = (1 + i) ** 240
        expected = (Decimal(1000000) - 10000 * growth) / ((growth - 1) / i)
    result = required_contribution(DEFAULTS, Decimal(1000000))
    assert abs(result.exact - expected) < Decimal("1e-40")
    assert result.amount == expected.quantize(Decimal("0.01"), rounding="ROUND_CEILING")
    assert result.amount == Decimal("1725.38")  # 1725.3726 rounded up (ADR-0006 exception 1)
    assert not result.reached_without_contributions
    # Paying the rounded-up amount always reaches the target (half-up gave 999998.55).
    assert result.projection.final_nominal == Decimal("1000004.09")


def test_its_own_contribution_is_ignored() -> None:
    target = Decimal(250000)
    assert required_contribution(DEFAULTS, target) == required_contribution(
        replace(DEFAULTS, contribution=Decimal(99999)), target
    )


def test_a_target_in_todays_money_is_inflated_to_the_horizon() -> None:
    real = required_contribution(DEFAULTS, Decimal(500000), real=True)
    with localcontext() as ctx:
        ctx.prec = 60
        nominal_target = Decimal(500000) * Decimal("1.025") ** 20
    nominal = required_contribution(DEFAULTS, nominal_target)
    assert real.exact == nominal.exact
    assert abs(real.projection.final_real - Decimal(500000)) <= Decimal("2")


def test_a_target_already_reached_needs_nothing() -> None:
    result = required_contribution(DEFAULTS, Decimal(40000))
    assert result.reached_without_contributions
    assert result.amount == 0 and result.exact == 0
    assert result.projection.final_nominal >= Decimal(40000)
    initial_only = project(replace(DEFAULTS, contribution=Decimal(0))).final_nominal
    exactly = required_contribution(DEFAULTS, initial_only - Decimal("0.01"))
    assert exactly.reached_without_contributions


def test_a_zero_rate_divides_evenly() -> None:
    flat = ForecastInput("USD", Decimal(1000), Decimal(0), Decimal(0), 10)
    result = required_contribution(flat, Decimal(13000))
    assert result.amount == Decimal("100.00")  # 120 months x 100 + 1000
    assert result.projection.final_nominal == Decimal("13000.00")


def test_escalation_lowers_the_first_year_amount() -> None:
    level = required_contribution(DEFAULTS, Decimal(1000000))
    rising = required_contribution(
        replace(DEFAULTS, contribution_growth_percent=Decimal(3)), Decimal(1000000)
    )
    assert rising.amount < level.amount
    yearly = required_contribution(
        replace(DEFAULTS, contribution_frequency=Frequency.YEARLY), Decimal(1000000)
    )
    assert yearly.amount > 12 * level.amount  # paid later, so it earns less


def test_a_negative_target_is_refused() -> None:
    with pytest.raises(InvalidForecast):
        required_contribution(DEFAULTS, Decimal(-1))


def test_invalid_inputs_are_refused_by_the_solver_too() -> None:
    with pytest.raises(InvalidForecast):
        required_contribution(replace(DEFAULTS, years=0), Decimal(1000))


@settings(max_examples=120, deadline=None)
@given(inputs(), st.decimals(min_value=0, max_value=10_000_000, places=2), st.booleans())
def test_the_exact_amount_reaches_the_target(
    inp: ForecastInput, target: Decimal, real: bool
) -> None:
    result = required_contribution(inp, target, real=real)
    unit = Decimal(1).scaleb(-{"USD": 2, "JPY": 0, "KWD": 3}[inp.currency])
    reached = result.projection.final_real if real else result.projection.final_nominal
    if result.reached_without_contributions:
        assert result.amount == 0
        assert reached >= target - unit
        return
    assert result.exact > 0
    # Rounded up: never short of the target (beyond the rounding of the reported value), and
    # over it by at most one unit per unit of contribution value.
    with localcontext() as ctx:
        ctx.prec = 60
        zero = replace(inp, contribution=Decimal(0))
        one = replace(inp, contribution=Decimal(1))
        per_unit = _exact_final(one) - _exact_final(zero)
        if real:
            per_unit /= (1 + inp.inflation_percent / 100) ** inp.years
    assert reached >= target - unit / 2
    assert reached - target <= unit * per_unit + unit


@settings(max_examples=80, deadline=None)
@given(inputs(), st.decimals(min_value=1, max_value=1_000_000, places=2))
def test_a_higher_target_never_needs_less(inp: ForecastInput, extra: Decimal) -> None:
    target = project(inp).final_nominal
    assume(target > 0)
    assert (
        required_contribution(inp, target + extra).exact >= required_contribution(inp, target).exact
    )


def _exact_final(inp: ForecastInput) -> Decimal:
    """Closed-form final value (as in test_engine), unrounded."""
    m, k = inp.compounding.per_year, inp.contribution_frequency.per_year
    i = (inp.annual_return_percent - inp.annual_fee_percent) / 100 / m
    year = (1 + i) ** m
    per = (1 + i) ** (Decimal(m) / k) - 1
    s = Decimal(k) if per == 0 else ((1 + per) ** k - 1) / per
    g = 1 + inp.contribution_growth_percent / 100
    n = inp.years
    return inp.initial * year**n + sum(
        inp.contribution * g ** (y - 1) * s * year ** (n - y) for y in range(1, n + 1)
    )
