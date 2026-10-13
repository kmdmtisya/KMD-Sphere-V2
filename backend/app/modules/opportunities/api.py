"""/api/v1/ai/opportunities (P12-T06): run the opportunity pipeline, and read your past runs.
Runs are owner-scoped: another user's run is not found."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import LlmProvider
from app.ai.providers.errors import LlmNotConfigured
from app.ai.providers.registry import build_llm
from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.opportunities.schemas import (
    OpportunitiesRequest,
    RunOut,
    RunSummaryOut,
    run_out,
    summary_out,
)
from app.modules.opportunities.service import OpportunityService, RunRequest
from app.modules.research.embedding import build_embedder
from app.modules.scoring.scoring import validate_weights

router = APIRouter(prefix="/api/v1/ai/opportunities", tags=["ai"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _llm(request: Request) -> LlmProvider | None:
    """The app's model, or None (template explanations) when none is configured."""
    state = request.app.state
    llm: LlmProvider | None = getattr(state, "llm", None)
    if llm is not None:
        return llm
    settings: Settings = state.settings
    if settings.ai_provider == "fake":
        return None
    try:
        return build_llm(settings)
    except LlmNotConfigured:
        return None


def _service(request: Request, session: AsyncSession) -> OpportunityService:
    settings: Settings = request.app.state.settings
    return OpportunityService(
        session,
        validate_weights(settings.opportunity_score_weights),
        build_embedder(settings.research_embedder),
        _llm(request),
        settings.ai_opportunity_runs_per_day,
    )


@router.post(
    "",
    response_model=RunOut,
    status_code=201,
    summary="Find research opportunities",
    responses={
        **UNAUTHORIZED,
        **not_found("portfolio"),
        **invalid("request"),
        429: {"description": "Too many runs in 24 hours"},
    },
)
async def run_opportunities(
    body: OpportunitiesRequest, request: Request, user: CurrentUserDep, session: SessionDep
) -> RunOut:
    """Runs the pipeline for you: the investment universe filtered by your eligibility, scored on
    measured characteristics, checked against your portfolio when given, with retrieved research;
    the model explains each candidate from those facts only, and an explanation that adds a fact,
    a figure or a forecast is replaced by fixed wording. The run is stored unchanged and
    audited. Limit: 10 runs per 24 hours. Not advice; nothing is bought."""
    if body.amount is not None and body.portfolio_id is None:
        raise InvalidValueError("An amount needs a portfolio to check it against.")
    service = _service(request, session)
    run = await service.run(
        user.id,
        RunRequest(
            portfolio_id=body.portfolio_id,
            amount=body.amount.amount if body.amount else None,
            amount_currency=body.amount.currency if body.amount else None,
            asset_class=body.asset_class,
            limit=body.limit,
        ),
        datetime.now(UTC),
    )
    stored, items = await service.get(user.id, run.id)
    return run_out(stored, items)


@router.get(
    "/runs",
    response_model=list[RunSummaryOut],
    summary="Your opportunity runs",
    responses=UNAUTHORIZED,
)
async def list_runs(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[RunSummaryOut]:
    """Your runs, newest first."""
    return [summary_out(r) for r in await _service(request, session).runs(user.id, limit)]


@router.get(
    "/runs/{run_id}",
    response_model=RunOut,
    summary="One of your opportunity runs",
    responses={**UNAUTHORIZED, **not_found("opportunity run")},
)
async def get_run(
    run_id: uuid.UUID, request: Request, user: CurrentUserDep, session: SessionDep
) -> RunOut:
    """A run exactly as it was produced. Another user's run is not found."""
    run, items = await _service(request, session).get(user.id, run_id)
    return run_out(run, items)
