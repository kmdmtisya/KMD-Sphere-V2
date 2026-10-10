"""/api/v1/me: the signed-in user's profile and preferences."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.identity.schemas import (
    MeResponse,
    PreferencesUpdate,
    RiskProfileCreate,
    RiskProfileOut,
    RiskProfileUpdate,
)
from app.modules.identity.service import IdentityService

router = APIRouter(prefix="/api/v1/me", tags=["identity"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing, invalid or expired access token"},
    429: {
        "description": "Rate limit exceeded (docs/security.md, API protection)",
        "headers": {
            "Retry-After": {
                "description": "Seconds to wait before retrying",
                "schema": {"type": "integer", "minimum": 1},
            }
        },
    },
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


# --------------------------------------------------------------------------- risk profiles

risk_router = APIRouter(prefix="/api/v1/risk-profiles", tags=["identity"])
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "No such risk profile for this user"}
}


@risk_router.post("", response_model=RiskProfileOut, status_code=201, responses=_UNAUTHORIZED)
async def add_risk_profile(
    body: RiskProfileCreate, user: CurrentUserDep, session: SessionDep
) -> RiskProfileOut:
    """Records a new risk self-assessment for the signed-in user."""
    return await IdentityService(session).add_risk_profile(user.id, body)


@risk_router.get("", response_model=list[RiskProfileOut], responses=_UNAUTHORIZED)
async def list_risk_profiles(user: CurrentUserDep, session: SessionDep) -> list[RiskProfileOut]:
    """The signed-in user's risk assessments, newest first."""
    return await IdentityService(session).list_risk_profiles(user.id)


@risk_router.get(
    "/{risk_profile_id}",
    response_model=RiskProfileOut,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def get_risk_profile(
    risk_profile_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> RiskProfileOut:
    """One of the signed-in user's risk assessments."""
    return await IdentityService(session).get_risk_profile(user.id, risk_profile_id)


@risk_router.patch(
    "/{risk_profile_id}",
    response_model=RiskProfileOut,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def update_risk_profile(
    risk_profile_id: uuid.UUID,
    change: RiskProfileUpdate,
    user: CurrentUserDep,
    session: SessionDep,
) -> RiskProfileOut:
    """Corrects one of the signed-in user's risk assessments."""
    return await IdentityService(session).update_risk_profile(user.id, risk_profile_id, change)
