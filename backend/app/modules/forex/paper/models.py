"""Paper-trading tables (P13-T09.1, migration 0025). PAPER TRADING only.

Kept apart from real money by construction:
- separate tables, prefixed `forex_paper_`;
- no foreign key into portfolios, holdings, transactions or net-worth tables, and none from them;
- no real-portfolio module imports this package (a test checks the imports and the SQL).

Every row carries its owner (`user_id`), so every query starts from `owned_by` (ADR-0011); a
child row repeats the account's owner so it can be scoped without a join. Closed positions and
filled orders are never edited again: a fill, a close or a level change is a new state recorded
with its time."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PRICE = Numeric(20, 10)
MONEY = Numeric(20, 4)  # account-currency amounts, kept to 4 places; shown in minor units
UNITS = Numeric(20, 4)


class ForexPaperAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forex_paper_accounts"
    __table_args__ = (
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("starting_balance > 0", name="starting_balance"),
        CheckConstraint("status IN ('active', 'closed')", name="status"),
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 100", name="name"),
        Index("ix_forex_paper_accounts_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3))
    starting_balance: Mapped[Decimal] = mapped_column(MONEY)
    starting_balance_is_default: Mapped[bool] = mapped_column()
    status: Mapped[str] = mapped_column(String(16))


class ForexPaperOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forex_paper_orders"
    __table_args__ = (
        CheckConstraint("side IN ('long', 'short')", name="side"),
        CheckConstraint("order_type IN ('market', 'limit')", name="order_type"),
        CheckConstraint("status IN ('pending', 'filled', 'cancelled', 'rejected')", name="status"),
        CheckConstraint("units > 0", name="units"),
        CheckConstraint("(order_type = 'limit') = (limit_price IS NOT NULL)", name="limit_price"),
        Index("ix_forex_paper_orders_account_id_status", "account_id", "status"),
        Index("ix_forex_paper_orders_user_id", "user_id"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("forex_paper_accounts.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    instrument: Mapped[str] = mapped_column(
        String(7), ForeignKey("forex_instruments.code", ondelete="RESTRICT")
    )
    side: Mapped[str] = mapped_column(String(5))
    order_type: Mapped[str] = mapped_column(String(6))
    lots: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    units: Mapped[Decimal] = mapped_column(UNITS)
    limit_price: Mapped[Decimal | None] = mapped_column(PRICE)
    stop: Mapped[Decimal] = mapped_column(PRICE)
    target: Mapped[Decimal | None] = mapped_column(PRICE)
    status: Mapped[str] = mapped_column(String(10))
    reject_reason: Mapped[str | None] = mapped_column(String(200))
    strategy_tag: Mapped[str | None] = mapped_column(String(40))
    spec_version: Mapped[int] = mapped_column(Integer)
    checked_until: Mapped[datetime] = mapped_column()  # quotes up to here have been evaluated
    filled_at: Mapped[datetime | None] = mapped_column()
    cancelled_at: Mapped[datetime | None] = mapped_column()


class ForexPaperPosition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forex_paper_positions"
    __table_args__ = (
        CheckConstraint("side IN ('long', 'short')", name="side"),
        CheckConstraint("status IN ('open', 'closed')", name="status"),
        CheckConstraint("units > 0", name="units"),
        CheckConstraint(
            "exit_reason IS NULL OR exit_reason IN ('stop', 'target', 'manual')",
            name="exit_reason",
        ),
        CheckConstraint(
            "(status = 'closed') = (exit_at IS NOT NULL AND exit_price IS NOT NULL "
            "AND realised_pnl IS NOT NULL)",
            name="closed_fields",
        ),
        Index("ix_forex_paper_positions_account_id_status", "account_id", "status"),
        Index("ix_forex_paper_positions_user_id", "user_id"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("forex_paper_accounts.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("forex_paper_orders.id", ondelete="CASCADE"), unique=True
    )
    instrument: Mapped[str] = mapped_column(
        String(7), ForeignKey("forex_instruments.code", ondelete="RESTRICT")
    )
    side: Mapped[str] = mapped_column(String(5))
    lots: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    units: Mapped[Decimal] = mapped_column(UNITS)
    entry_price: Mapped[Decimal] = mapped_column(PRICE)  # the fill, slippage included
    entry_mid: Mapped[Decimal] = mapped_column(PRICE)  # the quote's mid, to measure costs paid
    entry_quote_at: Mapped[datetime] = mapped_column()  # the quote the fill used
    data_type: Mapped[str] = mapped_column(String(16))  # of that quote: simulated, tradable...
    stop: Mapped[Decimal] = mapped_column(PRICE)
    target: Mapped[Decimal | None] = mapped_column(PRICE)
    margin: Mapped[Decimal] = mapped_column(MONEY)  # account currency, at the entry rate
    entry_commission: Mapped[Decimal] = mapped_column(MONEY)  # account currency
    strategy_tag: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(6))
    checked_until: Mapped[datetime] = mapped_column()
    exit_price: Mapped[Decimal | None] = mapped_column(PRICE)
    exit_at: Mapped[datetime | None] = mapped_column()
    exit_reason: Mapped[str | None] = mapped_column(String(12))
    exit_rate: Mapped[Decimal | None] = mapped_column(Numeric(30, 15))  # quote -> account
    exit_rate_path: Mapped[str | None] = mapped_column(String(80))
    realised_pnl: Mapped[Decimal | None] = mapped_column(MONEY)  # account currency, net of costs
    costs: Mapped[Decimal | None] = mapped_column(MONEY)  # spread, slippage and commission paid


class ForexPaperJournalEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forex_paper_journal"
    __table_args__ = (
        CheckConstraint("length(btrim(note)) BETWEEN 1 AND 4000", name="note"),
        CheckConstraint("cardinality(tags) <= 10", name="tags"),
        Index("ix_forex_paper_journal_account_id_created_at", "account_id", "created_at"),
        Index("ix_forex_paper_journal_user_id", "user_id"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("forex_paper_accounts.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("forex_paper_positions.id", ondelete="SET NULL")
    )
    note: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
