"""The forecast input limits are the same in the API and the mobile calculator (P06-T02.3).

Reads mobile/wealthsphere_app/lib/features/calculator/domain/forecast_input_limits.dart, so a
limit changed on one side only fails the build."""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.forecasting import limits
from app.modules.forecasting.limits import Limit
from app.modules.forecasting.schemas import ScenarioForecastIn

ROOT = Path(__file__).resolve().parents[3]
DART = ROOT / "mobile/wealthsphere_app/lib/features/calculator/domain/forecast_input_limits.dart"
FIXTURE = ROOT / "mobile/wealthsphere_app/assets/demo/forecast.json"

# Dart name -> backend limit.
SHARED = {
    "initialInvestment": limits.INITIAL_INVESTMENT,
    "monthlyContribution": limits.CONTRIBUTION,
    "returnRate": limits.RETURN_RATE,
    "years": limits.YEARS,
    "contributionGrowth": limits.CONTRIBUTION_GROWTH,
    "inflation": limits.INFLATION,
    "annualFee": limits.ANNUAL_FEE,
}


def _dart_decimal(expr: str) -> Decimal:
    expr = expr.strip()
    if expr == "Decimal.zero":
        return Decimal(0)
    if expr == "Decimal.one":
        return Decimal(1)
    if m := re.fullmatch(r"Decimal\.fromInt\((-?\d+)\)", expr):
        return Decimal(m.group(1))
    if m := re.fullmatch(r"Decimal\.parse\('(-?[\d.]+)'\)", expr):
        return Decimal(m.group(1))
    raise AssertionError(f"unrecognised Dart decimal: {expr}")


def _dart_limits() -> dict[str, Limit]:
    source = DART.read_text("utf-8")
    found = {}
    pattern = r"static final NumericLimit (\w+) = NumericLimit\((.*?)\);"
    for name, args in re.findall(pattern, source, re.S):
        fields = dict(re.findall(r"(\w+):\s*([^,]+(?:\([^)]*\))?)", args))
        found[name] = Limit(
            _dart_decimal(fields["min"]),
            _dart_decimal(fields["max"]),
            int(fields.get("fractionDigits", "2")),  # the Dart default
        )
    return found


def test_every_mobile_limit_is_shared() -> None:
    assert set(_dart_limits()) == set(SHARED)


@pytest.mark.parametrize("name", list(SHARED))
def test_the_limits_are_identical(name: str) -> None:
    assert _dart_limits()[name] == SHARED[name]


def test_both_sides_order_the_scenarios() -> None:
    source = DART.read_text("utf-8")
    assert "conservativeAboveBase" in source and "growthBelowBase" in source
    # The backend rule is exercised in test_forecast_api (conservative above base, growth below).


def test_the_calculator_defaults_are_a_valid_request() -> None:
    """The demo fixture's request is the calculator's opening inputs (a mobile test keeps them
    identical); with the API's field name for the contribution, the API accepts it."""
    request = json.loads(FIXTURE.read_text("utf-8"))["request"]
    request["contribution"] = request.pop("monthly_contribution")
    ScenarioForecastIn.model_validate(request)


def test_the_parser_reads_what_it_should() -> None:
    assert _dart_decimal("Decimal.fromInt(-20)") == Decimal(-20)
    assert _dart_decimal("Decimal.parse('0.5')") == Decimal("0.5")
    with pytest.raises(AssertionError):
        _dart_decimal("Decimal.ten")
    years = _dart_limits()["years"]
    assert years.decimals == 0 and years.maximum == 60
