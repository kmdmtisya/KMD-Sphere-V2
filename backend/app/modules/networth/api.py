"""/api/v1/liabilities and /api/v1/net-worth (P06-T07)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, conflict, invalid, not_found
from app.core.money import CURRENCY_PATTERN
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.networth.schemas import (
    LiabilityCreate,
    LiabilityOut,
    LiabilityUpdate,
    NetWorthOut,
)
from app.modules.networth.service import LiabilityService, NetWorthService

router = APIRouter(prefix="/api/v1/liabilities", tags=["net worth"])
networth_router = APIRouter(prefix="/api/v1/net-worth", tags=["net worth"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
_NOT_FOUND = not_found("liability")


def _now() -> datetime:
    return datetime.now(UTC)


@router.post(
    "",
    response_model=LiabilityOut,
    status_code=201,
    responses={
        **UNAUTHORIZED,
        **invalid("liability (limits, date or asset)"),
        **conflict("Name already used, or the liability limit is reached"),
    },
)
async def create_liability(
    body: LiabilityCreate, user: CurrentUserDep, session: SessionDep
) -> LiabilityOut:
    """Records something the user owes, with the date its balance applied."""
    return await LiabilityService(session).create(user.id, body, _now().date())


@router.get("", response_model=list[LiabilityOut], responses=UNAUTHORIZED)
async def list_liabilities(user: CurrentUserDep, session: SessionDep) -> list[LiabilityOut]:
    """The signed-in user's liabilities, by name."""
    return await LiabilityService(session).list(user.id)


@router.get(
    "/{liability_id}", response_model=LiabilityOut, responses={**UNAUTHORIZED, **_NOT_FOUND}
)
async def get_liability(
    liability_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> LiabilityOut:
    """One of the signed-in user's liabilities."""
    return await LiabilityService(session).get(user.id, liability_id)


@router.patch(
    "/{liability_id}",
    response_model=LiabilityOut,
    responses={**UNAUTHORIZED, **_NOT_FOUND, **invalid("change"), **conflict("Name already used")},
)
async def update_liability(
    liability_id: uuid.UUID, change: LiabilityUpdate, user: CurrentUserDep, session: SessionDep
) -> LiabilityOut:
    """Updates a liability, for example its latest balance."""
    return await LiabilityService(session).update(user.id, liability_id, change, _now().date())


@router.delete(
    "/{liability_id}",
    status_code=204,
    response_class=Response,
    responses={**UNAUTHORIZED, **_NOT_FOUND},
)
async def delete_liability(
    liability_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> Response:
    """Deletes a liability (for example one paid off)."""
    await LiabilityService(session).delete(user.id, liability_id)
    return Response(status_code=204)


@networth_router.get("", response_model=NetWorthOut, responses=UNAUTHORIZED)
async def get_net_worth(
    user: CurrentUserDep,
    session: SessionDep,
    currency: Annotated[
        str | None,
        Query(pattern=CURRENCY_PATTERN, description="Defaults to the user's base currency"),
    ] = None,
) -> NetWorthOut:
    """Total assets (the user's active portfolios) minus total liabilities, in one currency,
    with the FX rates used and how fresh and complete the figures are."""
    return await NetWorthService(session).user(user.id, currency, _now())
