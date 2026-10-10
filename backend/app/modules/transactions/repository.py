"""Ledger queries. The ledger is append-only: this repository can add entries and read them, and
has no update or delete (the database refuses those too, migration 0004)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, case, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.authz import owned_by
from app.modules.portfolio.models import Portfolio
from app.modules.transactions.models import Transaction
from app.modules.transactions.rules import POSITION_SIGN

_reversal = aliased(Transaction, name="reversal")


@dataclass(frozen=True)
class ListFilter:
    transaction_type: str | None = None
    asset_id: uuid.UUID | None = None
    from_date: date | None = None
    to_date: date | None = None


@dataclass(frozen=True)
class Cursor:
    trade_date: date
    created_at: datetime
    id: uuid.UUID


class LedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def owned_portfolio(
        self, user_id: uuid.UUID, portfolio_id: uuid.UUID, *, lock: bool = False
    ) -> Portfolio | None:
        """The caller's portfolio. With `lock`, the row is locked until the transaction ends,
        so postings to one portfolio are applied one at a time (position checks stay correct)."""
        stmt = owned_by(Portfolio, user_id).where(Portfolio.id == portfolio_id)
        if lock:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt.execution_options(populate_existing=True))
        return result.scalar_one_or_none()

    async def position(self, portfolio_id: uuid.UUID, asset_id: uuid.UUID) -> Decimal:
        """Units of `asset_id` held: trades and transfers, with every reversal cancelling the
        entry it reverses."""
        direction = case(
            *[(Transaction.transaction_type == t, s) for t, s in POSITION_SIGN.items()], else_=0
        )
        reversal_factor = case((Transaction.reverses_transaction_id.is_(None), 1), else_=-1)
        result = await self._session.execute(
            select(
                func.coalesce(
                    func.sum(func.coalesce(Transaction.quantity, 0) * direction * reversal_factor),
                    0,
                )
            ).where(Transaction.portfolio_id == portfolio_id, Transaction.asset_id == asset_id)
        )
        return Decimal(result.scalar_one())

    async def by_idempotency_key(self, portfolio_id: uuid.UUID, key: str) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(
                Transaction.portfolio_id == portfolio_id, Transaction.idempotency_key == key
            )
        )
        return result.scalar_one_or_none()

    async def get(
        self, portfolio_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> tuple[Transaction, uuid.UUID | None] | None:
        """An entry of this portfolio and the id of its reversal, if any."""
        result = await self._session.execute(
            self._with_reversal().where(
                Transaction.portfolio_id == portfolio_id, Transaction.id == transaction_id
            )
        )
        row = result.first()
        return (row[0], row[1]) if row else None

    async def add(self, values: dict[str, Any]) -> Transaction:
        row = Transaction(**values)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def page(
        self,
        portfolio_id: uuid.UUID,
        filters: ListFilter,
        after: Cursor | None,
        limit: int,
    ) -> list[tuple[Transaction, uuid.UUID | None]]:
        """Newest first: trade date, then entry time, then id (a stable order for the cursor)."""
        stmt = self._with_reversal().where(Transaction.portfolio_id == portfolio_id)
        if filters.transaction_type:
            stmt = stmt.where(Transaction.transaction_type == filters.transaction_type)
        if filters.asset_id:
            stmt = stmt.where(Transaction.asset_id == filters.asset_id)
        if filters.from_date:
            stmt = stmt.where(Transaction.trade_date >= filters.from_date)
        if filters.to_date:
            stmt = stmt.where(Transaction.trade_date <= filters.to_date)
        if after is not None:
            stmt = stmt.where(
                tuple_(Transaction.trade_date, Transaction.created_at, Transaction.id)
                < tuple_(after.trade_date, after.created_at, after.id)
            )
        stmt = stmt.order_by(
            Transaction.trade_date.desc(), Transaction.created_at.desc(), Transaction.id.desc()
        ).limit(limit)
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    @staticmethod
    def _with_reversal() -> Select[Transaction, uuid.UUID]:
        return select(Transaction, _reversal.id).outerjoin(
            _reversal,
            and_(
                _reversal.reverses_transaction_id == Transaction.id,
                _reversal.portfolio_id == Transaction.portfolio_id,
            ),
        )
