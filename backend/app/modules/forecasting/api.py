"""/api/v1/forecasts: compound, scenario and goal forecasts (P06-T02).

Computed by the deterministic engine from the request alone; no user data is read, but a signed-in
user is required like every other API route. Formulas: docs/design/forecast-engine.md."""

from fastapi import APIRouter

from app.core.api_responses import UNAUTHORIZED, invalid
from app.modules.forecasting import service
from app.modules.forecasting.schemas import (
    CompoundForecastIn,
    CompoundForecastOut,
    GoalForecastIn,
    GoalForecastOut,
    ScenarioForecastIn,
    ScenarioForecastOut,
)
from app.modules.identity.dependencies import CurrentUserDep

router = APIRouter(prefix="/api/v1/forecasts", tags=["forecasts"])
RESPONSES = {**UNAUTHORIZED, **invalid("forecast assumptions (outside the published limits)")}


@router.post("/compound", response_model=CompoundForecastOut, responses=RESPONSES)
async def compound_forecast(body: CompoundForecastIn, user: CurrentUserDep) -> CompoundForecastOut:
    """Project one set of assumptions: yearly nominal and real values, contributions and growth.
    An illustration of the assumptions, not a prediction."""
    return service.compound(body)


@router.post("/scenarios", response_model=ScenarioForecastOut, responses=RESPONSES)
async def scenario_forecast(body: ScenarioForecastIn, user: CurrentUserDep) -> ScenarioForecastOut:
    """The same assumptions under the user's conservative, base and growth returns."""
    return service.scenarios(body)


@router.post("/goal", response_model=GoalForecastOut, responses=RESPONSES)
async def goal_forecast(body: GoalForecastIn, user: CurrentUserDep) -> GoalForecastOut:
    """The first-year contribution per period that reaches a target, with the resulting
    projection."""
    return service.goal(body)
