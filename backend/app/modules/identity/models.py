"""Identity tables. A user row is provisioned from the first valid access token (issuer + subject);
WealthSphere never stores passwords or MFA secrets (Keycloak owns credentials)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
        CheckConstraint("status IN ('active', 'disabled')", name="status"),
    )

    issuer: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    email_verified: Mapped[bool] = mapped_column(server_default=text("false"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'active'"))
    last_seen_at: Mapped[datetime | None] = mapped_column()


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"
    __table_args__ = (CheckConstraint("base_currency ~ '^[A-Z]{3}$'", name="base_currency"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str | None] = mapped_column(String(100))
    base_currency: Mapped[str] = mapped_column(String(3), server_default=text("'USD'"))
    locale: Mapped[str] = mapped_column(String(35), server_default=text("'en'"))
    timezone: Mapped[str] = mapped_column(String(64), server_default=text("'UTC'"))
    # UI preferences only (theme, dashboard layout); validated by schemas.Preferences.
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class RiskProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The user's stated risk tolerance over time (one row per assessment)."""

    __tablename__ = "risk_profiles"
    __table_args__ = (
        CheckConstraint(
            "risk_tolerance IN ('conservative', 'balanced', 'growth', 'aggressive')",
            name="risk_tolerance",
        ),
        CheckConstraint(
            "horizon_years IS NULL OR (horizon_years BETWEEN 0 AND 100)", name="horizon_years"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    risk_tolerance: Mapped[str] = mapped_column(String(16))
    horizon_years: Mapped[int | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(32), server_default=text("'self_assessment'"))
    assessed_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
