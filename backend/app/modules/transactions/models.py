"""Ledger, derived holdings and manual valuations.

- `transactions` is the **append-only source of truth**: rows are never updated or deleted
  (database triggers, migration 0004). A mistake is corrected by a *reversal* entry that points at
  the original (`reverses_transaction_id`) and carries the original's figures; the holdings logic
  (P05-T05) treats a reversal as the negation. All amounts therefore stay non-negative, except a
  VALUATION_ADJUSTMENT, which can be a loss.
- `holdings` is **derived** from the ledger and can always be rebuilt from it; it is a cache.
- `valuations` are user-entered values for assets without a market price, as of a date.

Amounts are NUMERIC (ADR-0006): money 28,8; quantities 28,12; rates 28,12. Every posting keeps its
own currency and the FX rate (with its timestamp and source) to the portfolio currency."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AMOUNT, QUANTITY, RATE, Base, TimestampMixin, UUIDPrimaryKeyMixin

TRANSACTION_TYPES = (
    "BUY",
    "SELL",
    "DEPOSIT",
    "WITHDRAWAL",
    "DIVIDEND",
    "INTEREST",
    "COUPON",
    "RENT",
    "DISTRIBUTION",
    "FEE",
    "TAX",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "VALUATION_ADJUSTMENT",
)
_TYPES_SQL = ", ".join(f"'{t}'" for t in TRANSACTION_TYPES)


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        # Target of the composite foreign key below: a reversal must be in the same portfolio.
        UniqueConstraint("portfolio_id", "id", name="uq_transactions_portfolio_id_id"),
        ForeignKeyConstraint(
            ["portfolio_id", "reverses_transaction_id"],
            ["transactions.portfolio_id", "transactions.id"],
            ondelete="RESTRICT",
            name="fk_transactions_reversal_same_portfolio",
        ),
        # An entry can be reversed once.
        UniqueConstraint("reverses_transaction_id", name="uq_transactions_reverses_transaction_id"),
        UniqueConstraint(
            "portfolio_id", "idempotency_key", name="uq_transactions_portfolio_id_idempotency_key"
        ),
        CheckConstraint(f"transaction_type IN ({_TYPES_SQL})", name="transaction_type"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("source IN ('manual', 'import', 'system')", name="source"),
        CheckConstraint("fees >= 0 AND taxes >= 0", name="fees_taxes_non_negative"),
        CheckConstraint(
            "transaction_type = 'VALUATION_ADJUSTMENT' OR gross_amount >= 0",
            name="gross_amount_non_negative",
        ),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("unit_price IS NULL OR unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("fx_rate_to_portfolio_currency > 0", name="fx_rate_positive"),
        CheckConstraint(
            "settlement_date IS NULL OR settlement_date >= trade_date",
            name="settlement_after_trade",
        ),
        CheckConstraint(
            "transaction_type NOT IN ('BUY', 'SELL') "
            "OR (asset_id IS NOT NULL AND quantity > 0 AND unit_price IS NOT NULL)",
            name="trade_has_asset_quantity_price",
        ),
        CheckConstraint(
            "reverses_transaction_id IS NULL OR reverses_transaction_id <> id",
            name="not_self_reversal",
        ),
        CheckConstraint(
            "idempotency_key IS NULL OR length(idempotency_key) BETWEEN 1 AND 128",
            name="idempotency_key_length",
        ),
        Index("ix_transactions_portfolio_id_trade_date", "portfolio_id", "trade_date", "id"),
        Index("ix_transactions_asset_id", "asset_id"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT")
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    transaction_type: Mapped[str] = mapped_column(String(24))
    trade_date: Mapped[date] = mapped_column()
    settlement_date: Mapped[date | None] = mapped_column()
    quantity: Mapped[Decimal | None] = mapped_column(QUANTITY)
    unit_price: Mapped[Decimal | None] = mapped_column(AMOUNT)
    gross_amount: Mapped[Decimal] = mapped_column(AMOUNT)
    fees: Mapped[Decimal] = mapped_column(AMOUNT, server_default=text("0"))
    taxes: Mapped[Decimal] = mapped_column(AMOUNT, server_default=text("0"))
    # The currency the posting was made in, and the rate that converts it to the portfolio's base
    # currency (1 when they are the same). The rate keeps its source and the time it was valid.
    currency: Mapped[str] = mapped_column(String(3))
    fx_rate_to_portfolio_currency: Mapped[Decimal] = mapped_column(RATE, server_default=text("1"))
    fx_rate_as_of: Mapped[datetime | None] = mapped_column()
    fx_rate_source: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16), server_default=text("'manual'"))
    # A client-chosen key: posting the same key twice returns the first posting (P05-T04).
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    reverses_transaction_id: Mapped[uuid.UUID | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )


class Holding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Derived position of one asset in one portfolio (rebuildable from the ledger)."""

    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "asset_id", name="uq_holdings_portfolio_id_asset_id"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        Index("ix_holdings_asset_id", "asset_id"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    quantity: Mapped[Decimal] = mapped_column(QUANTITY)
    # Cost basis and realised result, in the portfolio's base currency (`currency`).
    cost_basis: Mapped[Decimal] = mapped_column(AMOUNT)
    realized_pl: Mapped[Decimal] = mapped_column(AMOUNT, server_default=text("0"))
    # Income from the asset (dividends, coupons, rent, distributions, interest) and costs charged
    # to it (fees, taxes, withholding), in the portfolio currency (ADR-0012).
    income: Mapped[Decimal] = mapped_column(AMOUNT, server_default=text("0"))
    expenses: Mapped[Decimal] = mapped_column(AMOUNT, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3))
    # The latest ledger entry the figures include, and when they were computed.
    last_transaction_at: Mapped[datetime | None] = mapped_column()
    computed_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Valuation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user-entered value of an asset (property, private business, pension) as of a date."""

    __tablename__ = "valuations"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "asset_id", "as_of", name="uq_valuations_portfolio_id_asset_id_as_of"
        ),
        CheckConstraint("value >= 0", name="value_non_negative"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("length(btrim(source)) BETWEEN 1 AND 64", name="source"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    value: Mapped[Decimal] = mapped_column(AMOUNT)
    currency: Mapped[str] = mapped_column(String(3))
    as_of: Mapped[datetime] = mapped_column()
    # A label such as "owner estimate", "bank statement" or "valuation report".
    source: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
