"""POST /api/v1/universe/compatibility (P12-T04): what adding an amount of a universe instrument
would do to one of the user's portfolios, and whether it fits. Hypothetical; nothing is bought."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.db.session import get_session
from app.modules.compatibility.schemas import (
    CompatibilityOut,
    CompatibilityRequest,
    compatibility_out,
)
from app.modules.compatibility.service import CompatibilityService
from app.modules.identity.dependencies import CurrentUserDep

router = APIRouter(prefix="/api/v1/universe", tags=["universe"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/compatibility",
    response_model=CompatibilityOut,
    summary="Check how an instrument fits a portfolio",
    responses={**UNAUTHORIZED, **not_found("portfolio or instrument"), **invalid("request")},
)
async def compatibility(
    body: CompatibilityRequest, user: CurrentUserDep, session: SessionDep
) -> CompatibilityOut:
    """Adds the amount (in the portfolio's base currency) to the portfolio as new money and
    re-measures it with the Portfolio Doctor's rules: concentration, asset class, currency and
    liquidity before and after, and the checks that would change. The verdict is not_suitable
    when the instrument is not eligible for you or the amount is below its minimum, caution when
    something gets materially worse, and fits otherwise. Hypothetical, never an order; another
    user's portfolio is not found."""
    result = await CompatibilityService(session).check(
        user.id,
        body.portfolio_id,
        body.asset_id,
        body.amount.amount,
        body.amount.currency,
        datetime.now(UTC),
    )
    return compatibility_out(result)
