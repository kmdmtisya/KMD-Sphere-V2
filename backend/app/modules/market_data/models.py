"""FX rates. Global reference data (no owner), timestamped, never rounded (ADR-0006).

P11-T02 extends this table with rate type and status and adds snapshots."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import RATE, Base, TimestampMixin, UUIDPrimaryKeyMixin


class FxRate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """1 `base_currency` = `rate` `quote_currency`, per `provider` at `rate_timestamp`."""

    __tablename__ = "fx_rates"
    __table_args__ = (
        CheckConstraint("base_currency ~ '^[A-Z]{3}$'", name="base_currency"),
        CheckConstraint("quote_currency ~ '^[A-Z]{3}$'", name="quote_currency"),
        CheckConstraint("base_currency <> quote_currency", name="distinct_currencies"),
        CheckConstraint("rate > 0", name="rate_positive"),
        UniqueConstraint(
            "base_currency",
            "quote_currency",
            "provider",
            "rate_timestamp",
            name="uq_fx_rates_pair_provider_timestamp",
        ),
        Index(
            "ix_fx_rates_pair_rate_timestamp", "base_currency", "quote_currency", "rate_timestamp"
        ),
    )

    base_currency: Mapped[str] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(RATE)
    provider: Mapped[str] = mapped_column(String(32))
    # When the rate was valid (the provider's timestamp) and when we fetched it.
    rate_timestamp: Mapped[datetime] = mapped_column()
    retrieved_at: Mapped[datetime] = mapped_column()


PRICE_TYPES = ("quote", "close")


class MarketPrice(UUIDPrimaryKeyMixin, Base):
    """A price of a global asset from a provider (P08-T05). Immutable: a row is never updated, a
    newer price is a new row. Every row says who provided it, when it was valid (`as_of`), when we
    fetched it (`retrieved_at`) and when we stored it (`ingested_at`). The price is in the asset's
    own currency (checked on ingestion)."""

    __tablename__ = "market_prices"
    __table_args__ = (
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("price_type IN ('quote', 'close')", name="price_type"),
        CheckConstraint("retrieved_at >= as_of", name="retrieved_after_as_of"),
        UniqueConstraint(
            "asset_id",
            "provider",
            "price_type",
            "as_of",
            name="uq_market_prices_asset_provider_type_as_of",
        ),
        Index("ix_market_prices_asset_id_as_of", "asset_id", "as_of"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    price: Mapped[Decimal] = mapped_column(RATE)
    currency: Mapped[str] = mapped_column(String(3))
    price_type: Mapped[str] = mapped_column(String(8))
    provider: Mapped[str] = mapped_column(String(32))
    as_of: Mapped[datetime] = mapped_column()
    retrieved_at: Mapped[datetime] = mapped_column()
    ingested_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
