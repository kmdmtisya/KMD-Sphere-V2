"""/api/v1/forecasts: compound, scenario and goal forecasts (P06-T02).

Computed by the deterministic engine from the request alone; no user data is read, but a signed-in
user is required like every other API route. Formulas: docs/design/forecast-engine.md."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid
from app.core.money import CURRENCY_PATTERN, Money
from app.db.session import get_session
from app.modules.forecasting import service
from app.modules.forecasting.schemas import (
    CompoundForecastIn,
    CompoundForecastOut,
    ForecastInReporting,
    ForecastProjection,
    GoalForecastIn,
    GoalForecastOut,
    ScenarioForecastIn,
    ScenarioForecastOut,
)
from app.modules.fx.snapshot import SnapshotService, convert
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.market_data.fx import FxRateUnavailable

router = APIRouter(prefix="/api/v1/forecasts", tags=["forecasts"])
RESPONSES = {**UNAUTHORIZED, **invalid("forecast assumptions (outside the published limits)")}
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ReportingCurrency = Annotated[
    str | None,
    Query(
        pattern=CURRENCY_PATTERN,
        description="Also show the end values in this currency, at today's rate (P11-T06). The "
        "forecast itself stays in its own currency; future exchange rates are not forecast.",
    ),
]


async def _in_reporting(
    request: Request, session: AsyncSession, projection: ForecastProjection, currency: str | None
) -> ForecastInReporting | None:
    """The end values translated at today's snapshot rate; None without a currency or a rate."""
    source = projection.final_nominal.currency
    if currency is None or currency == source:
        return None
    snapshots = SnapshotService(session, request.app.state.settings.fx_pivot_currency)
    places = await snapshots.decimal_places(currency)
    snapshot = await snapshots.current()
    try:
        rate = snapshot.rate(source, currency)
    except FxRateUnavailable:
        return None
    return ForecastInReporting(
        currency=currency,
        rate=rate.rate,
        rate_timestamp=rate.rate_timestamp,
        snapshot_id=str(snapshot.id),
        final_nominal=Money(
            amount=convert(projection.final_nominal.amount, rate.rate, places), currency=currency
        ),
        final_real=Money(
            amount=convert(projection.final_real.amount, rate.rate, places), currency=currency
        ),
    )


@router.post("/compound", response_model=CompoundForecastOut, responses=RESPONSES)
async def compound_forecast(
    body: CompoundForecastIn,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    reporting_currency: ReportingCurrency = None,
) -> CompoundForecastOut:
    """Project one set of assumptions: yearly nominal and real values, contributions and growth.
    An illustration of the assumptions, not a prediction."""
    out = service.compound(body)
    out.in_reporting = await _in_reporting(request, session, out.projection, reporting_currency)
    return out


@router.post("/scenarios", response_model=ScenarioForecastOut, responses=RESPONSES)
async def scenario_forecast(
    body: ScenarioForecastIn,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    reporting_currency: ReportingCurrency = None,
) -> ScenarioForecastOut:
    """The same assumptions under the user's conservative, base and growth returns. With a
    reporting currency, the base scenario's end values are also shown in it."""
    out = service.scenarios(body)
    out.in_reporting = await _in_reporting(request, session, out.scenarios.base, reporting_currency)
    return out


@router.post("/goal", response_model=GoalForecastOut, responses=RESPONSES)
async def goal_forecast(
    body: GoalForecastIn,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    reporting_currency: ReportingCurrency = None,
) -> GoalForecastOut:
    """The first-year contribution per period that reaches a target, with the resulting
    projection."""
    out = service.goal(body)
    out.in_reporting = await _in_reporting(request, session, out.projection, reporting_currency)
    return out
