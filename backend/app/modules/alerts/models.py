"""Watchlist, alert and alert-event tables (P08-T07). Every row belongs to one user; every query
is scoped to the owner (ADR-0011). Alerts are one-shot: an active alert that fires records an
event and becomes `triggered`; the user re-arms it by setting it `active` again. This keeps an
alert from firing again on every price update while its condition stays true."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import RATE, Base, TimestampMixin, UUIDPrimaryKeyMixin

ALERT_TYPES = ("price_above", "price_below", "allocation_above")
ALERT_STATUSES = ("active", "triggered", "paused")


class WatchlistItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "asset_id", name="uq_watchlist_items_user_id_asset_id"),
        Index("ix_watchlist_items_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class AlertPreference(TimestampMixin, Base):
    """What the user wants to hear about. No row means everything is on."""

    __tablename__ = "alert_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    alerts_enabled: Mapped[bool] = mapped_column(server_default=text("true"))
    price_alerts_enabled: Mapped[bool] = mapped_column(server_default=text("true"))
    allocation_alerts_enabled: Mapped[bool] = mapped_column(server_default=text("true"))


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('price_above', 'price_below', 'allocation_above')", name="alert_type"
        ),
        CheckConstraint("status IN ('active', 'triggered', 'paused')", name="status"),
        CheckConstraint("threshold > 0", name="threshold_positive"),
        CheckConstraint(
            "(alert_type IN ('price_above', 'price_below') AND asset_id IS NOT NULL "
            "AND portfolio_id IS NULL AND asset_class IS NULL) OR "
            "(alert_type = 'allocation_above' AND asset_id IS NULL AND portfolio_id IS NOT NULL "
            "AND asset_class IS NOT NULL AND threshold <= 100)",
            name="shape",
        ),
        CheckConstraint("note IS NULL OR length(btrim(note)) BETWEEN 1 AND 200", name="note"),
        Index("ix_alerts_user_id_status", "user_id", "status"),
        Index("ix_alerts_status", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    alert_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12), server_default=text("'active'"))
    # A price (in the asset's currency) or a percentage (0 to 100) of the portfolio.
    threshold: Mapped[Decimal] = mapped_column(RATE)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE")
    )
    asset_class: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(200))
    triggered_at: Mapped[datetime | None] = mapped_column()


class AlertEvent(UUIDPrimaryKeyMixin, Base):
    """An alert that fired. One per (alert, trigger key): the key is the price observation or the
    day, so evaluating the same data twice records one event."""

    __tablename__ = "alert_events"
    __table_args__ = (
        UniqueConstraint("alert_id", "trigger_key", name="uq_alert_events_alert_id_trigger_key"),
        Index("ix_alert_events_user_id_triggered_at", "user_id", "triggered_at"),
    )

    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    trigger_key: Mapped[str] = mapped_column(String(100))
    observed_value: Mapped[Decimal] = mapped_column(RATE)
    observed_as_of: Mapped[datetime] = mapped_column()
    triggered_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    seen_at: Mapped[datetime | None] = mapped_column()
