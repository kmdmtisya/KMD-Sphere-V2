"""Holdings derived from the ledger: weighted average cost in the portfolio currency (ADR-0012).

Pure functions (no I/O). The database cache and the API live in `holdings_service.py`."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, localcontext

from app.modules.transactions.rules import ASSET_INCOME

# Plenty of digits for averages and products; nothing is rounded inside the calculation.
PRECISION = 50
ZERO = Decimal(0)


@dataclass(frozen=True)
class Entry:
    """The ledger fields the calculation needs."""

    id: uuid.UUID
    transaction_type: str
    trade_date: date
    created_at: datetime
    asset_id: uuid.UUID | None
    quantity: Decimal | None
    gross_amount: Decimal
    fees: Decimal
    taxes: Decimal
    fx: Decimal
    reverses: uuid.UUID | None = None


@dataclass
class Position:
    asset_id: uuid.UUID
    quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO
    realized_pl: Decimal = ZERO
    income: Decimal = ZERO
    expenses: Decimal = ZERO
    last_transaction_at: datetime | None = None
    entries: int = field(default=0, repr=False)

    @property
    def average_cost(self) -> Decimal | None:
        if self.quantity == 0:
            return None
        with localcontext() as ctx:
            ctx.prec = PRECISION
            return self.cost_basis / self.quantity


class InconsistentLedger(ValueError):
    """The ledger sells or transfers out more units than it holds at that point."""


def effective(entries: Iterable[Entry]) -> list[Entry]:
    """Entries in calculation order, leaving out every reversed entry and its reversal."""
    entries = list(entries)
    reversed_ids = {e.reverses for e in entries if e.reverses is not None}
    kept = [e for e in entries if e.reverses is None and e.id not in reversed_ids]
    return sorted(kept, key=lambda e: (e.trade_date, e.created_at, e.id))


def compute(entries: Iterable[Entry]) -> dict[uuid.UUID, Position]:
    """Positions per asset. Raises InconsistentLedger if a quantity would go below zero."""
    positions: dict[uuid.UUID, Position] = {}
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for e in effective(entries):
            if e.asset_id is None:
                continue
            p = positions.setdefault(e.asset_id, Position(e.asset_id))
            _apply(p, e)
            p.entries += 1
            if p.last_transaction_at is None or e.created_at > p.last_transaction_at:
                p.last_transaction_at = e.created_at
    return positions


def never_negative(entries: Iterable[Entry]) -> bool:
    """Whether the date-ordered history keeps every quantity at or above zero."""
    try:
        compute(entries)
    except InconsistentLedger:
        return False
    return True


def _apply(p: Position, e: Entry) -> None:
    kind = e.transaction_type
    qty = e.quantity or ZERO
    if kind in ("BUY", "TRANSFER_IN"):
        p.quantity += qty
        p.cost_basis += (e.gross_amount + e.fees + e.taxes) * e.fx
    elif kind in ("SELL", "TRANSFER_OUT"):
        if qty > p.quantity:
            raise InconsistentLedger(
                f"{kind} of {qty} on {e.trade_date} exceeds the {p.quantity} units held"
            )
        # Selling everything removes exactly the remaining cost (no residue from the division).
        removed = p.cost_basis if qty == p.quantity else p.cost_basis / p.quantity * qty
        if kind == "SELL":
            proceeds = (e.gross_amount - e.fees - e.taxes) * e.fx
            p.realized_pl += proceeds - removed
        p.cost_basis -= removed
        p.quantity -= qty
    elif kind in ASSET_INCOME or kind == "INTEREST":
        p.income += e.gross_amount * e.fx
        p.expenses += (e.fees + e.taxes) * e.fx
    elif kind in ("FEE", "TAX"):
        p.expenses += (e.gross_amount + e.fees + e.taxes) * e.fx
    # VALUATION_ADJUSTMENT: a valuation input, not a cost (P05-T07, P05-T08).
