"""Maps validated forecast requests to the engine and its results to responses (P06-T02).
No state and no user data: forecasts are computed from the inputs alone."""

from datetime import UTC, datetime
from decimal import Decimal

from app.core.money import Money
from app.modules.forecasting import engine
from app.modules.forecasting.limits import NOTICE
from app.modules.forecasting.schemas import (
    CompoundForecastIn,
    CompoundForecastOut,
    ForecastAssumptions,
    ForecastProjection,
    ForecastScenarios,
    GoalForecastIn,
    GoalForecastOut,
    ScenarioForecastIn,
    ScenarioForecastOut,
    YearValue,
)


def compound(body: CompoundForecastIn) -> CompoundForecastOut:
    projection = engine.project(_input(body, body.contribution.amount))
    return CompoundForecastOut(
        currency=body.currency,
        projection=_projection(projection),
        assumptions=body,
        as_of=datetime.now(UTC),
        notice=NOTICE,
    )


def scenarios(body: ScenarioForecastIn) -> ScenarioForecastOut:
    results = engine.scenarios(
        _input(body, body.contribution.amount),
        {
            "conservative": body.conservative_return_percent,
            "base": body.annual_return_percent,
            "growth": body.growth_return_percent,
        },
    )
    return ScenarioForecastOut(
        currency=body.currency,
        scenarios=ForecastScenarios(**{k: _projection(p) for k, p in results.items()}),
        assumptions=body,
        as_of=datetime.now(UTC),
        notice=NOTICE,
    )


def goal(body: GoalForecastIn) -> GoalForecastOut:
    result = engine.required_contribution(
        _input(body, Decimal(0)), body.target.amount, real=body.target_in_todays_money
    )
    return GoalForecastOut(
        currency=body.currency,
        required_contribution=Money(amount=result.amount, currency=body.currency),
        reached_without_contributions=result.reached_without_contributions,
        projection=_projection(result.projection),
        assumptions=body,
        as_of=datetime.now(UTC),
        notice=NOTICE,
    )


def _input(body: ForecastAssumptions, contribution: Decimal) -> engine.ForecastInput:
    return engine.ForecastInput(
        currency=body.currency,
        initial=body.initial_investment.amount,
        contribution=contribution,
        annual_return_percent=body.annual_return_percent,
        years=body.years,
        contribution_growth_percent=body.contribution_growth_percent,
        inflation_percent=body.inflation_percent,
        annual_fee_percent=body.annual_fee_percent,
        compounding=body.compounding_frequency,
        contribution_frequency=body.contribution_frequency,
    )


def _projection(p: engine.Projection) -> ForecastProjection:
    def money(amount: Decimal) -> Money:
        return Money(amount=amount, currency=p.currency)

    return ForecastProjection(
        annual_return_percent=p.annual_return_percent,
        nominal=[YearValue(year=y.year, value=y.nominal) for y in p.series],
        real=[YearValue(year=y.year, value=y.real) for y in p.series],
        contributions=[YearValue(year=y.year, value=y.contributions) for y in p.series],
        final_nominal=money(p.final_nominal),
        final_real=money(p.final_real),
        total_contributions=money(p.total_contributions),
        total_growth=money(p.total_growth),
    )
