"""Devices that may receive push notifications (P09-T08). Every row belongs to one user; every
query is scoped to the owner (ADR-0011). A device token is a delivery address, not a credential,
but it is never logged or returned in full."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin

PLATFORMS = ("android", "ios")


class Device(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint("platform IN ('android', 'ios')", name="platform"),
        CheckConstraint("length(token) BETWEEN 8 AND 4096", name="token_length"),
        UniqueConstraint("user_id", "token", name="uq_devices_user_id_token"),
        Index("ix_devices_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(8))
    token: Mapped[str] = mapped_column(String(4096))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
