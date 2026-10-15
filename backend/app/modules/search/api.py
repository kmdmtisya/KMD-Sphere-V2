"""GET /api/v1/search?q=: the signed-in user's own portfolios, goals, liabilities and assets."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.search.service import MAX_QUERY, SearchOut, SearchService

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get(
    "",
    response_model=SearchOut,
    responses=UNAUTHORIZED,
    summary="Search your own records",
    description="Portfolios, goals, liabilities and the assets you hold, watch or created. "
    "Only the signed-in user's records are ever returned.",
)
async def search(
    user: CurrentUserDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY, description="Text to find")],
) -> SearchOut:
    return await SearchService(session).search(user.id, q)
