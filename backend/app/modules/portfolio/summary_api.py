"""Portfolio summaries: /api/v1/portfolios/{id}/summary and the consolidated summary.

Included before the portfolio router, so `consolidated` is never read as a portfolio id."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.money import CURRENCY_PATTERN
from app.db.session import get_session
from app.modules.fx.reporting import ReportingDep
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
    reporting: ReportingDep,
    currency: Annotated[
        str | None,
        Query(
            pattern=CURRENCY_PATTERN,
            description="Reporting currency; default: your reporting-currency setting",
        ),
    ] = None,
) -> SummaryOut:
    """All active portfolios together, in one currency (docs/design/portfolio-summary.md), with
    the rate snapshot every conversion used."""
    out = await SummaryService(session).consolidated(user.id, currency)
    out.reporting = reporting.out(out.currency)
    return out


@router.get(
    "/{portfolio_id}/summary",
    response_model=SummaryOut,
    responses={**UNAUTHORIZED, **not_found("portfolio"), **invalid("currency")},
)
async def portfolio_summary(
    portfolio_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    reporting: ReportingDep,
    currency: Annotated[
        str | None,
        Query(
            pattern=CURRENCY_PATTERN,
            description="View the portfolio in this currency; default: its base currency. "
            "Nothing is saved: the portfolio keeps its base currency",
        ),
    ] = None,
) -> SummaryOut:
    """Totals for one portfolio in its base currency (or viewed in `currency`), with currency
    breakdown, freshness and the rate snapshot used."""
    service = SummaryService(session)
    out = (
        await service.portfolio_in(user.id, portfolio_id, currency)
        if currency
        else await service.portfolio(user.id, portfolio_id)
    )
    out.reporting = reporting.out(out.currency)
    return out
