"""/api/v1/portfolios/{portfolio_id}/valuations."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, conflict, invalid, not_found
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.transactions.valuations_schemas import (
    ValuationCreate,
    ValuationOut,
    ValuationPage,
    ValuationUpdate,
)
from app.modules.transactions.valuations_service import MAX_PAGE, ValuationService

router = APIRouter(prefix="/api/v1/portfolios/{portfolio_id}/valuations", tags=["valuations"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
_ARCHIVED = conflict("The portfolio is archived")


@router.post(
    "",
    response_model=ValuationOut,
    status_code=201,
    responses={
        **UNAUTHORIZED,
        **not_found("portfolio"),
        **invalid("valuation"),
        **conflict("A valuation already exists at that moment, or the portfolio is archived"),
    },
)
async def create_valuation(
    portfolio_id: uuid.UUID, body: ValuationCreate, user: CurrentUserDep, session: SessionDep
) -> ValuationOut:
    """Records the value of an asset at a moment, with where the value comes from."""
    return await ValuationService(session).create(user.id, portfolio_id, body)


@router.get(
    "",
    response_model=ValuationPage,
    responses={**UNAUTHORIZED, **not_found("portfolio"), **invalid("cursor")},
)
async def list_valuations(
    portfolio_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    asset_id: uuid.UUID | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
) -> ValuationPage:
    """Valuations, newest as-of first."""
    return await ValuationService(session).page(user.id, portfolio_id, asset_id, cursor, limit)


@router.get(
    "/latest",
    response_model=list[ValuationOut],
    responses={**UNAUTHORIZED, **not_found("portfolio")},
)
async def latest_valuations(
    portfolio_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    at: Annotated[
        AwareDatetime | None, Query(description="Values as of this moment (default: now)")
    ] = None,
) -> list[ValuationOut]:
    """For each asset, the valuation with the latest as-of at or before `at`."""
    return await ValuationService(session).latest(user.id, portfolio_id, at)


@router.get(
    "/{valuation_id}",
    response_model=ValuationOut,
    responses={**UNAUTHORIZED, **not_found("valuation")},
)
async def get_valuation(
    portfolio_id: uuid.UUID, valuation_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> ValuationOut:
    """One valuation."""
    return await ValuationService(session).get(user.id, portfolio_id, valuation_id)


@router.patch(
    "/{valuation_id}",
    response_model=ValuationOut,
    responses={**UNAUTHORIZED, **not_found("valuation"), **invalid("change"), **_ARCHIVED},
)
async def update_valuation(
    portfolio_id: uuid.UUID,
    valuation_id: uuid.UUID,
    change: ValuationUpdate,
    user: CurrentUserDep,
    session: SessionDep,
) -> ValuationOut:
    """Corrects the value, source or note (audited). The as-of time cannot change."""
    return await ValuationService(session).update(user.id, portfolio_id, valuation_id, change)


@router.delete(
    "/{valuation_id}",
    status_code=204,
    responses={**UNAUTHORIZED, **not_found("valuation"), **_ARCHIVED},
)
async def delete_valuation(
    portfolio_id: uuid.UUID, valuation_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> Response:
    """Removes a mistaken valuation (audited)."""
    await ValuationService(session).delete(user.id, portfolio_id, valuation_id)
    return Response(status_code=204)
