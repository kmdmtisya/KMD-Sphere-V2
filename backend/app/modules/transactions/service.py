"""Ledger use cases: post, reverse, read and list.

- Postings to one portfolio are serialised (the portfolio row is locked for the transaction), so
  the position checks below cannot race.
- SELL, TRANSFER_OUT and reversals are checked against the date-ordered history: no quantity may
  go below zero on any date, including later sales that relied on the units (ADR-0012).
- An `Idempotency-Key` replay with the same content returns the original entry; the same key
  with different content is a conflict.
- Every posting and reversal writes an audit event in the same database transaction."""

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.authz import require_found
from app.core.errors import ConflictError, InvalidValueError
from app.core.money import Money, minor_units, round_half_up
from app.modules.assets.service import AssetService
from app.modules.portfolio.models import Portfolio
from app.modules.transactions.holdings import Entry, never_negative
from app.modules.transactions.holdings_service import HoldingsService
from app.modules.transactions.models import Transaction
from app.modules.transactions.repository import Cursor, LedgerRepository, ListFilter
from app.modules.transactions.rules import (
    POSITION_SIGN,
    Draft,
    Posting,
    RuleViolation,
    normalise,
)
from app.modules.transactions.schemas import (
    ReversalCreate,
    TransactionCreate,
    TransactionOut,
    TransactionPage,
)

MAX_PAGE = 100
# The columns that make two postings "the same" for an idempotent replay.
_IDENTITY = (
    "transaction_type",
    "trade_date",
    "settlement_date",
    "asset_id",
    "quantity",
    "unit_price",
    "gross_amount",
    "fees",
    "taxes",
    "currency",
    "fx_rate_to_portfolio_currency",
    "fx_rate_as_of",
    "fx_rate_source",
    "reverses_transaction_id",
    "note",
)


@dataclass(frozen=True)
class Result:
    transaction: TransactionOut
    replayed: bool


def today() -> date:
    return datetime.now(UTC).date()


class LedgerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = LedgerRepository(session)
        self._assets = AssetService(session)
        self._audit = AuditWriter(session)

    # ----------------------------------------------------------------------------- posting

    async def post(
        self,
        user_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        body: TransactionCreate,
        idempotency_key: str | None,
    ) -> Result:
        portfolio = await self._writable_portfolio(user_id, portfolio_id)
        try:
            posting = normalise(_draft(body), portfolio.base_currency, today())
        except RuleViolation as e:
            raise InvalidValueError(str(e)) from e
        values = {**_posting_values(posting), "note": body.note}
        replay = await self._replay(portfolio_id, idempotency_key, values)
        if replay is not None:
            return replay

        if posting.asset_id is not None and not await self._assets.is_visible(
            user_id, posting.asset_id
        ):
            raise InvalidValueError("asset_id: no such asset")
        sign = POSITION_SIGN.get(posting.transaction_type, 0)
        if sign < 0 and posting.asset_id is not None and posting.quantity is not None:
            history = await self._repo.entries(portfolio_id, posting.asset_id)
            candidate = _candidate(values, reverses=None)
            if not never_negative([*history, candidate]):
                raise ConflictError(
                    "Not enough units held on that date, or a later sale would no longer be "
                    "covered."
                )
        return await self._store(
            user_id, portfolio, values, idempotency_key, "transactions.transaction.posted"
        )

    async def reverse(
        self,
        user_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        transaction_id: uuid.UUID,
        body: ReversalCreate,
        idempotency_key: str | None,
    ) -> Result:
        portfolio = await self._writable_portfolio(user_id, portfolio_id)
        original, reversed_by = require_found(
            await self._repo.get(portfolio_id, transaction_id), "transaction"
        )
        values = {
            name: getattr(original, name)
            for name in _IDENTITY
            if name not in ("reverses_transaction_id", "note")
        }
        values.update(reverses_transaction_id=original.id, note=body.note)
        replay = await self._replay(portfolio_id, idempotency_key, values)
        if replay is not None:
            return replay
        if original.reverses_transaction_id is not None:
            raise ConflictError("A reversal cannot itself be reversed; post a new entry instead.")
        if reversed_by is not None:
            raise ConflictError("This entry has already been reversed.")
        sign = POSITION_SIGN.get(original.transaction_type, 0)
        if sign > 0 and original.asset_id is not None:
            history = await self._repo.entries(portfolio_id, original.asset_id)
            candidate = _candidate(values, reverses=original.id)
            if not never_negative([*history, candidate]):
                raise ConflictError(
                    "Reversing this entry would leave a negative position; reverse the later "
                    "sale or transfer first."
                )
        return await self._store(
            user_id, portfolio, values, idempotency_key, "transactions.transaction.reversed"
        )

    # ------------------------------------------------------------------------------ reading

    async def get(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> TransactionOut:
        require_found(await self._repo.owned_portfolio(user_id, portfolio_id), "portfolio")
        row, reversed_by = require_found(
            await self._repo.get(portfolio_id, transaction_id), "transaction"
        )
        return _out(row, reversed_by)

    async def list(
        self,
        user_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        filters: ListFilter,
        cursor: str | None,
        limit: int,
    ) -> TransactionPage:
        require_found(await self._repo.owned_portfolio(user_id, portfolio_id), "portfolio")
        limit = min(limit, MAX_PAGE)
        rows = await self._repo.page(portfolio_id, filters, _decode(cursor), limit + 1)
        page = rows[:limit]
        next_cursor = _encode(page[-1][0]) if len(rows) > limit else None
        return TransactionPage(items=[_out(r, rb) for r, rb in page], next_cursor=next_cursor)

    # ------------------------------------------------------------------------------ helpers

    async def _writable_portfolio(self, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> Portfolio:
        portfolio = require_found(
            await self._repo.owned_portfolio(user_id, portfolio_id, lock=True), "portfolio"
        )
        if portfolio.archived_at is not None:
            raise ConflictError("An archived portfolio takes no new entries.")
        return portfolio

    async def _replay(
        self, portfolio_id: uuid.UUID, key: str | None, values: dict[str, Any]
    ) -> Result | None:
        if key is None:
            return None
        existing = await self._repo.by_idempotency_key(portfolio_id, key)
        if existing is None:
            return None
        if any(getattr(existing, name) != values.get(name) for name in _IDENTITY):
            raise ConflictError("This Idempotency-Key was already used for a different entry.")
        found = await self._repo.get(portfolio_id, existing.id)
        assert found is not None  # noqa: S101 (just read in this transaction)
        return Result(_out(*found), replayed=True)

    async def _store(
        self,
        user_id: uuid.UUID,
        portfolio: Portfolio,
        values: dict[str, Any],
        idempotency_key: str | None,
        action: str,
    ) -> Result:
        portfolio_id = portfolio.id
        try:
            row = await self._repo.add(
                {
                    **values,
                    "portfolio_id": portfolio_id,
                    "idempotency_key": idempotency_key,
                    "created_by_user_id": user_id,
                    "source": "manual",
                }
            )
        except IntegrityError as e:
            await self._session.rollback()
            raise ConflictError("This entry conflicts with the ledger (already reversed?).") from e
        if row.asset_id is not None:
            await HoldingsService(self._session).rebuild_asset(
                portfolio_id, row.asset_id, portfolio.base_currency
            )
        await self._audit.record(
            action,
            Actor.user(user_id),
            resource_type="transaction",
            resource_id=row.id,
            details={
                "portfolio_id": str(portfolio_id),
                "transaction_type": row.transaction_type,
                "currency": row.currency,
                "reverses": str(row.reverses_transaction_id)
                if row.reverses_transaction_id
                else None,
            },
        )
        await self._session.commit()
        return Result(_out(row, None), replayed=False)


def _candidate(values: dict[str, Any], reverses: uuid.UUID | None) -> Entry:
    """The entry about to be stored, for checking the history it would create (it sorts after
    every existing entry on the same trade date)."""
    return Entry(
        id=uuid.uuid4(),
        transaction_type=values["transaction_type"],
        trade_date=values["trade_date"],
        created_at=datetime.now(UTC),
        asset_id=values["asset_id"],
        quantity=values["quantity"],
        gross_amount=values["gross_amount"],
        fees=values["fees"],
        taxes=values["taxes"],
        fx=values["fx_rate_to_portfolio_currency"],
        reverses=reverses,
    )


def _draft(body: TransactionCreate) -> Draft:
    return Draft(
        transaction_type=body.transaction_type,
        trade_date=body.trade_date,
        settlement_date=body.settlement_date,
        asset_id=body.asset_id,
        quantity=body.quantity,
        unit_price=body.unit_price,
        gross_amount=body.gross_amount,
        fees=body.fees,
        taxes=body.taxes,
        currency=body.currency,
        fx_rate=body.fx_rate_to_portfolio_currency,
        fx_rate_as_of=body.fx_rate_as_of,
        fx_rate_source=body.fx_rate_source,
    )


def _posting_values(p: Posting) -> dict[str, Any]:
    return {
        "transaction_type": p.transaction_type,
        "trade_date": p.trade_date,
        "settlement_date": p.settlement_date,
        "asset_id": p.asset_id,
        "quantity": p.quantity,
        "unit_price": p.unit_price,
        "gross_amount": p.gross_amount,
        "fees": p.fees,
        "taxes": p.taxes,
        "currency": p.currency,
        "fx_rate_to_portfolio_currency": p.fx_rate_to_portfolio_currency,
        "fx_rate_as_of": p.fx_rate_as_of,
        "fx_rate_source": p.fx_rate_source,
        "reverses_transaction_id": None,
    }


def _money(amount: Decimal, currency: str) -> Money:
    return Money(amount=round_half_up(amount, minor_units(currency)), currency=currency)


def _out(row: Transaction, reversed_by: uuid.UUID | None) -> TransactionOut:
    return TransactionOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        transaction_type=row.transaction_type,
        trade_date=row.trade_date,
        settlement_date=row.settlement_date,
        asset_id=row.asset_id,
        currency=row.currency,
        quantity=row.quantity,
        unit_price=Money(amount=row.unit_price.normalize(), currency=row.currency)
        if row.unit_price is not None
        else None,
        gross_amount=_money(row.gross_amount, row.currency),
        fees=_money(row.fees, row.currency),
        taxes=_money(row.taxes, row.currency),
        fx_rate_to_portfolio_currency=row.fx_rate_to_portfolio_currency,
        fx_rate_as_of=row.fx_rate_as_of,
        fx_rate_source=row.fx_rate_source,
        source=row.source,
        idempotency_key=row.idempotency_key,
        reverses_transaction_id=row.reverses_transaction_id,
        reversed_by_transaction_id=reversed_by,
        note=row.note,
        created_at=row.created_at,
    )


def _encode(row: Transaction) -> str:
    raw = json.dumps([row.trade_date.isoformat(), row.created_at.isoformat(), str(row.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode(cursor: str | None) -> Cursor | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        trade, created, ident = json.loads(base64.urlsafe_b64decode(padded))
        return Cursor(date.fromisoformat(trade), datetime.fromisoformat(created), uuid.UUID(ident))
    except (ValueError, TypeError, binascii.Error) as e:
        raise InvalidValueError("cursor: not a valid cursor") from e
