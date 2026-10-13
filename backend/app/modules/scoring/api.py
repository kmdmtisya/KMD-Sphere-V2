"""GET /api/v1/universe/scores (P12-T03): the explainable score of every universe instrument."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid
from app.core.config import Settings
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.scoring.schemas import ScoresOut, scores_out
from app.modules.scoring.scoring import validate_weights
from app.modules.scoring.service import ScoringService

router = APIRouter(prefix="/api/v1/universe", tags=["universe"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/scores",
    response_model=ScoresOut,
    summary="Explainable instrument scores",
    responses={**UNAUTHORIZED, **invalid("query")},
)
async def universe_scores(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    asset_class: Annotated[
        str | None, Query(pattern=r"^[a-z][a-z0-9_]{1,39}$", description="An asset class code")
    ] = None,
    eligible_only: Annotated[bool, Query(description="Only instruments eligible for you")] = False,
) -> ScoresOut:
    """Every active instrument's score from 0 to 100, decomposed into factor contributions
    (stability, resilience, past momentum, cost, liquidity, risk class) with the configured
    weights. Factors that could not be measured are listed and lower the coverage and confidence;
    with too little data there is no score. Scores describe measured characteristics: they are
    not forecasts, expected returns or recommendations."""
    settings: Settings = request.app.state.settings
    weights = validate_weights(settings.opportunity_score_weights)
    items = await ScoringService(session, weights).universe(user.id, asset_class, datetime.now(UTC))
    return scores_out(items, weights, eligible_only)
