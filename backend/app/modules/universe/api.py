"""GET /api/v1/universe (P12-T02): the investment universe with each instrument's eligibility for
the signed-in user. Read-only; the universe is public reference data and the investor facts are
the user's own (country of residence, latest risk profile)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.universe.schemas import UniverseOut, universe_out
from app.modules.universe.service import UniverseService

router = APIRouter(prefix="/api/v1/universe", tags=["universe"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "",
    response_model=UniverseOut,
    summary="Investment universe and eligibility",
    responses={**UNAUTHORIZED, **invalid("query")},
)
async def list_universe(
    user: CurrentUserDep,
    session: SessionDep,
    asset_class: Annotated[
        str | None, Query(pattern=r"^[a-z][a-z0-9_]{1,39}$", description="An asset class code")
    ] = None,
    eligible_only: Annotated[
        bool, Query(description="Only instruments that pass every rule")
    ] = False,
) -> UniverseOut:
    """Every active instrument with the outcome of each eligibility rule (jurisdiction, risk,
    liquidity, active) for the signed-in user, and the facts used. Eligibility filters what
    analysis may consider; it is not a recommendation. Jurisdiction rules are not legally
    reviewed yet (P12-T10)."""
    universe = await UniverseService(session).for_user(user.id, asset_class)
    return universe_out(universe, eligible_only)
