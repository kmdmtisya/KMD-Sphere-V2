"""/api/v1/me: the signed-in user's profile and preferences."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.identity.schemas import MeResponse, PreferencesUpdate
from app.modules.identity.service import IdentityService

router = APIRouter(prefix="/api/v1/me", tags=["identity"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing, invalid or expired access token"}
}


@router.get("", response_model=MeResponse, responses=_UNAUTHORIZED)
async def get_me(user: CurrentUserDep, session: SessionDep) -> MeResponse:
    """The signed-in user, created on first sign-in."""
    return await IdentityService(session).me(user.id)


@router.patch(
    "/preferences",
    response_model=MeResponse,
    responses={**_UNAUTHORIZED, 422: {"description": "Invalid preference values"}},
)
async def update_preferences(
    change: PreferencesUpdate, user: CurrentUserDep, session: SessionDep
) -> MeResponse:
    """Updates any subset of display name, base currency, locale, time zone and UI preferences."""
    return await IdentityService(session).update_preferences(user.id, change)
