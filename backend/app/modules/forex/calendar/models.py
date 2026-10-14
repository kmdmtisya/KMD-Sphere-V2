"""Calendar tables (P13-T04.1, migration 0021). Reference data, not user data.

An event row is upserted by (source, source event id), because a scheduled release gains its
`actual` value later. A published `actual` is never cleared, and `actual_seen_at` keeps when it was
first seen. Confirmed values, the consensus forecast and commentary are separate columns."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ARRAY, CheckConstraint, Date, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

VALUE = Numeric(28, 8)
LICENCES = "('demo', 'public_domain', 'unconfirmed', 'licensed')"


class ForexEconomicEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forex_economic_events"
    __table_args__ = (
        UniqueConstraint("source", "source_event_id", name="uq_forex_economic_events_source_event"),
        CheckConstraint(
            "kind IN ('indicator', 'central_bank_decision', 'speech', 'other')", name="kind"
        ),
        CheckConstraint("importance IN ('low', 'medium', 'high')", name="importance"),
        CheckConstraint(f"licence_status IN {LICENCES}", name="licence_status"),
        CheckConstraint("cardinality(currencies) >= 1", name="currencies"),
        Index("ix_forex_economic_events_scheduled_at", "scheduled_at"),
    )

    source: Mapped[str] = mapped_column(String(32))
    source_event_id: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(24))
    currencies: Mapped[list[str]] = mapped_column(ARRAY(String(3)))
    scheduled_at: Mapped[datetime] = mapped_column()  # UTC
    importance: Mapped[str] = mapped_column(String(8))
    unit: Mapped[str | None] = mapped_column(String(20))
    actual: Mapped[Decimal | None] = mapped_column(VALUE)  # confirmed, once released
    previous: Mapped[Decimal | None] = mapped_column(VALUE)  # confirmed (as last published)
    forecast: Mapped[Decimal | None] = mapped_column(VALUE)  # consensus expectation, not a fact
    commentary: Mapped[str | None] = mapped_column(Text)  # speculative, never data
    source_url: Mapped[str | None] = mapped_column(String(500))
    is_demo: Mapped[bool] = mapped_column()
    licence_status: Mapped[str] = mapped_column(String(16))
    retrieved_at: Mapped[datetime] = mapped_column()
    actual_seen_at: Mapped[datetime | None] = mapped_column()


class ForexPolicyRate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forex_policy_rates"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "currency",
            "effective_date",
            name="uq_forex_policy_rates_source_currency_date",
        ),
        CheckConstraint("rate BETWEEN -10 AND 100", name="rate"),
        CheckConstraint(f"licence_status IN {LICENCES}", name="licence_status"),
        Index("ix_forex_policy_rates_currency_effective_date", "currency", "effective_date"),
    )

    source: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    bank: Mapped[str] = mapped_column(String(100))
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 4))  # percent a year
    effective_date: Mapped[date] = mapped_column(Date)
    decided_at: Mapped[datetime] = mapped_column()
    source_url: Mapped[str | None] = mapped_column(String(500))
    is_demo: Mapped[bool] = mapped_column()
    licence_status: Mapped[str] = mapped_column(String(16))
    retrieved_at: Mapped[datetime] = mapped_column()
