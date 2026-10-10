"""FX rates. Global reference data (no owner), timestamped, never rounded (ADR-0006).

P11-T02 extends this table with rate type and status and adds snapshots."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, String, UniqueConstraint
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
