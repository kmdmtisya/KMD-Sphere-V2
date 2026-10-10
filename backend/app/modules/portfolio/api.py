"""/api/v1/portfolios."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, conflict, invalid, not_found
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.portfolio.schemas import PortfolioCreate, PortfolioOut, PortfolioUpdate
from app.modules.portfolio.service import PortfolioService

router = APIRouter(prefix="/api/v1/portfolios", tags=["portfolios"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
_NOT_FOUND = not_found("portfolio")


@router.post(
    "",
    response_model=PortfolioOut,
    status_code=201,
    responses={
        **UNAUTHORIZED,
        **invalid("portfolio"),
        **conflict("Name already used, or the portfolio limit is reached"),
    },
)
async def create_portfolio(
    body: PortfolioCreate, user: CurrentUserDep, session: SessionDep
) -> PortfolioOut:
    """Creates a portfolio for the signed-in user."""
    return await PortfolioService(session).create(user.id, body)


@router.get("", response_model=list[PortfolioOut], responses=UNAUTHORIZED)
async def list_portfolios(
    user: CurrentUserDep,
    session: SessionDep,
    include_archived: Annotated[bool, Query(description="Also return archived portfolios")] = False,
) -> list[PortfolioOut]:
    """The signed-in user's portfolios, oldest first."""
    return await PortfolioService(session).list(user.id, include_archived)


@router.get(
    "/{portfolio_id}", response_model=PortfolioOut, responses={**UNAUTHORIZED, **_NOT_FOUND}
)
async def get_portfolio(
    portfolio_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> PortfolioOut:
    """One of the signed-in user's portfolios."""
    return await PortfolioService(session).get(user.id, portfolio_id)


@router.patch(
    "/{portfolio_id}",
    response_model=PortfolioOut,
    responses={
        **UNAUTHORIZED,
        **_NOT_FOUND,
        **invalid("change"),
        **conflict("Name already used, or the portfolio is archived"),
    },
)
async def update_portfolio(
    portfolio_id: uuid.UUID, change: PortfolioUpdate, user: CurrentUserDep, session: SessionDep
) -> PortfolioOut:
    """Renames or re-describes a portfolio. The base currency cannot change."""
    return await PortfolioService(session).update(user.id, portfolio_id, change)


@router.post(
    "/{portfolio_id}/archive",
    response_model=PortfolioOut,
    responses={**UNAUTHORIZED, **_NOT_FOUND},
)
async def archive_portfolio(
    portfolio_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> PortfolioOut:
    """Archives a portfolio: it stays readable but cannot change. Repeating it is harmless."""
    return await PortfolioService(session).archive(user.id, portfolio_id)
