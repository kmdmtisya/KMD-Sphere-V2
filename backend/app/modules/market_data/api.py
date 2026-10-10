"""/api/v1/fx-rates: the FX rate WealthSphere would use, with its provenance."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED
from app.core.money import CURRENCY_PATTERN
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.market_data.fx import end_of_day
from app.modules.market_data.schemas import FxQuoteOut
from app.modules.market_data.service import FxService

router = APIRouter(prefix="/api/v1/fx-rates", tags=["fx"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
Currency = Annotated[str, Path(pattern=CURRENCY_PATTERN, description="ISO 4217 code")]


@router.get(
    "/{base}/{quote}",
    response_model=FxQuoteOut,
    responses={
        **UNAUTHORIZED,
        404: {"description": "No rate for this pair within the allowed age (fx-rate-unavailable)"},
    },
)
async def get_fx_rate(
    base: Currency,
    quote: Currency,
    user: CurrentUserDep,
    session: SessionDep,
    on: Annotated[
        date | None,
        Query(description="The historical rate for this day; omit for the latest rate"),
    ] = None,
) -> FxQuoteOut:
    """The rate from `base` to `quote`, chosen by the documented selection rules."""
    q = await FxService(session).quote(base, quote, end_of_day(on) if on else None)
    return FxQuoteOut(
        base_currency=q.base_currency,
        quote_currency=q.quote_currency,
        rate=q.rate,
        as_of=q.as_of,
        provider=q.provider,
        inverted=q.inverted,
        stale=q.stale,
        rule="historical" if on else "latest",
    )
