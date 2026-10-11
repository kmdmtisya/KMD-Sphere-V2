"""Compound forecast engine (P06-T01). Formulas and rounding: docs/design/forecast-engine.md.

Pure functions: no I/O, no LLM, no binary floating point. A forecast illustrates the assumptions
it is given; it is never a prediction or a guaranteed return."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from enum import StrEnum

from app.core.money import minor_units, round_half_up, round_up

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
    amount: Decimal  # per period in the first year, rounded up to the currency (ADR-0006)
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
    amount = round_up(exact, minor_units(inp.currency))  # enough to reach the target
    return RequiredContribution(
        amount=amount,
        exact=exact,
        reached_without_contributions=reached,
        projection=project(replace(inp, contribution=amount)),
    )


# ------------------------------------------------------------- horizons in months (P06-T06)


def value_after(inp: ForecastInput, months: int) -> tuple[Decimal, Decimal]:
    """Nominal and real (today's money) value after `months` months, unrounded. `inp.years` is
    ignored: goals end on a date, not after whole years."""
    _check_months(months, allow_zero=True)
    _check(inp, inp.contribution)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        balance = inp.initial
        for balance, _ in _steps(inp, inp.contribution, months):  # noqa: B007
            pass
        return balance, balance / _deflator(inp, months)


def months_to_reach(
    inp: ForecastInput, target: Decimal, *, real: bool = False, limit: int = MAX_YEARS * MONTHS
) -> int | None:
    """The first month (0 = now) at which the value reaches `target`, with the contribution of
    `inp`; None when it does not within `limit` months."""
    _check(inp, inp.contribution)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        if inp.initial >= target:
            return 0
        for month, (balance, _) in enumerate(_steps(inp, inp.contribution, limit), start=1):
            if (balance / _deflator(inp, month) if real else balance) >= target:
                return month
    return None


def required_contribution_by(
    inp: ForecastInput, target: Decimal, months: int, *, real: bool = False
) -> Decimal | None:
    """The first-year contribution per period that reaches `target` after `months` months, every
    other input fixed (unrounded; 0 when the initial amount alone reaches it). None when no
    contribution falls within the horizon (yearly contributions and a date under a year away),
    so no contribution can help."""
    _check_months(months)
    if target < 0:
        raise InvalidForecast("the target must not be negative")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        nominal_target = target * _deflator(inp, months) if real else target
        without = _final(inp, ZERO, months)
        if without >= nominal_target:
            return ZERO
        per_unit = _final(inp, ONE, months) - without
        return (nominal_target - without) / per_unit if per_unit > 0 else None


def _final(inp: ForecastInput, contribution: Decimal, months: int) -> Decimal:
    balance = inp.initial
    for balance, _ in _steps(inp, contribution, months):  # noqa: B007
        pass
    return balance


def _deflator(inp: ForecastInput, months: int) -> Decimal:
    """(1 + inflation)^(months / 12)."""
    base = ONE + inp.inflation_percent / HUNDRED
    return base ** (months // MONTHS) * (base ** (Decimal(months % MONTHS) / MONTHS))


def _check_months(months: int, *, allow_zero: bool = False) -> None:
    if not (0 if allow_zero else 1) <= months <= MAX_YEARS * MONTHS:
        raise InvalidForecast(f"the horizon must be at most {MAX_YEARS} years")


# ------------------------------------------------------------------------------------ stepping


def _simulate(inp: ForecastInput, contribution: Decimal) -> list[_Year]:
    """Balance and contributions at the end of each year 0..n, unrounded."""
    if not 1 <= inp.years <= MAX_YEARS:
        raise InvalidForecast(f"years must be between 1 and {MAX_YEARS}")
    out = [_Year(inp.initial, inp.initial)]
    for month, (balance, contributed) in enumerate(
        _steps(inp, contribution, inp.years * MONTHS), start=1
    ):
        if month % MONTHS == 0:
            out.append(_Year(balance, contributed))
    return out


def _steps(
    inp: ForecastInput, contribution: Decimal, months: int
) -> Iterator[tuple[Decimal, Decimal]]:
    """Balance and contributions at the end of months 1..`months`. Steps at the monthly factor
    equivalent to the compounding; contributions are paid at the end of each contribution period
    and step up once a year."""
    _check(inp, contribution)
    m = inp.compounding.per_year
    periodic = ONE + (inp.annual_return_percent - inp.annual_fee_percent) / HUNDRED / m
    monthly = periodic if m == MONTHS else periodic ** (Decimal(m) / MONTHS)
    every = MONTHS // inp.contribution_frequency.per_year
    escalation = ONE + inp.contribution_growth_percent / HUNDRED

    balance = contributed = inp.initial
    payment = contribution
    for month in range(1, months + 1):
        if month > 1 and (month - 1) % MONTHS == 0:
            payment = contribution * escalation ** ((month - 1) // MONTHS)
        balance *= monthly
        if month % every == 0:
            balance += payment
            contributed += payment
        yield balance, contributed


def _check(inp: ForecastInput, contribution: Decimal) -> None:
    if inp.initial < 0 or contribution < 0:
        raise InvalidForecast("amounts must not be negative")
    m = inp.compounding.per_year
    if ONE + (inp.annual_return_percent - inp.annual_fee_percent) / HUNDRED / m <= 0:
        raise InvalidForecast("the return net of fees must be above -100% per period")
    if inp.inflation_percent <= -HUNDRED or inp.contribution_growth_percent <= -HUNDRED:
        raise InvalidForecast("inflation and contribution growth must be above -100%")
