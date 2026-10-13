"""POST /api/v1/ai/portfolio-doctor (P12-T01): deterministic findings for one of the user's
portfolios. No model is involved: the assistant explains these findings through the
`get_portfolio_diagnosis` tool, it never produces them. Cached per user like the analytics API
and recomputed after any of their writes."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.cache import ResponseCache
from app.db.session import get_session
from app.modules.doctor.schemas import DoctorOut, DoctorRequest, doctor_out
from app.modules.doctor.service import DoctorService
from app.modules.identity.dependencies import CurrentUserDep

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/portfolio-doctor",
    response_model=DoctorOut,
    summary="Check a portfolio's health",
    responses={**UNAUTHORIZED, **not_found("portfolio"), **invalid("request")},
)
async def portfolio_doctor(
    body: DoctorRequest, request: Request, user: CurrentUserDep, session: SessionDep
) -> DoctorOut:
    """Concentration (holding, asset class, sector, country), currency exposure, liquidity,
    volatility, drawdown, income dependence, goal alignment and data completeness, each with a
    severity against stated thresholds (docs/design/portfolio-doctor.md). Scenarios show what
    the measures would be with a capped holding or asset class; they are hypothetical, never
    orders. Another user's portfolio is not found."""

    async def compute() -> DoctorOut:
        now = datetime.now(UTC)
        result = await DoctorService(session).portfolio(user.id, body.portfolio_id, now)
        return doctor_out(
            result.portfolio_id, result.as_of, result.diagnosis, result.inputs.complete
        )

    cache: ResponseCache = request.app.state.response_cache
    return await cache.cached(
        user.id, "portfolio_doctor", {"portfolio": body.portfolio_id}, DoctorOut, compute
    )
