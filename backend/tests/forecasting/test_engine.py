"""Compound forecast engine (P06-T01): golden vectors, closed-form agreement and properties.
Formulas: docs/design/forecast-engine.md."""

import ast
import json
from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.forecasting.engine import (
    ForecastInput,
    Frequency,
    InvalidForecast,
    project,
    scenarios,
)

VECTORS = json.loads(
    (Path(__file__).parents[1] / "golden" / "forecast_vectors.json").read_text("utf-8")
)


def from_vector(spec: dict[str, Any]) -> ForecastInput:
    return ForecastInput(
        currency=spec["currency"],
        initial=Decimal(spec["initial"]),
        contribution=Decimal(spec["contribution"]),
        annual_return_percent=Decimal(spec["annual_return_percent"]),
        years=spec["years"],
        contribution_growth_percent=Decimal(spec.get("contribution_growth_percent", "0")),
        inflation_percent=Decimal(spec.get("inflation_percent", "0")),
        annual_fee_percent=Decimal(spec.get("annual_fee_percent", "0")),
        compounding=Frequency(spec["compounding"]),
        contribution_frequency=Frequency(spec["contribution_frequency"]),
    )


# ------------------------------------------------------------------------------ golden vectors


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_golden_vectors(case: dict[str, Any]) -> None:
    p = project(from_vector(case["input"]))
    got = {
        "final_nominal": str(p.final_nominal),
        "final_real": str(p.final_real),
        "total_contributions": str(p.total_contributions),
        "total_growth": str(p.total_growth),
    }
    assert got == case["expected"]


def test_published_textbook_values() -> None:
    """Independent of the vector file: two values from published compound-interest tables."""
    lump = ForecastInput("USD", Decimal(10000), Decimal(0), Decimal(5), 10)
    assert project(replace(lump, compounding=Frequency.YEARLY)).final_nominal == Decimal("16288.95")
    annuity = ForecastInput("USD", Decimal(0), Decimal(100), Decimal(6), 10)
    assert project(annuity).final_nominal == Decimal("16387.93")


def test_the_yearly_series() -> None:
    inp = ForecastInput(
        "USD", Decimal(10000), Decimal(0), Decimal(5), 3, inflation_percent=Decimal(2)
    )
    p = project(replace(inp, compounding=Frequency.YEARLY))
    assert [(y.year, y.nominal, y.real, y.contributions, y.growth) for y in p.series] == [
        (0, Decimal("10000.00"), Decimal("10000.00"), Decimal("10000.00"), Decimal("0.00")),
        (1, Decimal("10500.00"), Decimal("10294.12"), Decimal("10000.00"), Decimal("500.00")),
        (2, Decimal("11025.00"), Decimal("10596.89"), Decimal("10000.00"), Decimal("1025.00")),
        (3, Decimal("11576.25"), Decimal("10908.56"), Decimal("10000.00"), Decimal("1576.25")),
    ]
    last = p.series[-1]
    assert (p.final_nominal, p.final_real, p.total_contributions, p.total_growth) == (
        last.nominal,
        last.real,
        last.contributions,
        last.growth,
    )
    assert p.annual_return_percent == Decimal(5) and p.currency == "USD"


def test_contributions_are_paid_at_the_end_of_each_period() -> None:
    """One year, no growth on the last payment: 12 monthly payments of 100 at 12% (1% a month)
    are worth 100 x (1.01^12 - 1) / 0.01 = 1268.25; quarterly 300 at the same compounding is
    worth 300 x ((1.01^3)^4 - 1) / (1.01^3 - 1) = 1255.65; yearly 1200 is worth 1200."""
    inp = ForecastInput("USD", Decimal(0), Decimal(100), Decimal(12), 1)
    assert project(inp).final_nominal == Decimal("1268.25")
    quarterly = replace(inp, contribution=Decimal(300), contribution_frequency=Frequency.QUARTERLY)
    assert project(quarterly).final_nominal == Decimal("1255.65")
    yearly = replace(inp, contribution=Decimal(1200), contribution_frequency=Frequency.YEARLY)
    assert project(yearly).final_nominal == Decimal("1200.00")


def test_escalation_steps_up_once_a_year() -> None:
    inp = ForecastInput(
        "USD", Decimal(0), Decimal(100), Decimal(0), 3, contribution_growth_percent=Decimal(10)
    )
    p = project(inp)
    # 1200 in year 1, 1320 in year 2, 1452 in year 3.
    assert [y.contributions for y in p.series] == [
        Decimal("0.00"),
        Decimal("1200.00"),
        Decimal("2520.00"),
        Decimal("3972.00"),
    ]


def test_compounding_frequency_matters() -> None:
    """The return is nominal: 12% compounded monthly beats 12% compounded yearly."""
    inp = ForecastInput("USD", Decimal(1000), Decimal(0), Decimal(12), 1)
    assert project(inp).final_nominal == Decimal("1126.83")
    assert project(replace(inp, compounding=Frequency.QUARTERLY)).final_nominal == Decimal(
        "1125.51"
    )
    assert project(replace(inp, compounding=Frequency.YEARLY)).final_nominal == Decimal("1120.00")


def test_scenarios_change_only_the_return() -> None:
    inp = ForecastInput(
        "USD", Decimal(10000), Decimal(500), Decimal(8), 20, Decimal(0), Decimal("2.5"),
        Decimal("0.5"),
    )  # fmt: skip
    result = scenarios(inp, {"conservative": Decimal(5), "base": Decimal(8), "growth": Decimal(12)})
    assert list(result) == ["conservative", "base", "growth"]
    assert result["base"] == project(inp)
    assert result["growth"] == project(replace(inp, annual_return_percent=Decimal(12)))
    finals = [result[k].final_nominal for k in ("conservative", "base", "growth")]
    assert finals == sorted(finals) and len(set(finals)) == 3
    assert {p.total_contributions for p in result.values()} == {Decimal("130000.00")}


def test_the_largest_published_inputs_stay_exact() -> None:
    """60 years at the top of every limit: no overflow, exponent or float."""
    inp = ForecastInput("USD", Decimal(1000000000), Decimal(10000000), Decimal(50), 60, Decimal(20))
    p = project(inp)
    assert p.final_nominal.as_tuple().exponent == -2
    assert p.total_contributions + p.total_growth == p.final_nominal
    assert "E" not in str(p.final_nominal)


@pytest.mark.parametrize(
    "change",
    [
        {"years": 0},
        {"years": 101},
        {"initial": Decimal(-1)},
        {"contribution": Decimal("-0.01")},
        {"annual_return_percent": Decimal(-1200), "compounding": Frequency.MONTHLY},
        {"annual_return_percent": Decimal(-100), "compounding": Frequency.YEARLY},
        {"annual_return_percent": Decimal(-95), "annual_fee_percent": Decimal(5),
         "compounding": Frequency.YEARLY},
        {"inflation_percent": Decimal(-100)},
        {"contribution_growth_percent": Decimal(-100)},
    ],
)  # fmt: skip
def test_inputs_outside_the_domain_are_refused(change: dict[str, Any]) -> None:
    inp = ForecastInput("USD", Decimal(1000), Decimal(100), Decimal(5), 10)
    with pytest.raises(InvalidForecast):
        project(replace(inp, **change))


def test_the_edges_of_the_domain_are_accepted() -> None:
    inp = ForecastInput("USD", Decimal(0), Decimal(0), Decimal(-20), 1)
    assert project(inp).final_nominal == Decimal("0.00")
    assert project(replace(inp, years=100, initial=Decimal(1))).final_nominal >= 0
    nearly = replace(inp, initial=Decimal(1), annual_return_percent=Decimal("-99.99"))
    assert project(replace(nearly, compounding=Frequency.YEARLY)).final_nominal == Decimal("0.00")


# ----------------------------------------------------------------------------------- properties

FREQ = st.sampled_from(list(Frequency))
MONEY = st.decimals(min_value=0, max_value=1_000_000, places=2)
RATE = st.decimals(min_value=-20, max_value=50, places=2)


@st.composite
def inputs(draw: st.DrawFn) -> ForecastInput:
    return ForecastInput(
        currency=draw(st.sampled_from(["USD", "JPY", "KWD"])),
        initial=draw(MONEY),
        contribution=draw(st.decimals(min_value=0, max_value=100_000, places=2)),
        annual_return_percent=draw(RATE),
        years=draw(st.integers(min_value=1, max_value=60)),
        contribution_growth_percent=draw(st.decimals(min_value=0, max_value=20, places=2)),
        inflation_percent=draw(st.decimals(min_value=0, max_value=30, places=2)),
        annual_fee_percent=draw(st.decimals(min_value=0, max_value=5, places=2)),
        compounding=draw(FREQ),
        contribution_frequency=draw(FREQ),
    )


@settings(max_examples=150, deadline=None)
@given(inputs())
def test_contributions_plus_growth_equal_the_value_at_every_year(inp: ForecastInput) -> None:
    p = project(inp)
    assert len(p.series) == inp.years + 1
    assert [y.year for y in p.series] == list(range(inp.years + 1))
    for y in p.series:
        assert y.contributions + y.growth == y.nominal
    assert p.series[0].nominal == p.series[0].contributions
    assert p.series[0].growth == 0


@settings(max_examples=100, deadline=None)
@given(inputs())
def test_total_contributions_are_what_was_paid_in(inp: ForecastInput) -> None:
    k = inp.contribution_frequency.per_year
    g = 1 + inp.contribution_growth_percent / 100
    with localcontext() as ctx:
        ctx.prec = 50
        paid = inp.initial + sum(inp.contribution * g**y * k for y in range(inp.years))
    places = {"USD": 2, "JPY": 0, "KWD": 3}[inp.currency]
    expected = paid.quantize(Decimal(1).scaleb(-places), rounding="ROUND_HALF_UP")
    assert project(inp).total_contributions == expected


@settings(max_examples=100, deadline=None)
@given(inputs())
def test_no_return_and_no_fee_means_no_growth(inp: ForecastInput) -> None:
    flat = replace(inp, annual_return_percent=Decimal(0), annual_fee_percent=Decimal(0))
    assert all(y.growth == 0 for y in project(flat).series)


@settings(max_examples=100, deadline=None)
@given(inputs(), st.decimals(min_value=0, max_value=10, places=2))
def test_more_return_is_never_worth_less(inp: ForecastInput, extra: Decimal) -> None:
    higher = replace(inp, annual_return_percent=inp.annual_return_percent + extra)
    assert project(higher).final_nominal >= project(inp).final_nominal


@settings(max_examples=100, deadline=None)
@given(inputs(), st.decimals(min_value=0, max_value=5, places=2))
def test_a_higher_fee_is_never_worth_more(inp: ForecastInput, extra: Decimal) -> None:
    costlier = replace(inp, annual_fee_percent=inp.annual_fee_percent + extra)
    assert project(costlier).final_nominal <= project(inp).final_nominal


@settings(max_examples=100, deadline=None)
@given(inputs(), MONEY, st.decimals(min_value=0, max_value=1000, places=2))
def test_paying_in_more_is_never_worth_less(
    inp: ForecastInput, more_initial: Decimal, more_contribution: Decimal
) -> None:
    richer = replace(
        inp, initial=inp.initial + more_initial, contribution=inp.contribution + more_contribution
    )
    assert project(richer).final_nominal >= project(inp).final_nominal


@settings(max_examples=100, deadline=None)
@given(inputs())
def test_with_a_non_negative_net_return_the_value_never_falls(inp: ForecastInput) -> None:
    if inp.annual_return_percent < inp.annual_fee_percent:
        inp = replace(inp, annual_return_percent=inp.annual_fee_percent)
    nominal = [y.nominal for y in project(inp).series]
    assert nominal == sorted(nominal)
    assert project(replace(inp, years=min(inp.years + 1, 60))).final_nominal >= nominal[-1]


@settings(max_examples=100, deadline=None)
@given(inputs(), st.decimals(min_value=0, max_value=10, places=2))
def test_inflation_lowers_only_the_real_value(inp: ForecastInput, extra: Decimal) -> None:
    base, hotter = (
        project(inp),
        project(replace(inp, inflation_percent=inp.inflation_percent + extra)),
    )
    assert hotter.final_nominal == base.final_nominal
    assert hotter.final_real <= base.final_real <= base.final_nominal
    for y in base.series:
        assert y.real <= y.nominal


@settings(max_examples=150, deadline=None)
@given(inputs())
def test_month_by_month_agrees_with_the_closed_form(inp: ForecastInput) -> None:
    """Independent check: lump sum plus a growing annuity per year at the per-period rate
    equivalent to the compounding (docs/design/forecast-engine.md, closed forms)."""
    m, k = inp.compounding.per_year, inp.contribution_frequency.per_year
    with localcontext() as ctx:
        ctx.prec = 60
        i = (inp.annual_return_percent - inp.annual_fee_percent) / 100 / m
        year = (1 + i) ** m
        per = (1 + i) ** (Decimal(m) / k) - 1
        s = Decimal(k) if per == 0 else ((1 + per) ** k - 1) / per
        g = 1 + inp.contribution_growth_percent / 100
        n = inp.years
        fv = inp.initial * year**n + sum(
            inp.contribution * g ** (y - 1) * s * year ** (n - y) for y in range(1, n + 1)
        )
    unit = Decimal(1).scaleb(-{"USD": 2, "JPY": 0, "KWD": 3}[inp.currency])
    # Equal after rounding, except when the exact value sits on a rounding boundary.
    assert abs(project(inp).final_nominal - fv) <= unit / 2 + Decimal("1e-20")


@settings(max_examples=50, deadline=None)
@given(inputs())
def test_the_engine_is_deterministic(inp: ForecastInput) -> None:
    assert project(inp) == project(inp)


def test_no_float_or_llm_in_the_engine() -> None:
    """The engine's code (not its prose) uses no float, math or numpy, and no LLM client."""
    tree = ast.parse(
        (Path(__file__).parents[2] / "app" / "modules" / "forecasting" / "engine.py").read_text(
            "utf-8"
        )
    )
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in (
            node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")]
        )
    }
    assert imported <= {"collections", "dataclasses", "decimal", "enum", "app"}, imported
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "float" not in names
    floats = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)]
    assert not [v for v in floats if isinstance(v, float)]


@pytest.mark.parametrize(
    ("currency", "initial", "rate", "expected"),
    [
        ("USD", "0.10", "5", "0.11"),  # 0.105: a tie, rounded away from zero
        ("USD", "0.30", "-5", "0.29"),  # 0.285
        ("JPY", "10", "5", "11"),  # 10.5
        ("KWD", "0.010", "5", "0.011"),  # 0.0105
    ],
)
def test_results_round_half_up_to_the_currency(
    currency: str, initial: str, rate: str, expected: str
) -> None:
    inp = ForecastInput(
        currency, Decimal(initial), Decimal(0), Decimal(rate), 1, compounding=Frequency.YEARLY
    )
    p = project(inp)
    assert str(p.final_nominal) == expected
    assert p.total_growth == Decimal(expected) - Decimal(initial)
