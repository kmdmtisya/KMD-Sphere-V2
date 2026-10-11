"""Income events (P06-T05): one per income entry of the ledger, kept in step with it in the same
database transaction, so the table can always be rebuilt from the ledger. Other modules read
payments through `payments()`; the income figures are in app/modules/networth/income.py."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.transactions.holdings import Entry, effective
from app.modules.transactions.models import INCOME_TYPES, Transaction
from app.modules.transactions.repository import LedgerRepository


@dataclass(frozen=True)
class Payment:
    """One income payment, in its own currency; `fx_rate` converts it to the portfolio
    currency (the posting's rate)."""

    transaction_id: uuid.UUID
    asset_id: uuid.UUID | None
    income_type: str
    paid_on: date
    currency: str
    gross: Decimal
    fees: Decimal
    taxes: Decimal
    fx_rate: Decimal


class IncomeEventService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = LedgerRepository(session)

    async def record(self, row: Transaction) -> None:
        """Called by the ledger for every new entry: an income entry adds its event, a reversal
        removes the event of the entry it reverses."""
        if row.reverses_transaction_id is not None:
            await self._repo.delete_income_event(row.reverses_transaction_id)
        elif row.transaction_type in INCOME_TYPES:
            await self._repo.add_income_event(row)

    async def payments(self, portfolio_id: uuid.UUID) -> list[Payment]:
        """Every income payment of a portfolio, by date. The caller has authorised it."""
        return [
            Payment(
                e.transaction_id,
                e.asset_id,
                e.income_type,
                e.paid_on,
                e.currency,
                e.gross,
                e.fees,
                e.taxes,
                e.fx_rate,
            )
            for e in await self._repo.income_events(portfolio_id)
        ]


def expected_payments(entries: Iterable[Entry]) -> list[Payment]:
    """What the income events must be for a ledger: its effective income entries (used to check
    the table against the ledger)."""
    return sorted(
        (
            Payment(
                e.id,
                e.asset_id,
                e.transaction_type,
                e.trade_date,
                e.currency,
                e.gross_amount,
                e.fees,
                e.taxes,
                e.fx,
            )
            for e in effective(entries)
            if e.transaction_type in INCOME_TYPES
        ),
        key=lambda p: (p.paid_on, p.transaction_id),
    )
