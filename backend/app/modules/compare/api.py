"""POST /api/v1/ai/compare and /api/v1/ai/simulate (P12-T07). Deterministic: no model is used.
Compare shows what is measured or recorded, past figures labelled past; Simulate shows the forecast
engine's results under the user's own return assumptions. Neither presents a future return as a
fact, and neither buys anything."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.core.money import DecimalString, Money, minor_units, round_half_up
from app.db.session import get_session
from app.modules.compare.service import MAX_COMPARED, Compared, CompareService, Simulation
from app.modules.compatibility.schemas import CompatibilityOut, compatibility_out
from app.modules.forecasting.schemas import ScenarioForecastIn, ScenarioForecastOut
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.opportunities.service import horizon
from app.modules.scoring.schemas import ScoreOut, scored_out
from app.modules.scoring.scoring import validate_weights

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
HUNDRED = Decimal(100)
COMPARE_NOTICE = (
    "Past figures describe what happened, not what will happen. No future return is shown. Not "
    "advice; DEMO instruments are fictional."
)
SIMULATE_NOTICE = (
    "An illustration under the return assumptions you entered, not a forecast of this "
    "instrument. Real returns vary and can be negative; nothing is guaranteed."
)


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_ids: list[uuid.UUID] = Field(min_length=2, max_length=MAX_COMPARED)
    portfolio_id: uuid.UUID | None = Field(
        default=None, description="Show each instrument's diversification impact on it"
    )
    amount: Money | None = Field(
        default=None,
        description="Hypothetical amount for the impact, in the portfolio's base currency; "
        "needed with portfolio_id",
    )


class PastFigures(BaseModel):
    """Measured over the last year from stored prices; past, never a forecast."""

    price_change_percent: DecimalString | None
    volatility_percent: DecimalString | None
    max_drawdown_percent: DecimalString | None
    last_close: str | None
    weeks_of_prices: int


class ComparedOut(BaseModel):
    asset_id: uuid.UUID
    symbol: str | None
    name: str
    asset_class: str
    country: str | None
    currency: str
    is_demo: bool
    risk_level: int
    liquidity: str
    minimum_investment: Money | None
    expense_ratio_percent: DecimalString | None = Field(description="Funds only")
    income_yield: None = Field(
        default=None, description="Not available: no distribution data is stored yet"
    )
    past: PastFigures
    score: ScoreOut
    eligible: bool
    eligibility_reasons: list[str]
    research_horizon: dict[str, Any]
    diversification: CompatibilityOut | None


class CompareOut(BaseModel):
    items: list[ComparedOut]
    notice: str = COMPARE_NOTICE


class SimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    assumptions: ScenarioForecastIn = Field(
        description="Your conservative, base and growth returns, contributions, years and fees"
    )
    portfolio_id: uuid.UUID | None = Field(
        default=None, description="Also check how the initial investment fits this portfolio"
    )


class SimulateOut(BaseModel):
    asset_id: uuid.UUID
    symbol: str | None
    name: str
    is_demo: bool
    returns_source: Literal["your_assumptions"] = "your_assumptions"
    simulation: ScenarioForecastOut
    notes: list[str] = Field(description="How your assumptions differ from what is recorded")
    fit: CompatibilityOut | None
    notice: str = SIMULATE_NOTICE


def _pct(x: Decimal | None) -> Decimal | None:
    return None if x is None else round_half_up(x * HUNDRED, 2)


def compared_out(c: Compared) -> ComparedOut:
    s, f = c.scored, c.scored.features
    item = s.item
    minimum = item.minimum_investment
    return ComparedOut(
        asset_id=item.asset_id,
        symbol=item.symbol,
        name=item.name,
        asset_class=item.asset_class,
        country=item.country,
        currency=item.currency,
        is_demo=item.is_demo,
        risk_level=item.risk_level,
        liquidity=item.liquidity.value,
        minimum_investment=None
        if minimum is None
        else Money(
            amount=round_half_up(minimum, minor_units(item.currency)), currency=item.currency
        ),
        expense_ratio_percent=_pct(f.expense_ratio),
        past=PastFigures(
            price_change_percent=_pct(f.trailing_return),
            volatility_percent=_pct(f.volatility),
            max_drawdown_percent=_pct(f.max_drawdown),
            last_close=f.last_close.isoformat() if f.last_close else None,
            weeks_of_prices=f.weeks,
        ),
        score=scored_out(s).score,
        eligible=item.eligibility.eligible,
        eligibility_reasons=item.eligibility.reasons,
        research_horizon=horizon(item.risk_level, item.liquidity),
        diversification=None if c.compatibility is None else compatibility_out(c.compatibility),
    )


def _service(request: Request, session: AsyncSession) -> CompareService:
    settings: Settings = request.app.state.settings
    return CompareService(session, validate_weights(settings.opportunity_score_weights))


@router.post(
    "/compare",
    response_model=CompareOut,
    summary="Compare instruments side by side",
    responses={**UNAUTHORIZED, **not_found("instrument or portfolio"), **invalid("request")},
)
async def compare(
    body: CompareRequest, request: Request, user: CurrentUserDep, session: SessionDep
) -> CompareOut:
    """2 to 5 universe instruments side by side: class, geography, currency, risk level,
    liquidity, minimum, fees, past figures over the last year (labelled past), the explainable
    score, your eligibility, a stated research horizon and, with a portfolio and an amount, the
    diversification impact. Income yield is not available yet. No future return is shown."""
    if (body.portfolio_id is None) != (body.amount is None):
        raise InvalidValueError("A portfolio and an amount go together.")
    items = await _service(request, session).compare(
        user.id,
        body.asset_ids,
        body.portfolio_id,
        body.amount.amount if body.amount else None,
        body.amount.currency if body.amount else None,
        datetime.now(UTC),
    )
    return CompareOut(items=[compared_out(c) for c in items])


def simulate_out(s: Simulation) -> SimulateOut:
    item = s.scored.item
    return SimulateOut(
        asset_id=item.asset_id,
        symbol=item.symbol,
        name=item.name,
        is_demo=item.is_demo,
        simulation=s.forecast,
        notes=s.notes,
        fit=None if s.compatibility is None else compatibility_out(s.compatibility),
    )


@router.post(
    "/simulate",
    response_model=SimulateOut,
    summary="Simulate an instrument under your assumptions",
    responses={**UNAUTHORIZED, **not_found("instrument or portfolio"), **invalid("request")},
)
async def simulate(
    body: SimulateRequest, request: Request, user: CurrentUserDep, session: SessionDep
) -> SimulateOut:
    """Runs the deterministic forecast engine for one universe instrument under the
    conservative, base and growth returns you enter (there is no default return). Notes say where
    your assumptions differ from what is recorded, for example the instrument's expense ratio.
    With a portfolio, the initial investment's fit is checked. An illustration, never a forecast
    of the instrument."""
    result = await _service(request, session).simulate(
        user.id, body.asset_id, body.assumptions, body.portfolio_id, datetime.now(UTC)
    )
    return simulate_out(result)
