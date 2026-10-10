"""/api/v1/portfolios/{portfolio_id}/transactions: the append-only ledger.

There is deliberately no PUT, PATCH or DELETE: corrections are reversals."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, conflict, invalid, not_found
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.transactions.holdings_service import HoldingsService
from app.modules.transactions.repository import ListFilter
from app.modules.transactions.schemas import (
    HoldingOut,
    ReversalCreate,
    TransactionCreate,
    TransactionOut,
    TransactionPage,
    TransactionType,
)
from app.modules.transactions.service import MAX_PAGE, LedgerService, Result

router = APIRouter(prefix="/api/v1/portfolios/{portfolio_id}/transactions", tags=["transactions"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        pattern=r"^[\x21-\x7e]{1,128}$",
        description="Client-chosen key (1-128 visible ASCII). A retry with the same key and "
        "content returns the original entry (200, Idempotent-Replayed: true).",
    ),
]
_REPLAY_HEADER = {
    "Idempotent-Replayed": {
        "description": "true when the response repeats an earlier posting with this key",
        "schema": {"type": "string", "enum": ["true"]},
    }
}
_POST_RESPONSES = {
    **UNAUTHORIZED,
    **not_found("portfolio"),
    **invalid("entry"),
    **conflict(
        "Archived portfolio, quantity above the units held, or an Idempotency-Key reused "
        "for a different entry"
    ),
    200: {"description": "Idempotent replay of an earlier posting", "headers": _REPLAY_HEADER},
}


def _respond(result: Result, response: Response) -> TransactionOut:
    if result.replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    return result.transaction


@router.post("", response_model=TransactionOut, status_code=201, responses=_POST_RESPONSES)
async def post_transaction(
    portfolio_id: uuid.UUID,
    body: TransactionCreate,
    user: CurrentUserDep,
    session: SessionDep,
    response: Response,
    idempotency_key: IdempotencyKey = None,
) -> TransactionOut:
    """Posts an entry to the portfolio's ledger. Posted entries never change."""
    result = await LedgerService(session).post(user.id, portfolio_id, body, idempotency_key)
    return _respond(result, response)


@router.get(
    "",
    response_model=TransactionPage,
    responses={**UNAUTHORIZED, **not_found("portfolio"), **invalid("filter or cursor")},
)
async def list_transactions(
    portfolio_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    transaction_type: TransactionType | None = None,
    asset_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
) -> TransactionPage:
    """The ledger, newest first, with optional filters and cursor pagination."""
    return await LedgerService(session).list(
        user.id,
        portfolio_id,
        ListFilter(transaction_type, asset_id, from_date, to_date),
        cursor,
        limit,
    )


@router.get(
    "/{transaction_id}",
    response_model=TransactionOut,
    responses={**UNAUTHORIZED, **not_found("transaction")},
)
async def get_transaction(
    portfolio_id: uuid.UUID, transaction_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> TransactionOut:
    """One ledger entry, with its reversal link."""
    return await LedgerService(session).get(user.id, portfolio_id, transaction_id)


@router.post(
    "/{transaction_id}/reversal",
    response_model=TransactionOut,
    status_code=201,
    responses={
        **_POST_RESPONSES,
        **not_found("transaction"),
        **conflict("Already reversed, a reversal, or it would leave a negative position"),
    },
)
async def reverse_transaction(
    portfolio_id: uuid.UUID,
    transaction_id: uuid.UUID,
    body: ReversalCreate,
    user: CurrentUserDep,
    session: SessionDep,
    response: Response,
    idempotency_key: IdempotencyKey = None,
) -> TransactionOut:
    """Cancels an entry by posting its reversal (same figures, linked to it). To correct an
    entry, reverse it and post the right one."""
    result = await LedgerService(session).reverse(
        user.id, portfolio_id, transaction_id, body, idempotency_key
    )
    return _respond(result, response)


holdings_router = APIRouter(prefix="/api/v1/portfolios/{portfolio_id}/holdings", tags=["holdings"])


@holdings_router.get(
    "", response_model=list[HoldingOut], responses={**UNAUTHORIZED, **not_found("portfolio")}
)
async def list_holdings(
    portfolio_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    include_closed: Annotated[
        bool, Query(description="Also return assets no longer held (for realised results)")
    ] = False,
) -> list[HoldingOut]:
    """Positions derived from the ledger: quantity, weighted average cost, cost basis, realised
    profit, income and expenses, in the portfolio currency (ADR-0012)."""
    return await HoldingsService(session).list(user.id, portfolio_id, include_closed)
