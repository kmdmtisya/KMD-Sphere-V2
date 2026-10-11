"""Compound forecast engine (P06-T01). Formulas and rounding: docs/design/forecast-engine.md.

Pure functions: no I/O, no LLM, no binary floating point. A forecast illustrates the assumptions
it is given; it is never a prediction or a guaranteed return."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from enum import StrEnum

from app.core.money import minor_units, round_half_up

# Plenty of digits for 720 monthly steps and fractional powers; nothing is rounded inside.
PRECISION = 50
MAX_YEARS = 100  # a sanity bound for the engine; the API publishes the product limit
ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)
MONTHS = 12


class Frequency(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

    @property
    def per_year(self) -> int:
        return {"monthly": 12, "quarterly": 4, "yearly": 1}[self.value]


class InvalidForecast(ValueError):
    """The inputs are outside the engine's domain (the API rejects them earlier)."""


@dataclass(frozen=True)
class ForecastInput:
    """Rates are percentages (8 means 8%). Amounts are in `currency`."""

    currency: str
    initial: Decimal
    contribution: Decimal  # per contribution period, first year
    annual_return_percent: Decimal  # nominal, compounded `compounding` times a year
    years: int
    contribution_growth_percent: Decimal = ZERO  # yearly escalation of the contribution
    inflation_percent: Decimal = ZERO
    annual_fee_percent: Decimal = ZERO
    compounding: Frequency = Frequency.MONTHLY
    contribution_frequency: Frequency = Frequency.MONTHLY


@dataclass(frozen=True)
class YearPoint:
    """Values at the end of `year` (year 0 is the start), rounded to the currency."""

    year: int
    nominal: Decimal
    real: Decimal  # in today's money
    contributions: Decimal  # cumulative, including the initial amount
    growth: Decimal  # nominal - contributions


@dataclass(frozen=True)
class Projection:
    currency: str
    annual_return_percent: Decimal
    final_nominal: Decimal
    final_real: Decimal
    total_contributions: Decimal
    total_growth: Decimal
    series: tuple[YearPoint, ...]


@dataclass(frozen=True)
class RequiredContribution:
    amount: Decimal  # per contribution period in the first year, rounded to the currency
    exact: Decimal  # unrounded, for further calculation
    reached_without_contributions: bool
    projection: Projection  # the forecast with `amount` as the contribution


@dataclass(frozen=True)
class _Year:
    balance: Decimal
    contributed: Decimal


def project(inp: ForecastInput) -> Projection:
    """The forecast for one set of assumptions."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        years = _simulate(inp, inp.contribution)
        deflator = ONE + inp.inflation_percent / HUNDRED
        places = minor_units(inp.currency)
        series = []
        for t, y in enumerate(years):
            nominal = round_half_up(y.balance, places)
            contributed = round_half_up(y.contributed, places)
            series.append(
                YearPoint(
                    year=t,
                    nominal=nominal,
                    real=round_half_up(y.balance / deflator**t, places),
                    contributions=contributed,
                    growth=nominal - contributed,
                )
            )
    last = series[-1]
    return Projection(
        currency=inp.currency,
        annual_return_percent=inp.annual_return_percent,
        final_nominal=last.nominal,
        final_real=last.real,
        total_contributions=last.contributions,
        total_growth=last.growth,
        series=tuple(series),
    )


def scenarios(inp: ForecastInput, returns: Mapping[str, Decimal]) -> dict[str, Projection]:
    """The same assumptions under several annual returns (for example conservative, base and
    growth). The caller supplies every rate; the engine suggests none."""
    return {name: project(replace(inp, annual_return_percent=r)) for name, r in returns.items()}


def required_contribution(
    inp: ForecastInput, target: Decimal, *, real: bool = False
) -> RequiredContribution:
    """The first-year contribution per period that reaches `target` at the horizon, with every
    other input of `inp` fixed (its own contribution is ignored). `real=True` reads the target in
    today's money. Closed form: the final value is linear in the contribution."""
    if target < 0:
        raise InvalidForecast("the target must not be negative")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        nominal_target = (
            target * (ONE + inp.inflation_percent / HUNDRED) ** inp.years if real else target
        )
        without = _simulate(inp, ZERO)[-1].balance
        per_unit = _simulate(inp, ONE)[-1].balance - without
        reached = without >= nominal_target
        exact = ZERO if reached else (nominal_target - without) / per_unit
    amount = round_half_up(exact, minor_units(inp.currency))
    return RequiredContribution(
        amount=amount,
        exact=exact,
        reached_without_contributions=reached,
        projection=project(replace(inp, contribution=amount)),
    )


def _simulate(inp: ForecastInput, contribution: Decimal) -> list[_Year]:
    """Balance and contributions at the end of each year 0..n, unrounded. Steps month by month
    at the monthly factor equivalent to the compounding; contributions are paid at the end of
    each contribution period and step up once a year."""
    _check(inp, contribution)
    m = inp.compounding.per_year
    periodic = ONE + (inp.annual_return_percent - inp.annual_fee_percent) / HUNDRED / m
    monthly = periodic if m == MONTHS else periodic ** (Decimal(m) / MONTHS)
    every = MONTHS // inp.contribution_frequency.per_year
    escalation = ONE + inp.contribution_growth_percent / HUNDRED

    balance = contributed = inp.initial
    out = [_Year(balance, contributed)]
    for year in range(inp.years):
        payment = contribution * escalation**year
        for month in range(1, MONTHS + 1):
            balance *= monthly
            if month % every == 0:
                balance += payment
                contributed += payment
        out.append(_Year(balance, contributed))
    return out


def _check(inp: ForecastInput, contribution: Decimal) -> None:
    if not 1 <= inp.years <= MAX_YEARS:
        raise InvalidForecast(f"years must be between 1 and {MAX_YEARS}")
    if inp.initial < 0 or contribution < 0:
        raise InvalidForecast("amounts must not be negative")
    m = inp.compounding.per_year
    if ONE + (inp.annual_return_percent - inp.annual_fee_percent) / HUNDRED / m <= 0:
        raise InvalidForecast("the return net of fees must be above -100% per period")
    if inp.inflation_percent <= -HUNDRED or inp.contribution_growth_percent <= -HUNDRED:
        raise InvalidForecast("inflation and contribution growth must be above -100%")
