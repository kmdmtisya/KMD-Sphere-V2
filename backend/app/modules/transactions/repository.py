"""Ledger queries. The ledger is append-only: this repository can add entries and read them, and
has no update or delete (the database refuses those too, migration 0004)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, and_, delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.authz import owned_by
from app.core.money import round_half_up
from app.modules.portfolio.models import Portfolio
from app.modules.transactions.holdings import Entry, Position
from app.modules.transactions.models import Holding, Transaction

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

    async def entries(self, portfolio_id: uuid.UUID, asset_id: uuid.UUID) -> list[Entry]:
        """Every ledger entry for one asset in one portfolio, including reversals."""
        result = await self._session.execute(
            select(Transaction).where(
                Transaction.portfolio_id == portfolio_id, Transaction.asset_id == asset_id
            )
        )
        return [to_entry(t) for t in result.scalars()]

    async def save_holding(
        self, portfolio_id: uuid.UUID, position: Position, currency: str
    ) -> None:
        """Stores one derived position (insert or replace). Figures are rounded half-up to the
        column scale (ADR-0012)."""
        values = {
            "portfolio_id": portfolio_id,
            "asset_id": position.asset_id,
            "quantity": round_half_up(position.quantity, 12),
            "cost_basis": round_half_up(position.cost_basis, 8),
            "realized_pl": round_half_up(position.realized_pl, 8),
            "income": round_half_up(position.income, 8),
            "expenses": round_half_up(position.expenses, 8),
            "currency": currency,
            "last_transaction_at": position.last_transaction_at,
            "computed_at": func.now(),
        }
        stmt = pg_insert(Holding).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_holdings_portfolio_id_asset_id",
            set_={k: stmt.excluded[k] for k in values if k not in ("portfolio_id", "asset_id")}
            | {"updated_at": func.now()},
        )
        await self._session.execute(stmt)

    async def delete_holding(self, portfolio_id: uuid.UUID, asset_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(Holding).where(
                Holding.portfolio_id == portfolio_id, Holding.asset_id == asset_id
            )
        )

    async def holdings(self, portfolio_id: uuid.UUID, include_closed: bool) -> list[Holding]:
        stmt = select(Holding).where(Holding.portfolio_id == portfolio_id)
        if not include_closed:
            stmt = stmt.where(Holding.quantity > 0)
        result = await self._session.execute(stmt.order_by(Holding.asset_id))
        return list(result.scalars())

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


def to_entry(t: Transaction) -> Entry:
    return Entry(
        id=t.id,
        transaction_type=t.transaction_type,
        trade_date=t.trade_date,
        created_at=t.created_at,
        asset_id=t.asset_id,
        quantity=t.quantity,
        gross_amount=t.gross_amount,
        fees=t.fees,
        taxes=t.taxes,
        fx=t.fx_rate_to_portfolio_currency,
        reverses=t.reverses_transaction_id,
    )
