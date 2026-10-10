"""Portfolio tables. A portfolio is owned by one user (`user_id`); other users can be added as
members (viewer or editor) in a later phase. Ownership checks use `owned_by` (ADR-0011).

Financial rows are never silently deleted: a portfolio cannot be removed while it has a ledger
(RESTRICT), and a user cannot be removed while they own portfolios. Erasure is the explicit
account-deletion workflow (P15-T05)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PORTFOLIO_TYPES = ("personal", "family", "retirement", "geographic", "strategy")
MEMBER_ROLES = ("viewer", "editor")


class Portfolio(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        CheckConstraint("base_currency ~ '^[A-Z]{3}$'", name="base_currency"),
        CheckConstraint(
            "portfolio_type IN ('personal', 'family', 'retirement', 'geographic', 'strategy')",
            name="portfolio_type",
        ),
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 100", name="name"),
        UniqueConstraint("user_id", "name", name="uq_portfolios_user_id_name"),
        Index("ix_portfolios_user_id_archived_at", "user_id", "archived_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(100))
    base_currency: Mapped[str] = mapped_column(String(3))
    portfolio_type: Mapped[str] = mapped_column(String(16), server_default=text("'personal'"))
    description: Mapped[str | None] = mapped_column(String(500))
    # Archived portfolios stay readable but take no new postings; nothing is deleted.
    archived_at: Mapped[datetime | None] = mapped_column()


class PortfolioMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Another user's access to a portfolio. The owner is `portfolios.user_id`, not a member."""

    __tablename__ = "portfolio_members"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "user_id", name="uq_portfolio_members_portfolio_id_user_id"
        ),
        CheckConstraint("role IN ('viewer', 'editor')", name="role"),
        Index("ix_portfolio_members_user_id", "user_id"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16), server_default=text("'viewer'"))
