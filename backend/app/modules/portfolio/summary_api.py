"""Portfolio summaries: /api/v1/portfolios/{id}/summary and the consolidated summary.

Included before the portfolio router, so `consolidated` is never read as a portfolio id."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.money import CURRENCY_PATTERN
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.portfolio.summary_schemas import SummaryOut
from app.modules.portfolio.summary_service import SummaryService

router = APIRouter(prefix="/api/v1/portfolios", tags=["portfolios"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/consolidated/summary",
    response_model=SummaryOut,
    responses={**UNAUTHORIZED, **invalid("currency")},
)
async def consolidated_summary(
    user: CurrentUserDep,
    session: SessionDep,
    currency: Annotated[
        str | None,
        Query(pattern=CURRENCY_PATTERN, description="Reporting currency; default: your base"),
    ] = None,
) -> SummaryOut:
    """All active portfolios together, in one currency (docs/design/portfolio-summary.md)."""
    return await SummaryService(session).consolidated(user.id, currency)


@router.get(
    "/{portfolio_id}/summary",
    response_model=SummaryOut,
    responses={**UNAUTHORIZED, **not_found("portfolio")},
)
async def portfolio_summary(
    portfolio_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> SummaryOut:
    """Totals for one portfolio in its base currency, with currency breakdown and freshness."""
    return await SummaryService(session).portfolio(user.id, portfolio_id)
