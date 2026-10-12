"""Currency reference data, reporting-currency preferences and the conversion audit (P11-T02).

- `currencies` is reference data: adding a currency is a row, not a code change. Its
  `decimal_places` is the precision a converted amount is rounded to (ADR-0006).
- `user_currency_preferences` holds the global reporting currency (ADR-0010), one row per user.
- `fx_conversion_audit` records conversions that become financial records (DEC-28: AI answers,
  reports and exports, explicit converter use), never cosmetic display switches. Like the audit
  trail it has no foreign key to the user, so it outlives the rows it describes, and it is
  append-only.

The rates themselves stay in `fx_rates` (`modules/market_data`), extended in the same migration."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    event,
    text,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.db.base import AMOUNT, RATE, Base, TimestampMixin, UUIDPrimaryKeyMixin

CONVERSION_TYPES = ("ai_answer", "report", "converter")
MAX_RECENT_CURRENCIES = 5


class Currency(TimestampMixin, Base):
    __tablename__ = "currencies"
    __table_args__ = (
        CheckConstraint("code ~ '^[A-Z]{3}$'", name="code"),
        CheckConstraint("decimal_places BETWEEN 0 AND 4", name="decimal_places"),
        CheckConstraint("length(name) BETWEEN 1 AND 100", name="name_length"),
    )

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    symbol: Mapped[str] = mapped_column(String(8))
    decimal_places: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class UserCurrencyPreference(TimestampMixin, Base):
    __tablename__ = "user_currency_preferences"
    __table_args__ = (
        CheckConstraint(
            f"cardinality(recent_currencies) <= {MAX_RECENT_CURRENCIES}",
            name="recent_currencies_size",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    reporting_currency: Mapped[str] = mapped_column(
        ForeignKey("currencies.code", ondelete="RESTRICT")
    )
    recent_currencies: Mapped[list[str]] = mapped_column(
        ARRAY(String(3)), server_default=text("'{}'::varchar(3)[]")
    )


class FxConversionAudit(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "fx_conversion_audit"
    __table_args__ = (
        CheckConstraint("source_currency ~ '^[A-Z]{3}$'", name="source_currency"),
        CheckConstraint("target_currency ~ '^[A-Z]{3}$'", name="target_currency"),
        CheckConstraint("rate > 0", name="rate_positive"),
        CheckConstraint(
            "conversion_type IN ('ai_answer', 'report', 'converter')", name="conversion_type"
        ),
        Index("ix_fx_conversion_audit_user_id_created_at", "user_id", "created_at"),
    )

    # No foreign key: the record outlives the user row, like audit_events.
    user_id: Mapped[uuid.UUID] = mapped_column()
    source_currency: Mapped[str] = mapped_column(String(3))
    target_currency: Mapped[str] = mapped_column(String(3))
    source_amount: Mapped[Decimal] = mapped_column(AMOUNT)
    converted_amount: Mapped[Decimal] = mapped_column(AMOUNT)
    rate: Mapped[Decimal] = mapped_column(RATE)
    rate_timestamp: Mapped[datetime] = mapped_column()
    provider: Mapped[str] = mapped_column(String(32))
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    conversion_type: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ConversionAuditImmutableError(RuntimeError):
    """Raised when code tries to change or delete a conversion audit record."""


@event.listens_for(FxConversionAudit, "before_update")
def _refuse_update(_mapper: Mapper[Any], _connection: Any, _target: FxConversionAudit) -> None:
    raise ConversionAuditImmutableError("conversion audit records are append-only")


@event.listens_for(FxConversionAudit, "before_delete")
def _refuse_delete(_mapper: Mapper[Any], _connection: Any, _target: FxConversionAudit) -> None:
    raise ConversionAuditImmutableError("conversion audit records are append-only")
